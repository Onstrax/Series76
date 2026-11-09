"""Property tests for the Spec 3 crypto module (Properties 38-41, 44).

Each property is a single Hypothesis test, >=100 iterations (the shared
``series76`` profile), tagged for traceability. These exercise the crypto
primitive, DEK/KEK lifecycle, fail-closed behavior, and secret redaction
without a database; the at-rest DB-dump scan (Property 39) is reinforced by an
integration test.
"""

from __future__ import annotations

import os
import uuid

from hypothesis import given
from hypothesis import strategies as st

from series76_api.domain.crypto import (
    CIPHER_VERSION,
    DEK_KEY_BYTES,
    GCM_NONCE_BYTES,
    AADContext,
    CryptoPurpose,
)
from series76_api.domain.errors import DecryptionError, KeyUnavailableError
from series76_api.infrastructure.crypto import CryptoService
from series76_api.infrastructure.safe_logging import (
    REDACTED,
    redact_mapping,
    safe_headers,
)

_PURPOSES = list(CryptoPurpose)


def _service_with_kek() -> CryptoService:
    return CryptoService(os.urandom(DEK_KEY_BYTES))


def _aad(
    purpose: CryptoPurpose, owner: uuid.UUID, conv: uuid.UUID, rec: uuid.UUID
) -> AADContext:
    return AADContext(
        purpose=purpose, owner_id=owner, conversation_id=conv, record_id=rec
    )


# Feature: backend-api-auth-jobs-crypto, Property 38: Encryption round-trips and
# binds AAD, with unique nonces.
@given(
    plaintext=st.binary(min_size=0, max_size=512),
    purpose=st.sampled_from(_PURPOSES),
)
def test_property_38_roundtrip_aad_binding_unique_nonce(
    plaintext: bytes, purpose: CryptoPurpose
) -> None:
    """Round-trip under the correct key+AAD; a different AAD fails; nonces unique."""

    svc = _service_with_kek()
    dek = svc.generate_dek()
    owner, conv, rec = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ctx = _aad(purpose, owner, conv, rec)

    ct1 = svc.encrypt(dek, plaintext, ctx)
    ct2 = svc.encrypt(dek, plaintext, ctx)

    # Round-trip returns the original plaintext.
    assert svc.decrypt(dek, ct1, ctx) == plaintext
    # 96-bit nonce, and two encryptions of the same plaintext use distinct
    # nonces (hence distinct ciphertext blobs) — uniqueness per key.
    assert ct1.cipher_version == CIPHER_VERSION
    nonce1 = ct1.blob[1 : 1 + GCM_NONCE_BYTES]
    nonce2 = ct2.blob[1 : 1 + GCM_NONCE_BYTES]
    assert len(nonce1) == GCM_NONCE_BYTES
    assert nonce1 != nonce2
    assert ct1.blob != ct2.blob

    # Changing ANY of the five AAD fields fails decryption (no plaintext).
    wrong_contexts = [
        _aad(
            _PURPOSES[(_PURPOSES.index(purpose) + 1) % len(_PURPOSES)], owner, conv, rec
        ),
        _aad(purpose, uuid.uuid4(), conv, rec),
        _aad(purpose, owner, uuid.uuid4(), rec),
        _aad(purpose, owner, conv, uuid.uuid4()),
        AADContext(purpose, owner, conv, rec, format_version=CIPHER_VERSION + 1),
    ]
    for wrong in wrong_contexts:
        try:
            svc.decrypt(dek, ct1, wrong)
            raise AssertionError("decryption under a different AAD must fail")
        except DecryptionError:
            pass


# Feature: backend-api-auth-jobs-crypto, Property 39: Sensitive data is
# ciphertext at rest; only the allowlist is cleartext.
@given(plaintext=st.text(min_size=8, max_size=256))
def test_property_39_ciphertext_at_rest_no_plaintext(plaintext: str) -> None:
    """The stored bytes never contain the full plaintext substring.

    AES-GCM ciphertext is indistinguishable from random bytes, so a single
    short byte could coincidentally appear; the invariant is that the sensitive
    *payload* is not stored in the clear. We assert the full plaintext (>=8
    chars, i.e. >=64 bits, making a coincidental contiguous match negligible)
    does not appear in the stored bytes.
    """

    svc = _service_with_kek()
    dek = svc.generate_dek()
    ctx = _aad(CryptoPurpose.MESSAGE_CONTENT, uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    raw = plaintext.encode("utf-8")
    stored = svc.encrypt(dek, raw, ctx).blob
    # The ciphertext body is not the plaintext and does not contain it...
    assert stored != raw
    assert raw not in stored
    # ...and the stored blob length differs from the plaintext (version+nonce+tag
    # overhead), another signal that it is not a verbatim cleartext copy.
    assert len(stored) == 1 + GCM_NONCE_BYTES + len(raw) + 16


# Feature: backend-api-auth-jobs-crypto, Property 40: Each DEK is stored only
# wrapped and the KEK is never in the database.
@given(data=st.data())
def test_property_40_dek_only_wrapped_kek_never_present(data: st.DataObject) -> None:
    """The persisted wrapped DEK is not the raw DEK and does not contain the KEK."""

    kek = os.urandom(DEK_KEY_BYTES)
    svc = CryptoService(kek)
    dek = svc.generate_dek()
    owner, conv = uuid.uuid4(), uuid.uuid4()

    wrapped = svc.wrap_dek(dek, owner_id=owner, conversation_id=conv)

    # What is persisted is ciphertext, not the DEK, and never the KEK.
    assert wrapped != dek
    assert dek not in wrapped
    assert kek not in wrapped
    # Unwrapping with the KEK recovers the DEK exactly.
    assert svc.unwrap_dek(wrapped, owner_id=owner, conversation_id=conv) == dek
    # A wrapped DEK is bound to its owner+conversation (cannot be replayed).
    other = data.draw(st.uuids())
    try:
        svc.unwrap_dek(wrapped, owner_id=other, conversation_id=conv)
        raise AssertionError("wrapped DEK must not unwrap under a different owner")
    except DecryptionError:
        pass


# Feature: backend-api-auth-jobs-crypto, Property 41: Decryption fails closed on
# tamper, legacy plaintext, or key unavailability.
@given(
    plaintext=st.binary(min_size=1, max_size=256),
    flip_index=st.integers(min_value=0, max_value=1_000_000),
)
def test_property_41_fail_closed(plaintext: bytes, flip_index: int) -> None:
    """Tampered ciphertext, legacy plaintext, and absent KEK all fail closed."""

    svc = _service_with_kek()
    dek = svc.generate_dek()
    ctx = _aad(CryptoPurpose.PLAN_CONTENT, uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    ct = svc.encrypt(dek, plaintext, ctx)

    # (a) Tamper: flip one byte of the stored blob -> tag verification fails.
    idx = flip_index % len(ct.blob)
    tampered = bytearray(ct.blob)
    tampered[idx] ^= 0x01
    from series76_api.infrastructure.crypto import Ciphertext

    try:
        svc.decrypt(dek, Ciphertext(bytes(tampered)), ctx)
        raise AssertionError("tampered ciphertext must fail closed")
    except DecryptionError:
        pass

    # (b) Legacy plaintext where ciphertext is required (bytes that are not a
    # valid version‖nonce‖ct+tag record).
    try:
        svc.decrypt(dek, Ciphertext(b"legacy-plaintext"), ctx)
        raise AssertionError("legacy plaintext must fail closed")
    except DecryptionError:
        pass

    # (c) KEK unavailable -> no key material, fail closed.
    no_kek = CryptoService(None)
    try:
        no_kek.unwrap_dek(
            b"\x00" * 64, owner_id=uuid.uuid4(), conversation_id=uuid.uuid4()
        )
        raise AssertionError("absent KEK must fail closed")
    except KeyUnavailableError:
        pass


# Feature: backend-api-auth-jobs-crypto, Property 44: Secrets never appear in
# logs or traces.
@given(secret_seed=st.binary(min_size=8, max_size=48))
def test_property_44_secrets_redacted_in_logs(secret_seed: bytes) -> None:
    """Secret-bearing fields and headers are redacted before any log output.

    A unique, high-entropy marker is embedded in every secret-bearing field; a
    correct redactor leaves that marker nowhere in the serialized output while
    preserving non-secret values verbatim.
    """

    marker = "SECRET_" + secret_seed.hex()
    record = {
        "event": "login",
        "password": marker,
        "access_token": marker,
        "kek_base64": marker,
        "nested": {"refresh_token": marker, "safe": "visible-value"},
        "items": [{"dek": marker}, {"ok": "fine-value"}],
    }
    redacted = redact_mapping(record)

    # No secret marker survives anywhere, at any nesting depth.
    assert marker not in repr(redacted)
    assert redacted["password"] == REDACTED
    assert redacted["access_token"] == REDACTED
    assert redacted["kek_base64"] == REDACTED
    assert redacted["nested"]["refresh_token"] == REDACTED
    assert redacted["nested"]["safe"] == "visible-value"
    assert redacted["items"][0]["dek"] == REDACTED
    assert redacted["items"][1]["ok"] == "fine-value"

    headers = {"Authorization": f"Bearer {marker}", "X-Trace": "visible"}
    safe = safe_headers(headers)
    assert safe["Authorization"] == REDACTED
    assert safe["X-Trace"] == "visible"
    assert marker not in repr(safe)
