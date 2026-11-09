"""Password hashing and opaque-token security primitives (Spec 3, Req 2).

* Passwords are hashed with Argon2id using a per-password random salt of at
  least 128 bits — never a bare/unsalted fast hash (Property 1).
* Opaque access/refresh secrets come from the OS CSPRNG (>=128 bits, we use
  256), and only ``SHA-256(secret)`` is stored; comparison is constant time
  via :func:`hmac.compare_digest` (Property 2).

Raw secrets are returned once to the caller to present to the client and are
never persisted or logged.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2 import exceptions as argon2_exceptions
from argon2.low_level import Type

from series76_api.domain.auth import TOKEN_SECRET_BYTES, TOKEN_SEPARATOR

# A single hasher instance (argon2id variant with safe defaults; salt length is
# >=128-bit). ``argon2-cffi`` generates a fresh random salt per hash.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=4,
    hash_len=32,
    salt_len=16,  # 128-bit salt, per policy.
    type=Type.ID,  # Argon2id.
)


def hash_password(password: str) -> str:
    """Return an Argon2id PHC-string verifier for ``password``.

    Two calls with the same password return different strings because the salt
    is random per call (Property 1). The result is a one-way hash, not
    reversible ciphertext.
    """

    return _hasher.hash(password)


def verify_password(verifier: str, password: str) -> bool:
    """Verify ``password`` against a stored Argon2id verifier.

    Returns ``True`` only for the correct password; any mismatch returns
    ``False`` without raising (so login paths stay indistinguishable).
    """

    try:
        return _hasher.verify(verifier, password)
    except (
        argon2_exceptions.VerifyMismatchError,
        argon2_exceptions.VerificationError,
        argon2_exceptions.InvalidHashError,
    ):
        return False


def is_argon2id_verifier(verifier: str) -> bool:
    """Return whether a stored string is an Argon2id PHC hash (not a fast hash).

    Used by Property 1 to assert the verifier is never a bare/unsalted hash.
    """

    return verifier.startswith("$argon2id$")


@dataclass(frozen=True, slots=True)
class IssuedToken:
    """A freshly minted opaque token.

    ``public_id`` is a non-secret lookup handle; ``secret`` is the high-entropy
    CSPRNG value presented by the client; ``verifier`` is the only value stored.
    The full presentable string is ``<public_id>.<secret>``.
    """

    public_id: str
    secret: str
    verifier: str

    @property
    def presented(self) -> str:
        """The ``<public_id>.<secret>`` string the client presents as a Bearer."""

        return f"{self.public_id}{TOKEN_SEPARATOR}{self.secret}"


def _b64url_no_pad(raw: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def compute_token_verifier(secret: str) -> str:
    """Return the stored verifier ``SHA-256(secret)`` as lowercase hex."""

    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_token() -> IssuedToken:
    """Generate an opaque token: random public id + 256-bit CSPRNG secret.

    Only the SHA-256 verifier of the secret is stored; the raw secret is
    returned once and never persisted or logged (Property 2).
    """

    public_id = uuid.uuid4().hex
    secret = _b64url_no_pad(secrets.token_bytes(TOKEN_SECRET_BYTES))
    verifier = compute_token_verifier(secret)
    return IssuedToken(public_id=public_id, secret=secret, verifier=verifier)


def verify_token_secret(stored_verifier: str, presented_secret: str) -> bool:
    """Constant-time check that ``presented_secret`` matches ``stored_verifier``.

    Computes the SHA-256 of the presented secret and compares with
    :func:`hmac.compare_digest`, whose duration does not vary with the number
    of matching leading characters (Property 2).
    """

    candidate = compute_token_verifier(presented_secret)
    return hmac.compare_digest(candidate, stored_verifier)


__all__ = [
    "hash_password",
    "verify_password",
    "is_argon2id_verifier",
    "IssuedToken",
    "compute_token_verifier",
    "generate_token",
    "verify_token_secret",
]
