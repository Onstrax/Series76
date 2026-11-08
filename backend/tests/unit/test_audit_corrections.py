"""Unit + property tests for correction staleness (Task 11).

Property 6 pure predicate: a correction whose referenced document hash differs
from the current source hash is stale and must not be applied. The DB-side of
Property 6 (the record is not written and the edition is unchanged) is exercised
in the integration suite.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from series76_data.audit.workflow import is_correction_stale

_hex = st.text(
    alphabet="0123456789abcdef", min_size=8, max_size=64
).filter(lambda s: len(s) >= 8)


# Feature: data-and-ingestion, Property 6: Stale corrections are not applied. For
# any correction whose referenced document hash differs from the current source
# document hash, it is reported stale and not applied.
@given(referenced=_hex, current=_hex)
def test_property_6_stale_correction_detected(referenced: str, current: str) -> None:
    stale = is_correction_stale(referenced, current)
    # Stale iff the hashes are not equal (case-insensitive).
    assert stale == (referenced.lower() != current.lower())


def test_matching_hash_is_not_stale_case_insensitive() -> None:
    assert not is_correction_stale("ABCDEF12", "abcdef12")
    assert is_correction_stale("abcdef12", "abcdef99")
