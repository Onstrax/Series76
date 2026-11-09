"""Pure cryptographic policy and AAD binding for the Series 76 backend (Spec 3).

This module owns the *policy* of the application-layer AES-256-GCM scheme —
key/nonce sizes, the format version, and the canonical construction of the
Additional Authenticated Data (AAD) that binds every ciphertext to its context.
It performs no actual encryption (that adapter lives in ``infrastructure``) so
it stays free of the ``cryptography`` dependency and remains purely testable.

AAD binds five fields (design: Token and crypto record shapes, Property 38):

    purpose ‖ owner ‖ conversation ‖ record_id ‖ format_version

Changing any field changes the AAD, so decryption under a different context
fails the GCM tag check and returns no plaintext (fail closed).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum

# AES-256 key size in bytes (256-bit).
DEK_KEY_BYTES = 32
# GCM nonce size in bytes (96-bit, unique per key — design/Property 38).
GCM_NONCE_BYTES = 12
# Current on-disk cipher format version; recorded in key_metadata.cipher_version.
CIPHER_VERSION = 1
# A canonical, unambiguous separator for AAD field joining. The 0x1f unit
# separator cannot appear in the UTF-8 encodings of the structured fields used
# here (UUIDs, enum labels, small ints), so the join is injective.
_AAD_SEP = b"\x1f"


class CryptoPurpose(str, Enum):
    """The ``purpose`` component of the AAD, one per sensitive record kind.

    Binding the purpose prevents a ciphertext minted for one column from being
    accepted when decrypted for another.
    """

    CONVERSATION_TITLE = "conversation.title"
    MESSAGE_CONTENT = "message.content"
    MESSAGE_BLOCKS = "message.blocks"
    DOMAIN_STATE = "domain.state"
    PLAN_CONTENT = "plan.content"
    TOOL_TRACE = "tool.trace"
    CHECKPOINT = "checkpoint.blob"
    JOB_INPUT = "job.input"


@dataclass(frozen=True, slots=True)
class AADContext:
    """The five-field context bound into every AES-256-GCM operation.

    ``record_id`` is the stable identifier of the record being encrypted (for
    example a ``message_id``); ``format_version`` defaults to the current
    :data:`CIPHER_VERSION`.
    """

    purpose: CryptoPurpose
    owner_id: uuid.UUID
    conversation_id: uuid.UUID
    record_id: uuid.UUID
    format_version: int = CIPHER_VERSION

    def to_bytes(self) -> bytes:
        """Serialize the context to the canonical AAD byte string.

        The encoding is deterministic and injective: the same context always
        yields the same bytes, and two distinct contexts never collide.
        """

        parts: tuple[bytes, ...] = (
            self.purpose.value.encode("utf-8"),
            self.owner_id.bytes,
            self.conversation_id.bytes,
            self.record_id.bytes,
            str(self.format_version).encode("ascii"),
        )
        return _AAD_SEP.join(parts)


__all__ = [
    "DEK_KEY_BYTES",
    "GCM_NONCE_BYTES",
    "CIPHER_VERSION",
    "CryptoPurpose",
    "AADContext",
]
