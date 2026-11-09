"""Tool Set B — specialized LangChain tools (Task 12.1, Req 9.*).

Three thin adapters over the shared domain operations:

* ``get_part_details`` → :func:`series76_domain.operations.get_part.get_part`
* ``search_parts`` → :func:`series76_domain.operations.search_parts.search_parts`
* ``get_source_notes`` (conditional) →
  :func:`series76_domain.operations.get_source_notes.get_source_notes`

Each is a ``langchain_core`` :class:`StructuredTool` whose args schema is the
model-visible Pydantic model (server-injected inputs are **not** present).
No LLM or network call occurs here — the tools are pure adapters the agent
layer (Spec 4) will later mount. The A/B winner is deferred to Spec 6; **no**
winner is declared (see ``docs/adr/0002-tool-ab.md``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.tools import StructuredTool

from series76_domain.tools.context import RepositoryFactory, ToolContext, ToolResult
from series76_domain.tools.core import (
    run_get_part,
    run_search,
    run_source_notes,
    validate_get_part,
    validate_search,
    validate_source_notes,
)
from series76_domain.tools.schemas import GetPartInput, SearchInput, SourceNotesInput

# A context provider yields the server-injected context for the current call.
ContextProvider = Callable[[], ToolContext]


def build_set_b(
    context_provider: ContextProvider,
    repository_factory: RepositoryFactory,
    *,
    expose_source_notes: bool = True,
) -> dict[str, StructuredTool]:
    """Build the Set B tools bound to a server context provider and repository.

    Args:
        context_provider: yields the server-injected :class:`ToolContext`
            (edition, permissions, limits, trace id) — never a model value.
        repository_factory: yields the edition-pinned repository for a context.
        expose_source_notes: whether to register the conditional
            ``get_source_notes`` tool.

    Returns:
        A mapping of tool name to :class:`StructuredTool`.
    """

    def _get_part_details(**kwargs: Any) -> ToolResult:
        validated = validate_get_part(kwargs)
        return run_get_part(validated, context_provider(), repository_factory)

    def _search_parts(**kwargs: Any) -> ToolResult:
        validated = validate_search(kwargs)
        return run_search(validated, context_provider(), repository_factory)

    def _get_source_notes(**kwargs: Any) -> ToolResult:
        validated = validate_source_notes(kwargs)
        return run_source_notes(validated, context_provider(), repository_factory)

    tools: dict[str, StructuredTool] = {
        "get_part_details": StructuredTool.from_function(
            func=_get_part_details,
            name="get_part_details",
            description=(
                "Look up one Series 76 part by its exact part number and return "
                "its documented facts, each with a data status and evidence "
                "reference. Returns a typed failure code for a malformed or "
                "unlisted part number."
            ),
            args_schema=GetPartInput,
        ),
        "search_parts": StructuredTool.from_function(
            func=_search_parts,
            name="search_parts",
            description=(
                "Search Series 76 parts with a typed boolean filter over an "
                "allowlisted field set. Returns exact match totals, verified "
                "and preliminary sets, and a page cursor. Never accepts SQL."
            ),
            args_schema=SearchInput,
        ),
    }
    if expose_source_notes:
        tools["get_source_notes"] = StructuredTool.from_function(
            func=_get_source_notes,
            name="get_source_notes",
            description=(
                "Return the literal source notes for a part, each as a separate "
                "item with its exact covered-row scope and evidence. Returns a "
                "not-documented state when no such note exists."
            ),
            args_schema=SourceNotesInput,
        )
    return tools
