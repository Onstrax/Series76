"""Pure Spec 3 Half B property/contract tests: content_blocks + trace sanitize.

These are DB-free: they exercise the structural ``content_blocks`` discriminated
union (unknown-kind -> text fallback), the pure trace sanitization policy
(Property 44 — no secrets in a trace), and the GCM checkpoint blob round-trip
primitive used by Property 45. Named ``spec3`` for selectability.
"""

from __future__ import annotations

import os
import uuid

from hypothesis import given
from hypothesis import strategies as st

from series76_api.api.envelopes import (
    BlockKind,
    TextBlock,
    parse_content_block,
    parse_content_blocks,
)
from series76_api.domain.crypto import DEK_KEY_BYTES, AADContext, CryptoPurpose
from series76_api.domain.errors import DecryptionError
from series76_api.domain.trace import sanitize_trace, sanitize_value
from series76_api.infrastructure.crypto import Ciphertext, CryptoService

_KNOWN_KINDS = [k.value for k in BlockKind]


# Feature: backend-api-auth-jobs-crypto, Property 13/4.8 (support): an unknown
# content-block kind degrades to a safe text fallback and never raises.
@given(
    kind=st.text(min_size=1, max_size=20).filter(lambda k: k not in _KNOWN_KINDS),
    text=st.text(max_size=100),
)
def test_spec3_content_block_unknown_kind_fallback(kind: str, text: str) -> None:
    """Any unknown/garbled block kind degrades to a TextBlock (no exception)."""

    block = parse_content_block({"kind": kind, "text": text})
    assert isinstance(block, TextBlock)
    assert block.kind == BlockKind.TEXT
    assert block.text == text

    # A known kind with a malformed payload also degrades rather than raising.
    degraded = parse_content_blocks(
        [{"kind": "bar_chart", "values": "not-a-list"}, {"kind": kind}]
    )
    assert all(isinstance(b, TextBlock) for b in degraded) or degraded[0].kind in (
        BlockKind.BAR_CHART,
        BlockKind.TEXT,
    )


# Feature: backend-api-auth-jobs-crypto, Property 44: Secrets never appear in
# logs or traces (pure sanitization policy over the trace shape).
@given(secret_seed=st.binary(min_size=8, max_size=48))
def test_property_44_trace_sanitization_strips_all_secrets(secret_seed: bytes) -> None:
    """A trace sanitized for a developer-owner contains no secret-named field.

    A unique high-entropy marker is embedded under every forbidden key name
    (token, secret, kek, dek, system prompt, authorization header, ...). The
    sanitizer leaves the marker nowhere in the output while preserving the
    allowed tool args/results and clamping negative timings to non-negative.
    """

    marker = "SECRET_" + secret_seed.hex()
    raw = {
        "tool_args": {
            "part_number": "ABC",
            "authorization": marker,
            "api_key": marker,
            "nested": {"system_prompt": marker, "kept": "visible"},
        },
        "tool_results": [
            {"value": "7V", "token": marker},
            {"dek": marker, "ok": "fine"},
        ],
        "steps": [{"bearer": marker, "name": "lookup"}],
        "duration_ms": -5,
        "kek": marker,
        "system_prompt": marker,
    }
    sanitized = sanitize_trace(raw)

    # No secret marker survives anywhere in the sanitized output.
    assert marker not in repr(sanitized)
    # The forbidden top-level fields are dropped entirely.
    assert "kek" not in sanitized
    assert "system_prompt" not in sanitized
    # Allowed, non-secret content is preserved.
    assert sanitized["tool_args"]["part_number"] == "ABC"
    assert sanitized["tool_args"]["nested"]["kept"] == "visible"
    assert sanitized["tool_results"][0]["value"] == "7V"
    assert sanitized["tool_results"][1]["ok"] == "fine"
    assert sanitized["steps"][0]["name"] == "lookup"
    # Negative timing clamped to a non-negative integer.
    assert sanitized["duration_ms"] == 0

    # sanitize_value is recursive and idempotent on a clean fragment.
    clean = {"a": [1, 2, {"b": "c"}]}
    assert sanitize_value(clean) == clean


# Feature: backend-api-auth-jobs-crypto, Property 45 (primitive): the GCM
# checkpoint blob round-trips and fails closed on tamper.
@given(
    checkpoint=st.binary(min_size=0, max_size=1024),
    pending=st.binary(min_size=0, max_size=1024),
    flip=st.integers(min_value=0, max_value=1_000_000),
)
def test_property_45_checkpoint_blob_gcm_roundtrip_fail_closed(
    checkpoint: bytes, pending: bytes, flip: int
) -> None:
    """A checkpoint + pending-writes blob GCM-round-trips; a tampered blob fails.

    This exercises the encryption contract the ``EncryptedCheckpointer`` uses
    for the serialized checkpoint blob (the GCM path, per ADR 0003): both the
    checkpoint and the pending-writes blob decrypt to the originals, and a
    single flipped byte fails the tag check (fail closed).
    """

    svc = CryptoService(os.urandom(DEK_KEY_BYTES))
    dek = svc.generate_dek()
    owner, conv, rec = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ctx = AADContext(
        purpose=CryptoPurpose.CHECKPOINT,
        owner_id=owner,
        conversation_id=conv,
        record_id=rec,
    )
    cp_blob = svc.encrypt(dek, checkpoint, ctx).blob
    pw_blob = svc.encrypt(dek, pending, ctx).blob

    assert svc.decrypt(dek, Ciphertext(cp_blob), ctx) == checkpoint
    assert svc.decrypt(dek, Ciphertext(pw_blob), ctx) == pending

    tampered = bytearray(cp_blob)
    tampered[flip % len(tampered)] ^= 0x01
    try:
        svc.decrypt(dek, Ciphertext(bytes(tampered)), ctx)
        raise AssertionError("tampered checkpoint blob must fail closed")
    except DecryptionError:
        pass
