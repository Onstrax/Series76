"""Unit_Of_Work controlling the transaction boundary (Spec 3, Req 1.2).

The Use_Case opens a Unit_Of_Work, uses the repositories it exposes, and then
commits or rolls back. Repositories never commit on their own — only the
Unit_Of_Work does — so a single use case step is one atomic transaction.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession

from series76_api.infrastructure.repositories import (
    AuthSessionRepository,
    CheckpointRepository,
    ConversationRepository,
    DomainStateRepository,
    JobAttemptRepository,
    KeyMetadataRepository,
    LoginAttemptRepository,
    MessageRepository,
    PlanRepository,
    TokenVerifierRepository,
    ToolTraceRepository,
    TurnJobRepository,
    UserRepository,
)


class UnitOfWork:
    """An async Unit_Of_Work wrapping a session and its repositories.

    Usage::

        async with UnitOfWork(session) as uow:
            uow.users.add(...)
            await uow.commit()

    On exit without an explicit commit, the transaction is rolled back.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._committed = False
        self.users = UserRepository(session)
        self.auth_sessions = AuthSessionRepository(session)
        self.tokens = TokenVerifierRepository(session)
        self.login_attempts = LoginAttemptRepository(session)
        # Half B: conversation / jobs / plans / crypto-key / trace repositories.
        self.conversations = ConversationRepository(session)
        self.messages = MessageRepository(session)
        self.domain_states = DomainStateRepository(session)
        self.plans = PlanRepository(session)
        self.turn_jobs = TurnJobRepository(session)
        self.job_attempts = JobAttemptRepository(session)
        self.tool_traces = ToolTraceRepository(session)
        self.checkpoints = CheckpointRepository(session)
        self.key_metadata = KeyMetadataRepository(session)

    @property
    def session(self) -> AsyncSession:
        """The underlying async session (for use cases needing raw access)."""

        return self._session

    async def commit(self) -> None:
        """Commit the current transaction."""

        await self._session.commit()
        self._committed = True

    async def rollback(self) -> None:
        """Roll back the current transaction."""

        await self._session.rollback()

    async def flush(self) -> None:
        """Flush pending changes without committing (to surface conflicts)."""

        await self._session.flush()

    async def __aenter__(self) -> UnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None or not self._committed:
            await self._session.rollback()


__all__ = ["UnitOfWork"]
