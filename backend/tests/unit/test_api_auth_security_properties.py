"""Property tests for password hashing and opaque-token verifiers (P1, P2).

Pure (no database): exercises the Argon2id hashing and the SHA-256
constant-time token verifier directly. Each property is one Hypothesis test,
>=100 iterations via the shared ``series76`` profile.
"""

from __future__ import annotations

import hashlib

from hypothesis import given
from hypothesis import strategies as st

from series76_api.infrastructure.security import (
    compute_token_verifier,
    generate_token,
    hash_password,
    is_argon2id_verifier,
    verify_password,
    verify_token_secret,
)

# Reasonable password alphabet (printable, no control chars) within policy len.
_passwords = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
    min_size=12,
    max_size=64,
)


# Feature: backend-api-auth-jobs-crypto, Property 1: Passwords are stored
# irreversibly with Argon2id.
@given(password=_passwords)
def test_property_1_argon2id_irreversible_salted(password: str) -> None:
    """Argon2id verifier: salted, not a bare hash, distinct per account, verifies."""

    v1 = hash_password(password)
    v2 = hash_password(password)

    # Argon2id PHC string (carries the >=128-bit random salt).
    assert is_argon2id_verifier(v1)
    assert is_argon2id_verifier(v2)
    # Identical passwords -> different stored verifiers (per-password salt).
    assert v1 != v2
    # Never equal to a bare/unsalted fast hash of the password.
    bare = hashlib.sha256(password.encode("utf-8")).hexdigest()
    assert v1 != bare
    assert bare not in v1
    # Verification succeeds only for the correct password.
    assert verify_password(v1, password)
    assert not verify_password(v1, password + "x")


# Feature: backend-api-auth-jobs-crypto, Property 2: Opaque token verifiers are
# SHA-256 and compared in constant time.
@given(data=st.data())
def test_property_2_token_sha256_verifier_constant_time(data: st.DataObject) -> None:
    """Stored verifier is SHA-256(secret); correct secret authorizes, near-miss does not."""

    token = generate_token()

    # The stored verifier is exactly SHA-256(secret) hex — never the raw secret.
    assert token.verifier == hashlib.sha256(token.secret.encode("utf-8")).hexdigest()
    assert token.secret not in token.verifier
    assert token.verifier == compute_token_verifier(token.secret)

    # The correct secret verifies via the constant-time primitive.
    assert verify_token_secret(token.verifier, token.secret)

    # Any near-miss secret fails (flip/append/truncate).
    assert not verify_token_secret(token.verifier, token.secret + "x")
    if len(token.secret) > 1:
        assert not verify_token_secret(token.verifier, token.secret[:-1])
    flipped = ("A" if token.secret[0] != "A" else "B") + token.secret[1:]
    assert not verify_token_secret(token.verifier, flipped)

    # A random unrelated secret does not authorize.
    other = data.draw(st.text(min_size=1, max_size=64))
    if compute_token_verifier(other) != token.verifier:
        assert not verify_token_secret(token.verifier, other)
