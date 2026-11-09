# ADR 0003: Encrypt LangGraph checkpoints with AES-256-GCM (GCM path taken; EAX reserved)

- Status: Accepted
- Spec: `backend-api-auth-jobs-crypto` (Spec 3)
- Supersedes: none
- Related: Requirement 9.8, 9.9; design § "Encrypted checkpointer"; Property 45

## Context

The agent runtime (Spec 4) persists LangGraph checkpoints — the serialized
graph state plus any pending writes — so a turn can recover after a worker
restart. Those checkpoints contain conversation-derived content and therefore
must be encrypted before they reach PostgreSQL under the same per-conversation
DEK/KEK scheme as every other sensitive field (titles, messages, domain state,
plans, traces).

The project's default AEAD is **AES-256-GCM** with a 96-bit nonce and
contextual AAD binding `purpose ‖ owner ‖ conversation ‖ record ‖ version`
(ADR-aligned with the crypto module). The handoff flagged that *some* LangGraph
serialization paths could, in principle, make GCM awkward for the checkpoint
blob specifically (for example if the framework required streaming or
random-access over a fixed single ciphertext), and pre-authorized an **AES-EAX
fallback for that blob only** as an escape hatch.

## Decision

**We take the GCM path.** We evaluated GCM viability for the serialized
checkpoint blob and found no framework constraint that makes it infeasible:

- LangGraph's `SerializerProtocol` (`JsonPlusSerializer`) reduces a checkpoint
  and its pending writes to opaque `bytes`. GCM encrypts those bytes as a
  single AEAD unit exactly like any other sensitive column.
- There is no streaming, random-access, or fixed-size-nonce-reuse requirement
  on the checkpoint blob. The checkpoint and the pending writes are encrypted
  as whole blobs with fresh 96-bit nonces and distinct record ids.
- Recovery reads the whole blob, decrypts it (fail-closed on tag mismatch), and
  deserializes — no partial/seeking access is needed.

The `EncryptedCheckpointer` therefore encrypts the checkpoint blob and the
pending-writes blob with **AES-256-GCM via the shared `CryptoService`**, and
`EncryptedCheckpointer.checkpoint_cipher == "GCM"`.

**The EAX fallback is reserved, not used.** It remains documented here as the
pre-authorized escape hatch should a future LangGraph change make GCM genuinely
infeasible for the checkpoint blob *only*. If that ever happens:

- EAX would apply to the **checkpoint blob only**; GCM is **never** relaxed for
  titles, messages, domain state, plans, or traces;
- the fallback would be recorded by bumping `cipher_version` and setting
  `checkpoint_cipher = "EAX"`, with this ADR updated to "EAX path taken" and
  the reason stated.

## Consequences

- One AEAD (GCM) is used uniformly across every sensitive field, including
  checkpoints — simpler to reason about and to audit.
- `Property 45` is verified against the GCM path: round-trip preserves the
  checkpoint and pending writes, and a tampered blob fails closed.
- The EAX code path is intentionally not exercised; the escape hatch is a
  documented contingency, not live behavior.
