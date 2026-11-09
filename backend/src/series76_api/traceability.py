"""Spec 3 traceability map: Requirements + Properties -> implementation/test.

This is the machine-checkable coverage report asserted by Task 18. It maps every
Correctness Property (P1-P49) to the implementation site(s) and the test(s) that
realize it, and every Requirement group (1-12) to at least one task. The unit
test ``test_spec3_traceability`` asserts full coverage: no property and no
requirement is orphaned, and every router/use case/repository/worker/crypto/
checkpointer adapter is registered at the composition root.

The mandatory ``POST /api/conversation`` contract (non-empty ``session_id`` +
``answer``) is tracked explicitly as holding across every job path.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PropertyTrace:
    """One correctness property mapped to its implementation + test sites."""

    number: int
    summary: str
    implementation: tuple[str, ...]
    tests: tuple[str, ...] = field(default_factory=tuple)


# Half A properties (P1-P10, P38-P44) are implemented + tested in Half A; listed
# here only so the coverage assertion spans the full P1-P49 range. Half B
# (P11-P37, P45-P49) carries the detailed implementation/test sites.
_HALF_A_PROPERTIES: dict[int, str] = {
    1: "Passwords stored irreversibly with Argon2id",
    2: "Opaque token verifiers are SHA-256, constant-time compared",
    3: "Registration always creates role user, never elevates",
    4: "Invalid registration creates no account, no enumeration",
    5: "Login failure indistinguishable and rate-limited",
    6: "Refresh rotation atomic + single-winner",
    7: "Refresh reuse revokes the entire family",
    8: "Logout revokes only the current session family",
    9: "/me never discloses secret material",
    10: "Ownership session-authoritative; cross-user = indistinguishable 404",
    38: "Encryption round-trips, binds AAD, unique nonces",
    39: "Sensitive data ciphertext at rest; only allowlist cleartext",
    40: "Each DEK stored only wrapped; KEK never in DB",
    41: "Decryption fails closed on tamper/legacy/key-unavailable",
    42: "Authorization precedes decryption",
    43: "Endpoint authorization precedes any model/tool dispatch",
    44: "Secrets never appear in logs or traces",
}

HALF_B_PROPERTIES: tuple[PropertyTrace, ...] = (
    PropertyTrace(
        11,
        "The mandatory POST contract is inviolable",
        (
            "application/conversation_service.py:run_sync_turn",
            "api/routers/conversation.py",
        ),
        (
            "tests/integration/test_spec3_conversation_api.py::test_property_11_mandatory_contract_inviolable",
        ),
    ),
    PropertyTrace(
        12,
        "Omitting session_id creates a caller-owned stable conversation",
        ("application/conversation_service.py:_resolve_conversation",),
        (
            "tests/integration/test_spec3_conversation_api.py::test_property_12_omit_session_creates_stable_owned_conversation",
        ),
    ),
    PropertyTrace(
        13,
        "Clarification/confirmation carries status and only verified numbers",
        (
            "application/agent_seam.py:FakeAgent",
            "application/conversation_service.py:_build_envelope",
        ),
        (
            "tests/integration/test_spec3_conversation_api.py::test_property_13_clarification_confirmation_status",
        ),
    ),
    PropertyTrace(
        14,
        "Multi-turn history persists across restart, owner-scoped",
        (
            "application/conversation_service.py:get_messages",
            "infrastructure/repositories.py:MessageRepository",
        ),
        (
            "tests/integration/test_spec3_conversation_api.py::test_property_14_history_persists_across_restart_owner_scoped",
        ),
    ),
    PropertyTrace(
        15,
        "Repeated client_request_id yields exactly one turn effect",
        (
            "application/conversation_service.py:run_sync_turn",
            "application/jobs_service.py:accept",
            "migrations/0006:uq_turn_jobs_owner_request",
        ),
        (
            "tests/integration/test_spec3_conversation_api.py::test_property_15_idempotent_client_request_id",
        ),
    ),
    PropertyTrace(
        16,
        "Invalid query rejected with no persistence",
        ("application/conversation_service.py:validate_query",),
        (
            "tests/integration/test_spec3_conversation_api.py::test_property_16_invalid_query_rejected_no_persistence",
        ),
    ),
    PropertyTrace(
        17,
        "Job acceptance returns 202 with QUEUED",
        (
            "application/jobs_service.py:accept",
            "api/routers/conversation.py:enqueue_turn",
        ),
        (
            "tests/integration/test_spec3_jobs_api.py::test_property_17_accept_202_queued",
        ),
    ),
    PropertyTrace(
        18,
        "Polling returns one state + shared envelope on COMPLETED",
        ("application/jobs_service.py:poll", "api/routers/jobs.py:poll_job"),
        (
            "tests/integration/test_spec3_jobs_api.py::test_property_18_poll_state_and_envelope",
        ),
    ),
    PropertyTrace(
        19,
        "Cancellation is idempotent",
        ("application/jobs_service.py:cancel",),
        (
            "tests/integration/test_spec3_jobs_api.py::test_property_19_cancel_idempotent",
        ),
    ),
    PropertyTrace(
        20,
        "Polling headers correct per state (no-store; Retry-After 1-60)",
        ("api/routers/jobs.py:poll_job", "application/jobs_service.py:poll"),
        ("tests/integration/test_spec3_jobs_api.py::test_property_20_poll_headers",),
    ),
    PropertyTrace(
        21,
        "Exceeding pending-job cap rejects without side effects",
        ("application/jobs_service.py:accept",),
        (
            "tests/integration/test_spec3_jobs_api.py::test_property_21_pending_cap_rejects",
        ),
    ),
    PropertyTrace(
        22,
        "Accepted jobs durable across restart",
        (
            "infrastructure/repositories.py:TurnJobRepository",
            "migrations/0006:turn_jobs",
        ),
        (
            "tests/integration/test_spec3_jobs_api.py::test_property_22_accepted_jobs_durable_across_restart",
        ),
    ),
    PropertyTrace(
        23,
        "At most one RUNNING per conversation; distinct parallel",
        (
            "application/worker_service.py:_claim_phase",
            "infrastructure/repositories.py:has_other_running",
        ),
        (
            "tests/integration/test_spec3_worker_protocol.py::test_property_23_at_most_one_running_per_conversation",
        ),
    ),
    PropertyTrace(
        24,
        "accepted_seq transactional, strictly increasing, not claim-order",
        (
            "infrastructure/repositories.py:next_accepted_seq",
            "migrations/0006:uq_turn_jobs_session_seq",
        ),
        (
            "tests/integration/test_spec3_jobs_api.py::test_property_24_accepted_seq_strictly_increasing",
        ),
    ),
    PropertyTrace(
        25,
        "Claim establishes single fenced lease holder",
        (
            "application/worker_service.py:_claim_phase",
            "infrastructure/repositories.py:lease",
        ),
        (
            "tests/integration/test_spec3_worker_protocol.py::test_property_25_claim_single_fenced_lease",
        ),
    ),
    PropertyTrace(
        26,
        "Stale fencing writes rejected, no duplication",
        (
            "infrastructure/repositories.py:persist_result",
            "application/worker_service.py:_persist_phase",
        ),
        (
            "tests/integration/test_spec3_worker_protocol.py::test_property_26_stale_fence_rejected",
        ),
    ),
    PropertyTrace(
        27,
        "No SQL transaction spans the model call",
        ("application/worker_service.py:process_one",),
        (
            "tests/integration/test_spec3_worker_protocol.py::test_property_27_no_txn_spans_model_call",
        ),
    ),
    PropertyTrace(
        28,
        "Plan revisions strictly increasing; only current confirms",
        (
            "application/plans_service.py:create_revision",
            "application/plans_service.py:confirm",
        ),
        (
            "tests/integration/test_spec3_plans_api.py::test_property_28_revisions_increasing_current_only",
        ),
    ),
    PropertyTrace(
        29,
        "Plan confirmation idempotent for the current revision",
        (
            "application/plans_service.py:confirm",
            "infrastructure/repositories.py:mark_confirmed_executed",
        ),
        (
            "tests/integration/test_spec3_plans_api.py::test_property_29_confirm_idempotent",
        ),
    ),
    PropertyTrace(
        30,
        "Unauthenticated plan confirmation performs no effect",
        (
            "api/routers/plans.py:confirm_plan",
            "application/authorization.py:authenticate",
        ),
        (
            "tests/integration/test_spec3_plans_api.py::test_property_30_unauthenticated_confirm_no_effect",
        ),
    ),
    PropertyTrace(
        31,
        "Deletion cancels, tombstones, purges, crypto-shreds",
        ("application/deletion_service.py:delete",),
        (
            "tests/integration/test_spec3_delete_trace_api.py::test_property_31_delete_tombstone_purge_shred",
        ),
    ),
    PropertyTrace(
        32,
        "No resurrection of a deleted conversation",
        (
            "application/worker_service.py:_persist_phase",
            "application/deletion_service.py:delete",
        ),
        (
            "tests/integration/test_spec3_delete_trace_api.py::test_property_32_no_resurrection",
        ),
    ),
    PropertyTrace(
        33,
        "Non-owner deletion has no effect",
        ("application/deletion_service.py:delete",),
        (
            "tests/integration/test_spec3_delete_trace_api.py::test_property_33_non_owner_delete_no_effect",
        ),
    ),
    PropertyTrace(
        34,
        "Deleted vs not-owned references indistinguishable",
        (
            "application/deletion_service.py:delete",
            "api/routers/sessions.py:delete_session",
        ),
        (
            "tests/integration/test_spec3_delete_trace_api.py::test_property_34_deleted_vs_not_owned_indistinguishable",
        ),
    ),
    PropertyTrace(
        35,
        "Session listing + title search owner-scoped, decrypt-after-authorize",
        (
            "application/conversation_service.py:list_sessions",
            "infrastructure/repositories.py:list_for_owner",
        ),
        (
            "tests/integration/test_spec3_conversation_api.py::test_property_35_listing_title_search_owner_scoped",
        ),
    ),
    PropertyTrace(
        36,
        "Message history deterministic total order, excludes traces",
        ("infrastructure/repositories.py:MessageRepository.list_for_session",),
        (
            "tests/integration/test_spec3_conversation_api.py::test_property_36_message_history_total_order",
        ),
    ),
    PropertyTrace(
        37,
        "Rename enforces length + ownership, persists ciphertext",
        ("application/conversation_service.py:rename_session",),
        (
            "tests/integration/test_spec3_conversation_api.py::test_property_37_rename_length_ownership_ciphertext",
        ),
    ),
    PropertyTrace(
        45,
        "Checkpoints GCM-serialized, fail-closed, recoverable",
        (
            "infrastructure/checkpointer.py:EncryptedCheckpointer",
            "docs/adr/0003-checkpoint-eax-fallback.md",
        ),
        (
            "tests/unit/test_spec3_envelope_trace_properties.py::test_property_45_checkpoint_blob_gcm_roundtrip_fail_closed",
            "tests/integration/test_spec3_checkpointer.py::test_property_45_checkpoint_gcm_recoverable_fail_closed",
        ),
    ),
    PropertyTrace(
        46,
        "Trace sanitized to developer-owner or identical denial",
        (
            "application/trace_service.py:get_sanitized_trace",
            "domain/trace.py:sanitize_trace",
        ),
        (
            "tests/integration/test_spec3_delete_trace_api.py::test_property_46_trace_developer_owner_or_identical_denial",
        ),
    ),
    PropertyTrace(
        47,
        "Error envelope stable + status mapping consistent",
        ("api/errors.py:build_error_response", "domain/errors.py:HTTP_STATUS_BY_CODE"),
        (
            "tests/integration/test_spec3_errors_ready_api.py::test_property_47_error_envelope_stable",
        ),
    ),
    PropertyTrace(
        48,
        "NO_RESULTS vs UPSTREAM_UNAVAILABLE never conflated",
        (
            "application/agent_seam.py:OutcomeKind",
            "application/conversation_service.py:run_sync_turn",
        ),
        (
            "tests/integration/test_spec3_errors_ready_api.py::test_property_48_no_results_vs_upstream_unavailable",
        ),
    ),
    PropertyTrace(
        49,
        "Readiness distinguishes DB from other deps; health liveness-only",
        ("api/routers/health.py:ready", "api/routers/health.py:health"),
        (
            "tests/integration/test_spec3_errors_ready_api.py::test_property_49_ready_distinguishes_dependencies",
        ),
    ),
)

# Requirement group -> the task(s)/area realizing it (1-12 all covered).
REQUIREMENT_TASKS: dict[int, tuple[str, ...]] = {
    1: ("Task 1/18: app skeleton + composition root + import boundary",),
    2: ("Task 4/5: auth register/login/refresh/logout/me",),
    3: ("Task 6: authorization / ownership guard",),
    4: ("Task 7: conversation persistence + mandatory sync POST",),
    5: ("Task 11: async endpoints 202/poll/cancel + caps",),
    6: ("Task 9/10: durable jobs + worker claim/lease/fencing",),
    7: ("Task 12: plan confirmation + revision",),
    8: ("Task 8/13: listing/messages/rename + deletion",),
    9: ("Task 3/14: crypto module + encrypted checkpointer",),
    10: ("Task 15: debug trace endpoint",),
    11: ("Task 16: error envelope + health/ready + transport",),
    12: ("Task 2/16/17: migrations + reproducibility + seed CLI",),
}

# The mandatory POST contract holds across every job path.
MANDATORY_CONTRACT_PATHS: tuple[str, ...] = (
    "sync POST /api/conversation (always returns the final envelope)",
    "async POST /api/conversation/jobs (202 QUEUED, never substitutes the sync final response)",
    "GET /api/jobs/{id} (returns the SAME Response_Envelope on COMPLETED)",
)


def all_property_numbers() -> set[int]:
    """Return the full set of property numbers covered (P1-P49)."""

    return set(_HALF_A_PROPERTIES) | {p.number for p in HALF_B_PROPERTIES}


__all__ = [
    "PropertyTrace",
    "HALF_B_PROPERTIES",
    "REQUIREMENT_TASKS",
    "MANDATORY_CONTRACT_PATHS",
    "all_property_numbers",
]
