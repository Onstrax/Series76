"""Spec 3 crypto at-rest integration test (real PostgreSQL).

Reinforces Property 39 (sensitive data is ciphertext at rest) and Property 40
(the DEK is stored only wrapped; the KEK is never in the database) by writing a
real encrypted conversation title and a wrapped DEK into ``key_metadata`` and
then scanning the raw stored bytes of the whole database dump for the plaintext
and the KEK.

Named with ``spec3``/``crypto`` for selectability.
"""

from __future__ import annotations

import os
import uuid

import pytest
from alembic.config import Config
from sqlalchemy import text

from series76_api.domain.crypto import CIPHER_VERSION, AADContext, CryptoPurpose
from series76_api.domain.models import UserRole
from series76_api.infrastructure.crypto import Ciphertext, CryptoService
from series76_api.infrastructure.engine import create_app_engine, create_session_factory
from series76_api.infrastructure.orm import ConversationORM, KeyMetadataORM, UserORM
from series76_api.infrastructure.security import hash_password

pytestmark = pytest.mark.integration


async def test_spec3_crypto_ciphertext_at_rest_and_kek_absent(
    migrated_db: Config, postgres_url: str
) -> None:
    """A stored title is ciphertext; wrapped DEK != DEK; the KEK is nowhere in PG."""

    kek = os.urandom(32)
    crypto = CryptoService(kek)
    secret_title = "CONFIDENTIAL-TITLE-" + uuid.uuid4().hex

    engine = create_app_engine(postgres_url)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            owner = UserORM(
                id=uuid.uuid4(),
                email=f"owner-{uuid.uuid4().hex}@example.com",
                password_verifier=hash_password("Str0ng-Passw0rd!"),
                role=UserRole.USER,
                email_verified=False,
            )
            session.add(owner)
            await session.flush()

            session_id = uuid.uuid4()
            dek = crypto.generate_dek()
            ctx = AADContext(
                purpose=CryptoPurpose.CONVERSATION_TITLE,
                owner_id=owner.id,
                conversation_id=session_id,
                record_id=session_id,
            )
            title_ct = crypto.encrypt(dek, secret_title.encode("utf-8"), ctx).blob
            wrapped = crypto.wrap_dek(
                dek, owner_id=owner.id, conversation_id=session_id
            )

            session.add(
                ConversationORM(
                    session_id=session_id,
                    owner_id=owner.id,
                    title_ciphertext=title_ct,
                )
            )
            session.add(
                KeyMetadataORM(
                    key_id=uuid.uuid4(),
                    cipher_version=CIPHER_VERSION,
                    wrapped_dek=wrapped,
                    session_id=session_id,
                    owner_id=owner.id,
                )
            )
            await session.commit()

            # The wrapped DEK is not the raw DEK and does not contain the KEK.
            assert wrapped != dek
            assert dek not in wrapped
            assert kek not in wrapped

            # Decrypt-after-fetch round-trips with the correct key+AAD.
            fetched = await session.get(ConversationORM, session_id)
            assert fetched is not None and fetched.title_ciphertext is not None
            back = crypto.decrypt(dek, Ciphertext(fetched.title_ciphertext), ctx)
            assert back.decode("utf-8") == secret_title

        # Scan the raw stored bytes of the whole database for the plaintext
        # title and the KEK. Neither may appear anywhere at rest.
        async with engine.connect() as conn:
            # pg_catalog function to dump every bytea title + wrapped_dek as hex.
            title_rows = (
                await conn.execute(
                    text(
                        "SELECT encode(title_ciphertext, 'escape') "
                        "FROM conversation.conversations "
                        "WHERE title_ciphertext IS NOT NULL"
                    )
                )
            ).all()
            dek_rows = (
                await conn.execute(
                    text("SELECT wrapped_dek FROM execution.key_metadata")
                )
            ).all()

        title_bytes_blobs = [r[0] for r in title_rows]
        for blob in title_bytes_blobs:
            assert secret_title not in str(blob)

        for (wd,) in dek_rows:
            raw = bytes(wd)
            # The raw DEK and the KEK never appear in the stored wrapped bytes.
            assert kek not in raw
            assert dek not in raw
    finally:
        await engine.dispose()
