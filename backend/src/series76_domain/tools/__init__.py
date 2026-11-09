"""Custom LangChain tool assemblies over the shared domain operations (Spec 2).

Two assemblies — Set B (specialized: ``get_part_details``, ``search_parts``,
conditional ``get_source_notes``) and Set A (generic ``query_parts``) — are
built over the **identical** domain operations, repository, validation,
server-injected merge, and sanitization. No winner is declared; the A/B
comparison is Spec 6 (see ``docs/adr/0002-tool-ab.md``). No LLM or network
call occurs in this layer.
"""

from __future__ import annotations

from series76_domain.tools.context import (
    RepositoryFactory,
    SanitizedFact,
    ToolContext,
    ToolResult,
)
from series76_domain.tools.core import ToolInputError
from series76_domain.tools.set_a import build_set_a
from series76_domain.tools.set_b import ContextProvider, build_set_b

__all__ = [
    "ContextProvider",
    "RepositoryFactory",
    "SanitizedFact",
    "ToolContext",
    "ToolInputError",
    "ToolResult",
    "build_set_a",
    "build_set_b",
]
