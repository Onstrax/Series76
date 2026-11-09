"""Pure domain layer for the Series 76 backend (Spec 3).

This package contains only pure rules and invariants for authentication,
sessions, jobs, and cryptography. It imports **none** of FastAPI, SQLAlchemy,
LangChain, or any provider SDK (Requirement 1.1); the import-boundary unit test
enforces this. Everything here is deterministic and side-effect free so it can
be reasoned about and property-tested in isolation.
"""

from __future__ import annotations
