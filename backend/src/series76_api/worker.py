"""Worker process entrypoint + composition root (Spec 3, Req 1.4, 6).

The API and worker are two processes built from the same image. This module is
the worker's composition root: it builds the async engine/session factory
(connecting as ``app_writer``), the crypto service (holding the KEK), the clock,
and the faked agent seam, then runs the claim/lease/fencing drain loop via
:class:`WorkerService`.

No real LLM/provider call is ever made — the agent seam is faked (zero spend).
The processing loop uses short transactions and never holds a SQL transaction
across the (faked) model call (Property 27). The process starts even when a
provider would be unreachable; readiness is surfaced by the API's ``/ready``.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys

from series76_api.app import _build_crypto
from series76_api.application.agent_seam import AgentPort, FakeAgent
from series76_api.application.worker_service import WorkerService
from series76_api.infrastructure.clock import Clock, SystemClock
from series76_api.infrastructure.crypto import CryptoService
from series76_api.infrastructure.engine import (
    create_app_engine,
    create_session_factory,
)
from series76_api.infrastructure.settings import Settings, get_settings


def build_worker(
    settings: Settings,
    *,
    clock: Clock | None = None,
    crypto: CryptoService | None = None,
    agent: AgentPort | None = None,
) -> tuple[WorkerService, object]:
    """Build a :class:`WorkerService` and return it with its engine.

    The engine is returned so the caller can dispose it on shutdown. The agent
    seam defaults to the deterministic, zero-spend :class:`FakeAgent`.
    """

    resolved_clock = clock or SystemClock()
    resolved_crypto = crypto or _build_crypto(settings)
    resolved_agent: AgentPort = agent or FakeAgent()
    engine = create_app_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    worker = WorkerService(
        session_factory, resolved_clock, resolved_crypto, resolved_agent, settings
    )
    return worker, engine


async def _drain_forever(worker: WorkerService, *, poll_interval: float = 0.5) -> None:
    """Drain the queue continuously; sleep briefly when it is empty."""

    while True:  # pragma: no cover - long-running loop
        processed = await worker.process_one()
        if processed is None:
            await asyncio.sleep(poll_interval)


def main(argv: list[str] | None = None) -> int:
    """Entrypoint: build the worker from settings and run the drain loop.

    Returns a process exit code. Configuration is touched so a misconfiguration
    surfaces at boot; secrets are never printed.
    """

    settings = get_settings()
    _ = settings.database_url  # surface a bad URL early; never print it
    worker, engine = build_worker(settings)
    sys.stdout.write("series76 worker: configuration loaded; draining turn jobs\n")

    async def _run() -> None:
        try:
            await _drain_forever(worker)
        finally:
            await engine.dispose()  # type: ignore[attr-defined]

    with contextlib.suppress(KeyboardInterrupt):  # pragma: no cover - signals
        asyncio.run(_run())
    return 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
