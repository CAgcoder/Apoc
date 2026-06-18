"""Objective, deterministic metrics over a single design dict.

No LLM. These are the core deliverable: they cannot be dismissed as judge bias.
"""

from __future__ import annotations

from typing import Any

_SECTIONS = [
    "title", "executive_summary", "context", "requirements_mapping", "components",
    "data_flows", "tech_stack", "nfrs", "decisions", "risks", "cost_estimate",
    "open_questions",
]
_BOILERPLATE = {"", "n/a", "na", "none", "-", "—"}


def _is_substantive(text: Any) -> bool:
    """An `alternatives` string that actually names a rejected option."""
    s = (text or "").strip() if isinstance(text, str) else ""
    return len(s) >= 12 and s.lower() not in _BOILERPLATE


def alternatives_density(design: dict[str, Any]) -> dict[str, float]:
    decisions = design.get("decisions") or []
    decisions = [d for d in decisions if isinstance(d, dict)]
    count = sum(1 for d in decisions if _is_substantive(d.get("alternatives")))
    ratio = count / len(decisions) if decisions else 0.0
    return {"count": count, "ratio": ratio}


def risk_specificity(design: dict[str, Any]) -> int:
    risks = design.get("risks") or []
    return sum(
        1 for r in risks
        if isinstance(r, dict) and (r.get("title") or "").strip()
        and (r.get("mitigation") or "").strip()
    )


def structural_completeness(design: dict[str, Any]) -> bool:
    for key in _SECTIONS:
        val = design.get(key)
        if val is None or (isinstance(val, (str, list, dict)) and len(val) == 0):
            return False
    return True


def objective_scores(design: dict[str, Any]) -> dict[str, Any]:
    alt = alternatives_density(design)
    return {
        "alternatives_count": alt["count"],
        "alternatives_ratio": alt["ratio"],
        "risk_specificity": risk_specificity(design),
        "structural_complete": structural_completeness(design),
    }
