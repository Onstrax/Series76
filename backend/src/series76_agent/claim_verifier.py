"""Deterministic ``ClaimVerifier`` (Req 8.3-8.5, 8.10).

A claim is checked against the verified figure set only. Comparative claims
require exactly one figure per part under an *identical* service / frequency /
supply / unit context and both values ``AVAILABLE``; anything else is
``UNVERIFIABLE``. Non-numeric claims are verified too, so a false assertion is
removed even when it contains no digits. An efficiency / lower-consumption
claim is never verifiable from this source (FLA under different supplies does
not prove efficiency — F2 §4).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from series76_agent.domain.claims import Claim, ClaimKind, ClaimResult, Verdict
from series76_agent.domain.figures import BoundFigure, VerifiedFigureSet, same_service

_TORQUE_KEY_BY_UNIT = {"in-lbs": "torque_inlbs", "Nm": "torque_nm"}


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """All claim verdicts plus the turn-level outcome."""

    results: tuple[ClaimResult, ...]
    insufficient_information: bool

    @property
    def visible(self) -> tuple[ClaimResult, ...]:
        """Only VERIFIED claims may be shown."""
        return tuple(r for r in self.results if r.visible)


class ClaimVerifier:
    """Verifies claims deterministically; performs no I/O and no LLM call."""

    def verify(self, claim: Claim, figures: VerifiedFigureSet) -> ClaimResult:
        """Return the verdict for one claim."""

        kind = claim.kind
        if kind is ClaimKind.HAS_MORE_TORQUE:
            key = _TORQUE_KEY_BY_UNIT.get(claim.unit or "")
            if key is None:
                return _r(claim, Verdict.UNVERIFIABLE, "torque claim needs a documented unit")
            return self._compare(claim, figures, key, larger_is_true=True)
        if kind is ClaimKind.IS_FASTER:
            # Operating speed is a stroke time: a smaller time is faster.
            return self._compare(claim, figures, "operating_speed", larger_is_true=False)
        if kind is ClaimKind.SAME_FREQUENCY:
            return self._same_frequency(claim, figures)
        if kind is ClaimKind.NO_RESULT:
            if not figures.searched or "total_matches" not in figures.counts:
                return _r(claim, Verdict.UNVERIFIABLE, "no search was executed")
            ok = figures.counts["total_matches"] == 0
            return _r(claim, Verdict.VERIFIED if ok else Verdict.REFUTED, "search total")
        if kind is ClaimKind.SUPPORTS_SERVICE:
            if claim.subject_pn is None or claim.value_text is None:
                return _r(claim, Verdict.UNVERIFIABLE, "missing subject or service")
            if claim.subject_pn not in figures.listed_parts:
                return _r(claim, Verdict.UNVERIFIABLE, "part facts not retrieved")
            services = figures.services.get(claim.subject_pn, set())
            ok = any(same_service(s, claim.value_text) for s in services)
            return _r(claim, Verdict.VERIFIED if ok else Verdict.REFUTED, "documented services")
        if kind is ClaimKind.HAS_ENCLOSURE:
            if claim.subject_pn is None or claim.value_text is None:
                return _r(claim, Verdict.UNVERIFIABLE, "missing subject or enclosure")
            if claim.subject_pn not in figures.listed_parts:
                return _r(claim, Verdict.UNVERIFIABLE, "part facts not retrieved")
            encl = figures.enclosures.get(claim.subject_pn, set())
            ok = any(same_service(e, claim.value_text) for e in encl)
            return _r(claim, Verdict.VERIFIED if ok else Verdict.REFUTED, "documented enclosure")
        if kind is ClaimKind.IS_LISTED:
            if claim.subject_pn is None:
                return _r(claim, Verdict.UNVERIFIABLE, "missing subject")
            ok = claim.subject_pn in figures.listed_parts
            return _r(claim, Verdict.VERIFIED if ok else Verdict.UNVERIFIABLE, "listing")
        # LOWER_ENERGY_CONSUMPTION and any future kind: no deterministic check.
        return _r(claim, Verdict.UNVERIFIABLE, "no documented basis for this assertion")

    def verify_all(self, claims: Iterable[Claim], figures: VerifiedFigureSet) -> VerificationReport:
        """Verify every claim; a required unverified claim flags the turn."""

        results = tuple(self.verify(c, figures) for c in claims)
        insufficient = any(r.claim.required and not r.visible for r in results)
        return VerificationReport(results=results, insufficient_information=insufficient)

    # --- helpers -------------------------------------------------------------

    def _candidates(
        self, claim: Claim, figures: VerifiedFigureSet, pn: str, key: str
    ) -> list[BoundFigure]:
        return figures.select(
            pn,
            key,
            service=claim.service,
            frequency_hz=claim.frequency_hz,
            supply=claim.supply,
        )

    def _compare(
        self,
        claim: Claim,
        figures: VerifiedFigureSet,
        key: str,
        *,
        larger_is_true: bool,
    ) -> ClaimResult:
        if claim.subject_pn is None or claim.object_pn is None:
            return _r(claim, Verdict.UNVERIFIABLE, "comparative claim needs two parts")
        if claim.subject_pn == claim.object_pn:
            return _r(claim, Verdict.UNVERIFIABLE, "a part is not compared with itself")
        left = self._candidates(claim, figures, claim.subject_pn, key)
        right = self._candidates(claim, figures, claim.object_pn, key)
        if len(left) != 1 or len(right) != 1:
            return _r(claim, Verdict.UNVERIFIABLE, "no single fact under the stated context")
        a, b = left[0], right[0]
        if a.context_key != b.context_key:
            return _r(claim, Verdict.UNVERIFIABLE, "facts are not under an identical context")
        if a.figure.direct is None or b.figure.direct is None:
            return _r(claim, Verdict.UNVERIFIABLE, "a compared value is N/A or not documented")
        va, vb = a.figure.direct.value, b.figure.direct.value
        assert va is not None and vb is not None
        holds = va > vb if larger_is_true else va < vb
        return _r(claim, Verdict.VERIFIED if holds else Verdict.REFUTED, "documented values")

    def _same_frequency(self, claim: Claim, figures: VerifiedFigureSet) -> ClaimResult:
        if claim.subject_pn is None or claim.object_pn is None:
            return _r(claim, Verdict.UNVERIFIABLE, "frequency claim needs two parts")
        fa = figures.frequencies.get(claim.subject_pn)
        fb = figures.frequencies.get(claim.object_pn)
        if not fa or not fb:
            return _r(claim, Verdict.UNVERIFIABLE, "no explicit documented frequency")
        if claim.frequency_hz is not None:
            ok = claim.frequency_hz in fa and claim.frequency_hz in fb
        else:
            ok = fa == fb
        return _r(claim, Verdict.VERIFIED if ok else Verdict.REFUTED, "documented frequencies")


def _r(claim: Claim, verdict: Verdict, reason: str) -> ClaimResult:
    return ClaimResult(claim=claim, verdict=verdict, reason=reason)
