"""``Claim`` objects verified before any visible output (Req 8.3-8.5).

A claim names *which* facts it is about (part numbers + comparison context) and
never carries a number of its own: the verifier reads the numbers from the
verified figure set. Non-numeric claims (a service is supported, an enclosure
is documented, an efficiency statement) are verified as well — a false claim
is removed even when it contains no digits.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class ClaimKind(str, Enum):
    """The verifiable assertion kinds."""

    HAS_MORE_TORQUE = "has_more_torque"
    IS_FASTER = "is_faster"
    SAME_FREQUENCY = "same_frequency"
    NO_RESULT = "no_result"
    SUPPORTS_SERVICE = "supports_service"
    HAS_ENCLOSURE = "has_enclosure"
    IS_LISTED = "is_listed"
    LOWER_ENERGY_CONSUMPTION = "lower_energy_consumption"

    @property
    def is_numeric(self) -> bool:
        """True iff verification compares documented magnitudes."""
        return self in (ClaimKind.HAS_MORE_TORQUE, ClaimKind.IS_FASTER)


class Verdict(str, Enum):
    """A claim's deterministic verification outcome."""

    VERIFIED = "VERIFIED"
    REFUTED = "REFUTED"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True, slots=True)
class Claim:
    """A proposed assertion about products.

    Attributes:
        kind: the assertion kind.
        subject_pn: the part the claim is about.
        object_pn: the part it is compared against (comparative claims).
        service / frequency_hz / supply / unit: the comparison context the
            claim is asserted under — verification requires both facts to share
            exactly this context.
        value_text: the non-numeric object of the claim (a service name, an
            enclosure label).
        required: whether the turn cannot be answered without this claim.
    """

    kind: ClaimKind
    subject_pn: str | None = None
    object_pn: str | None = None
    service: str | None = None
    frequency_hz: Decimal | None = None
    supply: str | None = None
    unit: str | None = None
    value_text: str | None = None
    required: bool = False


@dataclass(frozen=True, slots=True)
class ClaimResult:
    """A claim with its verdict and a secret-free reason."""

    claim: Claim
    verdict: Verdict
    reason: str

    @property
    def visible(self) -> bool:
        """Only a VERIFIED claim may appear in any visible output."""
        return self.verdict is Verdict.VERIFIED
