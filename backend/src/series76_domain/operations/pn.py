"""Part-number well-formedness (``INVALID_PN`` vs ``PART_NOT_LISTED``).

A *malformed* PN is rejected with ``INVALID_PN`` before any catalog lookup; a
*well-formed but absent* PN yields ``PART_NOT_LISTED`` (Property 4). The
canonical format is deliberately permissive — an alphanumeric token with
optional separators ``-`` / ``.`` / ``/`` — because the printed PN is never
decoded for meaning (design § Data Models).
"""

from __future__ import annotations

import re

# A canonical PN is a non-empty token of letters/digits with internal
# separators; it must start and end with an alphanumeric and never contain
# whitespace or SQL-significant characters.
_CANONICAL_PN = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9]|[-./](?=[A-Za-z0-9])){0,63}$")


def is_well_formed_pn(candidate: str) -> bool:
    """Return ``True`` iff ``candidate`` is a structurally valid canonical PN."""

    if not isinstance(candidate, str):
        return False
    return bool(_CANONICAL_PN.match(candidate))


def normalize_pn(candidate: str) -> str:
    """Normalize a PN for lookup (trim, upper-case).

    Normalization never changes identity semantics; the printed form is kept
    separately by the catalog.
    """

    return candidate.strip().upper()
