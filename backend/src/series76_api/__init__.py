"""Series 76 Technical Assistant — backend API (Spec 3).

Feature-First + light-hexagonal modular monolith:

* :mod:`series76_api.api` — FastAPI routers and Pydantic DTOs (transport edge).
* :mod:`series76_api.application` — use cases + Unit_Of_Work (transaction boundary).
* :mod:`series76_api.domain` — pure auth/session/job/crypto invariants; imports
  none of FastAPI, SQLAlchemy, LangChain, or any provider SDK.
* :mod:`series76_api.infrastructure` — async SQLAlchemy repositories, the crypto
  adapter, settings, engine, and clock (external adapters).

This package implements the first half of Spec 3: skeleton/config, Alembic
migrations + roles, the crypto module, authentication, and the authorization
guard. The conversation/jobs/plans/delete/trace/error-envelope wiring is a
separate later task; clean seams are left for it.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
