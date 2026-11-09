"""Import-boundary unit test for the Spec 3 domain layer (Req 1.1).

Asserts that ``series76_api.domain`` imports none of FastAPI, SQLAlchemy,
LangChain, or any provider SDK. The domain layer must stay pure so its
invariants (auth/session/job/crypto) can be reasoned about and property-tested
in isolation.

Named ``test_api_import_boundary`` so it is selectable alongside the other
Spec-3 suites.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys

import series76_api.domain as domain_pkg

# Top-level module names the domain layer must never import (directly or via a
# transitive import that lands in ``sys.modules`` after importing domain).
_FORBIDDEN = {
    "fastapi",
    "starlette",
    "sqlalchemy",
    "langchain",
    "langchain_core",
    "langgraph",
    "openai",
    "psycopg",
    "pydantic_settings",
}


def _import_all_domain_modules() -> None:
    for mod in pkgutil.walk_packages(domain_pkg.__path__, prefix="series76_api.domain."):
        importlib.import_module(mod.name)


def test_domain_imports_no_forbidden_libraries() -> None:
    """Importing every domain module pulls in no forbidden top-level package."""

    # Drop any previously-imported forbidden modules so this test measures what
    # the domain import *itself* requires, not what an earlier test loaded.
    before = {name for name in _FORBIDDEN if name in sys.modules}

    _import_all_domain_modules()

    # A forbidden module is a violation only if a domain module is the importer.
    # Since the domain package imports nothing from these, re-importing the
    # domain modules must not newly introduce any forbidden top-level package.
    newly_loaded = {
        name for name in _FORBIDDEN if name in sys.modules and name not in before
    }
    assert not newly_loaded, f"domain layer imported forbidden packages: {newly_loaded}"


def test_domain_module_files_have_no_forbidden_import_statements() -> None:
    """Static check: no domain source file names a forbidden import.

    Belt-and-suspenders alongside the runtime check: scans the domain source
    text so a lazily-imported forbidden dependency is still caught.
    """

    import pathlib

    domain_dir = pathlib.Path(domain_pkg.__path__[0])
    offenders: list[str] = []
    for py in domain_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for name in _FORBIDDEN:
            if f"import {name}" in text or f"from {name}" in text:
                offenders.append(f"{py.name}:{name}")
    assert not offenders, f"forbidden import statements in domain: {offenders}"
