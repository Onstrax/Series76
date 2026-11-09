"""AES-256-GCM crypto adapter and DEK/KEK lifecycle (Spec 3, Req 9).

This adapter encrypts sensitive content *before* it reaches PostgreSQL under a
per-conversation Data Encryption Key (DEK). Each DEK is itself stored only
*wrapped* by an external Key-Encryption-Key (KEK) that never touches the
database. Everything fails closed: a GCM tag mismatch, legacy plaintext where
ciphertext is required, or an unavailable KEK / unwrappable DEK returns no data
and no key material (Properties 38–41). Secrets are never logged (Property 44).

Design references:
- 96-bit nonce unique per key; AAD binds purpose‖owner‖conversation‖record‖version.
- DEK wrapped by KEK; persist only wrapped_dek + key_metadata(key_id, cipher_version).
- Crypto-shred = delete the DEK so ciphertext becomes unrecoverable.
"""

from __future__ import annotations

import base64
import os
import uuid
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from series76_api.domain.crypto import (
    CIPHER_VERSION,
    DEK_KEY_BYTES,
    GCM_NONCE_BYTES,
    AADContext,
    CryptoPurpose,
)
from series76_api.domain.errors import DecryptionError, KeyUnavailableError

# A sentinel purpose for wrapping the DEK itself under the KEK. The DEK wrap AAD
# binds the owner + conversation so a wrapped DEK cannot be replayed elsewhere.
_DEK_WRAP_PURPOSE = b"dek.wrap.v1"


@dataclass(frozen=True, slots=True)
class Ciphertext:
    """A self-describing AES-256-GCM record: version‖nonce‖ct+tag.

    The stored ``blob`` contains everything needed to decrypt *except* the key
    and the AAD (both supplied at decrypt time), and never contains plaintext.
    """

    blob: bytes

    @property
    def cipher_version(self) -> int:
        """The cipher format version recorded in the first byte."""

        return self.blob[0] if self.blob else 0


def _encrypt(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    """AES-256-GCM encrypt, returning ``version(1) ‖ nonce(12) ‖ ct+tag``.

    A fresh 96-bit nonce is drawn from the OS CSPRNG for every call; with a
    random 96-bit nonce per key the probability of reuse is negligible, so the
    uniqueness invariant (Property 38) holds across operations under a key.
    """

    if len(key) != DEK_KEY_BYTES:
        # Never attempt encryption with a wrong-sized key; fail closed.
        raise KeyUnavailableError("Encryption key unavailable.")
    nonce = os.urandom(GCM_NONCE_BYTES)
    ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    return bytes([CIPHER_VERSION]) + nonce + ct


def _decrypt(key: bytes, blob: bytes, aad: bytes) -> bytes:
    """AES-256-GCM decrypt a ``version‖nonce‖ct+tag`` blob, or fail closed.

    Raises :class:`DecryptionError` on a tag mismatch, a malformed/legacy blob,
    or an unexpected version — returning no plaintext and no key material.
    """

    if len(key) != DEK_KEY_BYTES:
        raise KeyUnavailableError("Decryption key unavailable.")
    if len(blob) < 1 + GCM_NONCE_BYTES + 16:
        # Too short to be a valid record (incl. the 16-byte GCM tag): this is
        # legacy plaintext or corruption where ciphertext is required.
        raise DecryptionError("Ciphertext required but legacy/invalid bytes found.")
    version = blob[0]
    if version != CIPHER_VERSION:
        raise DecryptionError("Unsupported cipher version.")
    nonce = blob[1 : 1 + GCM_NONCE_BYTES]
    ct = blob[1 + GCM_NONCE_BYTES :]
    try:
        return AESGCM(key).decrypt(nonce, ct, aad)
    except InvalidTag as exc:
        raise DecryptionError("Authentication tag verification failed.") from exc


class CryptoService:
    """Application-layer crypto: DEK generation, KEK wrap/unwrap, encrypt/decrypt.

    The KEK is provided once at construction (from settings/env, never stored).
    If no KEK is configured the service still constructs, but any key operation
    fails closed with :class:`KeyUnavailableError`.
    """

    def __init__(self, kek: bytes | None) -> None:
        if kek is not None and len(kek) != DEK_KEY_BYTES:
            raise KeyUnavailableError("KEK must be 32 bytes (AES-256).")
        self._kek = kek

    @classmethod
    def from_base64_kek(cls, kek_base64: str) -> CryptoService:
        """Build a service from a base64-encoded 32-byte KEK.

        An empty or malformed value yields a service with no KEK; all key
        operations then fail closed (Property 41, KEK-unavailable).
        """

        if not kek_base64:
            return cls(None)
        try:
            raw = base64.b64decode(kek_base64, validate=True)
        except Exception:  # noqa: BLE001 — never leak base64 decode detail
            return cls(None)
        if len(raw) != DEK_KEY_BYTES:
            return cls(None)
        return cls(raw)

    # --- DEK lifecycle ----------------------------------------------------

    @staticmethod
    def generate_dek() -> bytes:
        """Generate a fresh 256-bit DEK from the OS CSPRNG."""

        return os.urandom(DEK_KEY_BYTES)

    def _dek_wrap_aad(self, owner_id: uuid.UUID, conversation_id: uuid.UUID) -> bytes:
        return b"\x1f".join((_DEK_WRAP_PURPOSE, owner_id.bytes, conversation_id.bytes))

    def wrap_dek(
        self, dek: bytes, *, owner_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> bytes:
        """Wrap (encrypt) a DEK under the KEK, binding owner+conversation.

        Returns the wrapped-DEK ciphertext to persist in
        ``key_metadata.wrapped_dek``. The raw DEK and the KEK are never stored.
        """

        if self._kek is None:
            raise KeyUnavailableError("KEK unavailable; cannot wrap DEK.")
        aad = self._dek_wrap_aad(owner_id, conversation_id)
        return _encrypt(self._kek, dek, aad)

    def unwrap_dek(
        self, wrapped_dek: bytes, *, owner_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> bytes:
        """Unwrap a persisted wrapped DEK, or fail closed.

        Raises :class:`KeyUnavailableError` when the KEK is absent and
        :class:`DecryptionError` when the wrapped DEK does not authenticate
        (e.g. tampered, or belongs to a different owner/conversation).
        """

        if self._kek is None:
            raise KeyUnavailableError("KEK unavailable; cannot unwrap DEK.")
        aad = self._dek_wrap_aad(owner_id, conversation_id)
        return _decrypt(self._kek, wrapped_dek, aad)

    # --- Record encryption ------------------------------------------------

    def encrypt(self, dek: bytes, plaintext: bytes, context: AADContext) -> Ciphertext:
        """Encrypt ``plaintext`` under ``dek`` with the five-field AAD bound."""

        return Ciphertext(_encrypt(dek, plaintext, context.to_bytes()))

    def decrypt(self, dek: bytes, ciphertext: Ciphertext, context: AADContext) -> bytes:
        """Decrypt a record, returning plaintext only on tag-verify success.

        Decryption under a different AAD context (any of the five fields) fails
        the tag check and raises :class:`DecryptionError` (Property 38/41).
        """

        return _decrypt(dek, ciphertext.blob, context.to_bytes())

    @property
    def has_kek(self) -> bool:
        """Whether a KEK is configured (used by readiness, never logs it)."""

        return self._kek is not None


__all__ = ["Ciphertext", "CryptoService", "AADContext", "CryptoPurpose"]
