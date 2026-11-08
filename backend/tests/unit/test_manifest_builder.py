"""Unit + property tests for the ManifestBuilder canonical digest (Task 13)."""

from __future__ import annotations

from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from series76_data.pipeline.manifest_builder import (
    ManifestBuilder,
    VerificationManifestData,
    compute_manifest_digest,
)


def _manifest(
    source_shas: dict[str, str],
    facts: list[dict[str, Any]],
) -> VerificationManifestData:
    return VerificationManifestData(
        source_shas=source_shas,
        normalization_version="n1",
        rules_version="r1",
        extractor_version="e1",
        canonical_facts=facts,
        corrections=[],
        verification_report={"passed": True},
    )


def test_digest_is_stable_regardless_of_key_order() -> None:
    a = _manifest({"b.pdf": "2", "a.pdf": "1"}, [{"x": 1, "y": 2}])
    b = _manifest({"a.pdf": "1", "b.pdf": "2"}, [{"y": 2, "x": 1}])
    assert compute_manifest_digest(a) == compute_manifest_digest(b)


# Feature: data-and-ingestion, Property (manifest stability, Req 1.5, 2.2):
# identical approved artifacts produce an identical canonical digest; any change
# produces a different digest.
@given(
    shas=st.dictionaries(
        st.text(min_size=1, max_size=8),
        st.text(min_size=1, max_size=16),
        min_size=1,
        max_size=5,
    ),
    bump=st.text(min_size=1, max_size=4),
)
def test_property_manifest_digest_identical_and_change_sensitive(
    shas: dict[str, str], bump: str
) -> None:
    base = _manifest(dict(shas), [{"k": "v"}])
    same = _manifest(dict(shas), [{"k": "v"}])
    # Identical content -> identical digest.
    assert compute_manifest_digest(base) == compute_manifest_digest(same)

    # Any change -> different digest.
    changed_shas = dict(shas)
    first_key = sorted(changed_shas)[0]
    changed_shas[first_key] = changed_shas[first_key] + bump
    changed = _manifest(changed_shas, [{"k": "v"}])
    assert compute_manifest_digest(changed) != compute_manifest_digest(base)


def test_builder_binds_digest() -> None:
    data = _manifest({"a.pdf": "1"}, [{"k": "v"}])
    built = ManifestBuilder().build(data)
    assert built.manifest_digest == compute_manifest_digest(data)
    assert built.source_shas == {"a.pdf": "1"}
