"""Optional held-out, blind, position-controlled pairwise judge (spec §5).

A win counts only if the same design wins in BOTH orders; otherwise it is a tie
(position bias). Contestant names never enter the prompt — the judge sees only
"Design 1" / "Design 2".
"""

from __future__ import annotations

import json
from typing import Any

from app import llm

_SYS = (
    "You compare two software architecture designs and pick the stronger one on "
    "completeness, trade-off transparency, technical soundness, and actionability. "
    "Answer with a single JSON object {\"winner\": \"first\"|\"second\"}."
)


def _ask(system: str, user: str, model: str) -> str:
    raw, _ = llm.run_text(system=system, user=user, model=model, max_tokens=300, json_mode=True)
    try:
        return str(llm.extract_json(raw).get("winner", "")).strip().lower()
    except Exception:
        return ""


def _prompt(first: dict[str, Any], second: dict[str, Any]) -> str:
    return (
        "Design 1:\n" + json.dumps(first, ensure_ascii=False)
        + "\n\nDesign 2:\n" + json.dumps(second, ensure_ascii=False)
    )


def pairwise(
    a: dict[str, Any], b: dict[str, Any], *, model: str, a_name: str, b_name: str
) -> dict[str, Any]:
    # order 1: a first; order 2: b first
    w1 = _ask(_SYS, _prompt(a, b), model)   # "first" => a wins
    w2 = _ask(_SYS, _prompt(b, a), model)   # "first" => b wins
    a_wins = (w1 == "first") and (w2 == "second")
    b_wins = (w1 == "second") and (w2 == "first")
    if a_wins:
        return {"winner": a_name, "consistent": True}
    if b_wins:
        return {"winner": b_name, "consistent": True}
    return {"winner": "tie", "consistent": False}
