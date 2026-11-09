"""Application layer: use cases + Unit_Of_Work (Spec 3).

Use cases authorize owner+role, control the transaction boundary (the
Unit_Of_Work; repositories never self-commit), and orchestrate auth and the
authorization guard. Half A implements auth and authorization use cases and
leaves seams for conversation/jobs/plans use cases (Half B).
"""

from __future__ import annotations
