"""Infrastructure adapters for the Series 76 backend (Spec 3).

Async SQLAlchemy engine/session providers, the AES-256-GCM crypto adapter and
key lifecycle, password/token security primitives, settings, and the clock.
This is the only layer that touches external edges (database, OS CSPRNG,
``cryptography``/``argon2`` libraries).
"""

from __future__ import annotations
