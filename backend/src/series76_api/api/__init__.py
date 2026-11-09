"""API layer: FastAPI routers and Pydantic DTOs (Spec 3, transport edge).

Resolves identity/owner, validates DTOs, and maps application outcomes to HTTP
and the stable ``Error_Envelope``. Never executes model-generated SQL.
"""

from __future__ import annotations
