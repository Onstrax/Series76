"""Unit test: the repository exposes only typed queries, no raw-SQL path (Task 4.3).

Introspect :class:`CatalogRepository` and assert that:

  * every public method is one of the known typed, edition-scoped queries;
  * no public method accepts a caller-supplied SQL string parameter (no
    ``sql``/``query``/``statement`` text parameter, no ``str``-annotated SQL
    escape hatch);
  * the source of the repository module never calls ``text(...)`` or
    ``Connection.exec_driver_sql`` with caller input — reads are built from the
    ORM ``select`` construct only.

Requirements: 7.4
"""

from __future__ import annotations

import inspect
import re

from series76_data.db import repository
from series76_data.db.repository import CatalogRepository

# The complete sanctioned public surface (edition-scoped, typed).
EXPECTED_PUBLIC_METHODS = {
    "get_active_edition",
    "get_edition",
    "get_part_numbers",
    "get_configurations",
    "get_service_performance",
    "get_unqualified_performance",
    "get_operating_conditions",
    "get_measurements",
}

# Parameter names that would signal a free-form SQL escape hatch.
_FORBIDDEN_PARAM_NAMES = {"sql", "query", "statement", "stmt", "raw", "text", "expr"}


def _public_methods(cls: type) -> dict[str, object]:
    return {
        name: member
        for name, member in inspect.getmembers(cls, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def test_repository_public_surface_is_exactly_the_typed_methods() -> None:
    methods = _public_methods(CatalogRepository)
    assert set(methods) == EXPECTED_PUBLIC_METHODS


def test_no_public_method_accepts_a_sql_string_parameter() -> None:
    for name, method in _public_methods(CatalogRepository).items():
        sig = inspect.signature(method)
        for param_name, param in sig.parameters.items():
            if param_name in ("self",):
                continue
            # No parameter may be named like a SQL escape hatch.
            assert param_name.lower() not in _FORBIDDEN_PARAM_NAMES, (name, param_name)
            # No parameter may be annotated as a bare ``str`` SQL text: the only
            # str-ish inputs here would be identifiers, and this repo uses typed
            # ids (uuid.UUID / int) exclusively.
            annotation = str(param.annotation)
            assert "str" not in annotation.lower(), (name, param_name, annotation)


def test_repository_source_has_no_raw_sql_execution() -> None:
    source = inspect.getsource(repository)
    # No free-form text() SQL, no driver-level raw SQL execution.
    assert "exec_driver_sql" not in source
    assert not re.search(r"\btext\s*\(", source), "repository must not build text() SQL"
    # Reads go exclusively through the typed select() construct.
    assert "select(" in source
