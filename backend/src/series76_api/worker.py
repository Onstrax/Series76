"""Worker process entrypoint (Spec 3).

The API and worker are two processes built from the same image (Req 1.4). The
full claim/lease/fencing job-processing loop is implemented in Half B; this
module provides the runnable entrypoint seam (``python -m series76_api.worker``)
so the single image can start either process and ``docker compose`` resolves a
coherent worker service today.

It validates configuration and reports readiness without performing real LLM
calls (the provider and Spec 4 agent are faked); it exits cleanly so a
container orchestrator can supervise it.
"""

from __future__ import annotations

import sys

from series76_api.infrastructure.settings import get_settings


def main(argv: list[str] | None = None) -> int:
    """Entrypoint: load settings and report a ready-to-process worker.

    Returns a process exit code. The processing loop (claim/lease/fencing) is
    wired in Half B; here we only confirm the worker can boot from the
    environment-backed settings without requiring a reachable provider.
    """

    settings = get_settings()
    # Touch config so a misconfiguration surfaces at boot; never print secrets.
    _ = settings.database_url
    sys.stdout.write("series76 worker: configuration loaded; awaiting Half B job loop\n")
    return 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
