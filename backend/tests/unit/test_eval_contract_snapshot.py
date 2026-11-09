"""Spec 6 Test_Level 5: the backend contract matches its versioned snapshot."""

from __future__ import annotations

import json

from series76_eval.contract import MANDATORY, SNAPSHOT, current_openapi, render


def test_contract_matches_committed_snapshot() -> None:
    assert SNAPSHOT.exists(), "run: python -m series76_eval contract-snapshot --write"
    assert SNAPSHOT.read_text(encoding="utf-8") == render(current_openapi()), (
        "contract drift: review the change, then regenerate the snapshot"
    )


def test_mandatory_endpoints_are_in_the_contract() -> None:
    paths = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["paths"]
    for method, path in MANDATORY:
        assert method in paths.get(path, {}), f"{method.upper()} {path} missing"
    body = paths["/api/conversation"]["post"]
    assert "requestBody" in body and "200" in body["responses"]
