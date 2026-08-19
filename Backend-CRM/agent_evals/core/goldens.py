"""Goldens loader — a suite of test cases from a simple YAML/JSON file.

File shape::

    connector: orbit            # which connectors/<name>.py runs these
    cases:
      - id: unique-case-id
        description: what this case proves
        review: pending | approved     # human domain-expert sign-off marker
        input: { ...verbatim connector input... }
        expected_tools: [list_my_tasks]     # optional -> tool-use metric
        checks:                              # deterministic layer (primary)
          - {type: action_taken, command: list_my_tasks, require_ok: true}
        judge:                               # optional G-Eval (fuzzy cases only)
          criteria: plain-English criteria for the LLM judge
          threshold: 0.7
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class GoldenCase:
    id: str
    input: Dict[str, Any]
    description: str = ""
    review: str = "pending"
    expected_tools: List[str] = field(default_factory=list)
    checks: List[dict] = field(default_factory=list)
    judge: Optional[dict] = None


@dataclass
class GoldenSuite:
    connector: str
    cases: List[GoldenCase]
    path: str = ""


def load_suite(path: str) -> GoldenSuite:
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        import yaml

        data = yaml.safe_load(raw)
    else:
        data = json.loads(raw)

    if not isinstance(data, dict) or "cases" not in data:
        raise ValueError(f"{path}: goldens file must be a mapping with a 'cases' list")

    cases: List[GoldenCase] = []
    seen: set = set()
    for i, c in enumerate(data["cases"]):
        if not isinstance(c, dict) or not c.get("id"):
            raise ValueError(f"{path}: case #{i} is missing an 'id'")
        if c["id"] in seen:
            raise ValueError(f"{path}: duplicate case id '{c['id']}'")
        seen.add(c["id"])
        if not isinstance(c.get("input"), dict):
            raise ValueError(f"{path}: case '{c['id']}' needs a mapping 'input'")
        judge = c.get("judge")
        if judge is not None and not judge.get("criteria"):
            raise ValueError(f"{path}: case '{c['id']}' judge block needs 'criteria'")
        cases.append(GoldenCase(
            id=str(c["id"]),
            input=c["input"],
            description=str(c.get("description") or ""),
            review=str(c.get("review") or "pending"),
            expected_tools=[str(t) for t in (c.get("expected_tools") or [])],
            checks=list(c.get("checks") or []),
            judge=judge,
        ))
    return GoldenSuite(connector=str(data.get("connector") or ""), cases=cases, path=str(p))
