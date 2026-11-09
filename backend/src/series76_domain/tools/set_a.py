"""Tool Set A — generic baseline LangChain tool (Task 13.1, Req 9.*).

A single generic ``query_parts`` tool with a discriminated
``{ op: GET | SEARCH, ... }`` payload that routes GET to the **same**
``get_part`` path and SEARCH to the **same** ``search_parts`` path used by
Set B. Set A and Set B share the identical repository, validation,
server-injected merge, sanitization, and
:class:`~series76_domain.model.enums.SemanticFailureCode` behavior — they
differ only in the model-visible surface shape.

**No winner is declared.** The empirical A/B comparison of ergonomics is an
experiment deferred to Spec 6 (see ``docs/adr/0002-tool-ab.md``). No LLM or
network call occurs here.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool

from series76_domain.tools.context import RepositoryFactory, ToolResult
from series76_domain.tools.core import run_query_parts, validate_query_parts
from series76_domain.tools.schemas import QueryPartsInput
from series76_domain.tools.set_b import ContextProvider


def build_set_a(
    context_provider: ContextProvider,
    repository_factory: RepositoryFactory,
) -> dict[str, StructuredTool]:
    """Build the Set A generic tool bound to a server context and repository.

    Returns a mapping with the single ``query_parts`` tool.
    """

    def _query_parts(**kwargs: Any) -> ToolResult:
        validated = validate_query_parts(kwargs)
        return run_query_parts(validated, context_provider(), repository_factory)

    return {
        "query_parts": StructuredTool.from_function(
            func=_query_parts,
            name="query_parts",
            description=(
                "Generic Series 76 catalog query. Set op='GET' with a "
                "part_number to look up one part, or op='SEARCH' with a typed "
                "filter_ast to search. Routes to the same deterministic core as "
                "the specialized tools. Never accepts SQL."
            ),
            args_schema=QueryPartsInput,
        )
    }
