"""Unit + property tests for SourceInventory and verified_replay hashing (Task 5, 6).

Pure-logic coverage: the SHA-256 compare that the halting behaviour pivots on,
the template/role rules, and Property 3 (hash mismatch halts) exercised against
both the SourceInventory digest check and the replay-artifact digest check
without needing a real PDF or a database.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from series76_data.errors import IngestionError, IngestionErrorCode
from series76_data.models.enums import AuthorityRole
from series76_data.pipeline.extractor_replay import (
    ReplayArtifact,
    ReplayManifestView,
    VerifiedReplayExtractor,
)
from series76_data.pipeline.source_inventory import (
    AUTHORITY_BY_FILENAME,
    RECOGNIZED_TEMPLATES,
    compute_sha256,
    digests_match,
    is_authorized_technical_source,
    resolve_authority_role,
    verify_digest,
)


def test_electric_data_is_authorized_summary_is_context_only() -> None:
    assert (
        AUTHORITY_BY_FILENAME["series_76_electric_data.pdf"]
        is AuthorityRole.AUTHORIZED_TECHNICAL_SOURCE
    )
    assert AUTHORITY_BY_FILENAME["series_76_summary.pdf"] is AuthorityRole.CONTEXT_ONLY
    assert is_authorized_technical_source(
        resolve_authority_role("series_76_electric_data.pdf")
    )
    # The summary PDF can never be used as a technical source.
    assert not is_authorized_technical_source(
        resolve_authority_role("series_76_summary.pdf")
    )


def test_unknown_filename_defaults_to_context_only() -> None:
    assert resolve_authority_role("random.pdf") is AuthorityRole.CONTEXT_ONLY


def test_known_templates_recognized() -> None:
    assert "T03" in RECOGNIZED_TEMPLATES
    assert "summary" in RECOGNIZED_TEMPLATES
    assert "T99" not in RECOGNIZED_TEMPLATES


def test_matching_digest_does_not_raise() -> None:
    data = b"hello world"
    digest = compute_sha256(data)
    # Must not raise.
    verify_digest("doc:x", digest, compute_sha256(data))
    assert digests_match(digest, digest.upper())


# Feature: data-and-ingestion, Property 3: Hash mismatch halts and preserves the
# prior edition. For any registered document whose recomputed SHA-256 differs
# from its recorded digest, the pipeline reports HASH_MISMATCH and halts before
# producing an edition.
@given(
    recorded=st.binary(min_size=0, max_size=64),
    actual=st.binary(min_size=0, max_size=64),
)
def test_property_3_source_hash_mismatch_halts(recorded: bytes, actual: bytes) -> None:
    recorded_digest = compute_sha256(recorded)
    recomputed_digest = compute_sha256(actual)
    if recorded == actual:
        # Equal bytes -> equal digests -> no halt.
        verify_digest("doc:x", recorded_digest, recomputed_digest)
        assert digests_match(recorded_digest, recomputed_digest)
    else:
        # Different bytes -> digests differ with overwhelming probability -> halt.
        assert not digests_match(recorded_digest, recomputed_digest)
        try:
            verify_digest("doc:x", recorded_digest, recomputed_digest)
        except IngestionError as exc:
            assert exc.failure.code is IngestionErrorCode.HASH_MISMATCH
        else:  # pragma: no cover - would indicate a hash collision
            raise AssertionError("expected HASH_MISMATCH on differing digests")


# Feature: data-and-ingestion, Property 3: Hash mismatch halts and preserves the
# prior edition — exercised on the verified_replay artifact digest check. A
# tampered artifact halts the replay before any edition/fact is produced.
@given(
    payload=st.binary(min_size=0, max_size=128),
    tamper=st.binary(min_size=1, max_size=16),
    tamper_recorded=st.booleans(),
)
def test_property_3_replay_artifact_hash_mismatch_halts(
    payload: bytes, tamper: bytes, tamper_recorded: bool
) -> None:
    good_digest = compute_sha256(payload)
    extractor = VerifiedReplayExtractor()

    # A decoder that ignores payload bytes — this property is about the hash
    # check that runs BEFORE any decoding, so arbitrary binary payloads are fine.
    def _noop_decode(_manifest: ReplayManifestView) -> list[dict[str, object]]:
        return []

    # Baseline: a faithful artifact reconstructs (verification passes) without raising.
    faithful = ReplayManifestView(
        manifest_digest="d",
        artifacts={
            "a": ReplayArtifact(name="a", payload=payload, recorded_sha256=good_digest)
        },
        confirmable_transformations=frozenset(),
    )
    result = extractor.extract(faithful, decode=_noop_decode)
    assert result.confirmed_artifacts == ["a"]

    # Tamper either the recorded digest or the payload so they disagree.
    if tamper_recorded:
        bad_recorded = compute_sha256(payload + tamper)
        artifact = ReplayArtifact(
            name="a", payload=payload, recorded_sha256=bad_recorded
        )
    else:
        artifact = ReplayArtifact(
            name="a", payload=payload + tamper, recorded_sha256=good_digest
        )
    tampered = ReplayManifestView(
        manifest_digest="d",
        artifacts={"a": artifact},
        confirmable_transformations=frozenset(),
    )
    try:
        extractor.extract(tampered)
    except IngestionError as exc:
        assert exc.failure.code is IngestionErrorCode.HASH_MISMATCH
    else:  # pragma: no cover - would indicate a hash collision
        raise AssertionError("expected HASH_MISMATCH on tampered artifact")


def test_replay_unconfirmed_transformation_halts() -> None:
    payload = b"{}"
    extractor = VerifiedReplayExtractor()
    manifest = ReplayManifestView(
        manifest_digest="d",
        artifacts={
            "a": ReplayArtifact(
                name="a",
                payload=payload,
                recorded_sha256=compute_sha256(payload),
                declared_transformations=("unknown-transform",),
            )
        },
        confirmable_transformations=frozenset({"known"}),
    )
    try:
        extractor.extract(manifest)
    except IngestionError as exc:
        assert exc.failure.code is IngestionErrorCode.HASH_MISMATCH
    else:
        raise AssertionError("expected HASH_MISMATCH for unconfirmed transformation")


def test_replay_module_imports_no_network_or_ai_client() -> None:
    """verified_replay makes zero external AI/OCR/LLM calls (Req 2.1).

    Assert the module's import graph contains no network/LLM/OCR client, so a
    replay reconstruction cannot reach the network by construction.
    """

    import series76_data.pipeline.extractor_replay as replay

    forbidden = {
        "google",
        "google.generativeai",
        "openai",
        "httpx",
        "requests",
        "urllib.request",
        "socket",
        "paddleocr",
        "docling",
    }
    referenced = set(vars(replay).keys())
    assert not (forbidden & referenced)
    # The only imports the module needs are stdlib hashing/json + internal deps.
    assert replay.__dict__.get("json") is not None
