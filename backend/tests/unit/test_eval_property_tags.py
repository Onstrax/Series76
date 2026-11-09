"""Every Spec 6 property (1-44) is implemented by exactly one tagged test."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TAG = re.compile(r"(?://|#) Feature: evaluation-and-reproducibility, Property (\d+): (.+)$", re.M)


def test_all_44_properties_tagged_once_with_design_titles() -> None:
    design = (REPO / ".kiro/specs/evaluation-and-reproducibility/design.md").read_text("utf-8")
    titles = {int(n): t.strip() for n, t in re.findall(r"^### Property (\d+): (.+)$", design, re.M)}
    assert sorted(titles) == list(range(1, 45))
    sources = list((REPO / "backend" / "tests").rglob("test_*.py"))
    sources += list((REPO / "android" / "app" / "src").rglob("*Test.kt"))
    found: dict[int, list[str]] = {}
    for path in sources:
        for n, title in TAG.findall(path.read_text(encoding="utf-8")):
            found.setdefault(int(n), []).append(title.strip())
            assert title.strip() == titles[int(n)], f"P{n} tag title differs in {path.name}"
    assert sorted(found) == list(range(1, 45)), f"missing: {set(range(1, 45)) - set(found)}"
    assert all(len(v) == 1 for v in found.values()), {k: v for k, v in found.items() if len(v) > 1}
