"""The domain repository port exposes no raw-SQL surface (Req 1.1, 1.2).

Introspect the :class:`TypedRepository` protocol and the PostgreSQL adapter to
assert there is no ``execute(sql: str)`` escape hatch and no public method
accepts a SQL-string parameter.
"""

from __future__ import annotations

import inspect

from series76_domain.repository import pg_adapter
from series76_domain.repository.pg_adapter import PostgresTypedRepository
from series76_domain.repository.port import TypedRepository

_FORBIDDEN_PARAM_NAMES = {"sql", "query", "statement", "stmt", "raw", "expr"}
_EXPECTED_PORT_METHODS = {
    "find_part_number",
    "list_part_numbers",
    "configurations_for",
    "service_performance_for",
    "unqualified_performance_for",
    "operating_conditions_for",
    "measurements_for",
    "notes_for_part",
}


def _public_methods(cls: type) -> dict[str, object]:
    return {
        name: member
        for name, member in inspect.getmembers(cls, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def test_port_exposes_only_typed_query_methods() -> None:
    methods = set(_public_methods(TypedRepository))
    # The protocol's query surface is exactly the typed, edition-pinned methods.
    assert methods >= _EXPECTED_PORT_METHODS
    assert "execute" not in methods


def test_no_public_method_takes_a_sql_string() -> None:
    for name, method in _public_methods(PostgresTypedRepository).items():
        sig = inspect.signature(method)
        for param_name in sig.parameters:
            assert param_name.lower() not in _FORBIDDEN_PARAM_NAMES, (name, param_name)


def test_adapter_has_no_execute_sql_method() -> None:
    assert not hasattr(PostgresTypedRepository, "execute")
    # The only text() use is the fixed, parameter-free `SET ROLE` statement
    # binding the least-privilege reader role.
    source = inspect.getsource(pg_adapter)
    assert "SET ROLE" in source
    assert "runtime_reader_role" in source
    # No driver-level raw SQL execution of caller input.
    assert "exec_driver_sql" not in source
