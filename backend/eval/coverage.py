"""Requirement coverage against a frozen, human-reviewed checklist.

The checklist is ground truth (extracted once, frozen). Only the per-item
"addressed?" decision uses the held-out judge model.
"""

from __future__ import annotations

from typing import Any

from app import llm

_SYS = (
    "You check whether a software design addresses a specific requirement. "
    "Answer with a single JSON object {\"addressed\": true|false}. "
    "Mark addressed only if the design's requirements mapping concretely covers it."
)


def _mapping_text(design: dict[str, Any]) -> str:
    rows = design.get("requirements_mapping") or []
    return "\n".join(
        f"- {r.get('requirement', '')}: {r.get('how_addressed', '')}"
        for r in rows if isinstance(r, dict)
    )


def _judge_item(item: str, mapping_text: str, model: str) -> bool:
    user = f"Requirement:\n{item}\n\nDesign requirements mapping:\n{mapping_text}"
    raw, _ = llm.run_text(system=_SYS, user=user, model=model, max_tokens=200, json_mode=True)
    try:
        return bool(llm.extract_json(raw).get("addressed"))
    except Exception:
        return False


def score(design: dict[str, Any], checklist: list[str], *, model: str) -> dict[str, Any]:
    total = len(checklist)
    if total == 0:
        return {"addressed": 0, "total": 0, "coverage": 0.0}
    mapping_text = _mapping_text(design)
    addressed = sum(1 for item in checklist if _judge_item(item, mapping_text, model))
    return {"addressed": addressed, "total": total, "coverage": addressed / total}
