"""Pure authentication invariants for the Series 76 backend (Spec 3).

Email canonicalization, password strength policy, opaque-token shape/parsing,
and the login lockout policy. Pure and side-effect free: the Argon2id hasher,
SHA-256 verifier computation, and CSPRNG secret generation live in
``infrastructure`` (they need the ``argon2``/``hashlib``/``secrets`` adapters);
this module owns the rules those adapters must honor.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import ValidationError

# Email length bounds (design: AuthService, Req 2).
EMAIL_MIN_LEN = 3
EMAIL_MAX_LEN = 254
# Password length bounds.
PASSWORD_MIN_LEN = 12
PASSWORD_MAX_LEN = 128
# Minimum opaque-token secret entropy in bytes (>=128 bits; we prefer 256).
TOKEN_SECRET_MIN_BYTES = 16
TOKEN_SECRET_BYTES = 32
# Minimum Argon2id salt size in bytes (>=128-bit).
ARGON2_SALT_MIN_BYTES = 16

# Login lockout policy (Property 5).
LOGIN_MAX_FAILURES = 5
LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60

# The separator between the public id and the secret in a presented token.
TOKEN_SEPARATOR = "."


def canonicalize_email(raw: str) -> str:
    """Return the canonical form of an email for uniqueness comparison.

    Trims surrounding whitespace and lowercases. Canonicalization is what the
    unique index is built on, so two inputs differing only in case or padding
    map to the same account.
    """

    return raw.strip().lower()


def validate_email(raw: str) -> str:
    """Validate and return the canonical email, or raise ``ValidationError``.

    The error message is generic and never reveals whether an account exists
    (Property 4) — existence conflicts are handled separately and generically.
    """

    canonical = canonicalize_email(raw)
    if not (EMAIL_MIN_LEN <= len(canonical) <= EMAIL_MAX_LEN):
        raise ValidationError("Invalid email.")
    # Minimal structural check: exactly one '@' with non-empty local/domain and
    # a dot in the domain. Full RFC validation is out of scope; this rejects
    # obviously malformed input without enabling enumeration.
    local, sep, domain = canonical.partition("@")
    if not sep or not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValidationError("Invalid email.")
    return canonical


def password_strength_ok(password: str) -> bool:
    """Return whether a password meets the strength policy.

    Policy: within the length bounds and containing at least three of the four
    character classes (lowercase, uppercase, digit, symbol). This is a pure
    predicate so it can be property-tested directly.
    """

    if not (PASSWORD_MIN_LEN <= len(password) <= PASSWORD_MAX_LEN):
        return False
    has_lower = any(c.islower() for c in password)
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_symbol = any(not c.isalnum() for c in password)
    classes = sum((has_lower, has_upper, has_digit, has_symbol))
    return classes >= 3


def validate_password(password: str) -> str:
    """Validate a password against the policy, or raise ``ValidationError``."""

    if not password_strength_ok(password):
        raise ValidationError("Password does not meet the strength policy.")
    return password


@dataclass(frozen=True, slots=True)
class PresentedToken:
    """A parsed ``<public_id>.<secret>`` bearer token."""

    public_id: str
    secret: str


def parse_bearer_token(raw: str) -> PresentedToken:
    """Parse a presented opaque token of the form ``<public_id>.<secret>``.

    Raises ``ValidationError`` for a malformed token. A malformed token must
    never be mistaken for a valid one; it is rejected before any DB lookup.
    """

    candidate = raw.strip()
    if candidate.lower().startswith("bearer "):
        candidate = candidate[len("bearer ") :].strip()
    public_id, sep, secret = candidate.partition(TOKEN_SEPARATOR)
    if not sep or not public_id or not secret:
        raise ValidationError("Malformed token.")
    return PresentedToken(public_id=public_id, secret=secret)


def is_locked_out(recent_failure_count: int) -> bool:
    """Return whether the lockout threshold has been reached within the window.

    The caller supplies the number of consecutive failures already recorded in
    the current :data:`LOGIN_FAILURE_WINDOW_SECONDS` window; lockout engages at
    :data:`LOGIN_MAX_FAILURES` (the 6th attempt is rejected).
    """

    return recent_failure_count >= LOGIN_MAX_FAILURES


__all__ = [
    "EMAIL_MIN_LEN",
    "EMAIL_MAX_LEN",
    "PASSWORD_MIN_LEN",
    "PASSWORD_MAX_LEN",
    "TOKEN_SECRET_MIN_BYTES",
    "TOKEN_SECRET_BYTES",
    "ARGON2_SALT_MIN_BYTES",
    "LOGIN_MAX_FAILURES",
    "LOGIN_FAILURE_WINDOW_SECONDS",
    "TOKEN_SEPARATOR",
    "canonicalize_email",
    "validate_email",
    "password_strength_ok",
    "validate_password",
    "PresentedToken",
    "parse_bearer_token",
    "is_locked_out",
]
