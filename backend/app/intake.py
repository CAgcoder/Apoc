"""Conversational requirement intake.

A stateless "intake agent": given the running message history it returns the
next turn — a question, optional clickable option cards each with a one-line
advantage, and (once enough has been gathered) a structured ``brief`` plus the
project title, ready to hand to the generation pipeline unchanged.

The frontend owns the conversation and posts the full history each turn, so this
module never touches the database; it just shapes the model's JSON into a turn
the UI can render safely.
"""

from __future__ import annotations

import uuid
from typing import Any

from . import config, llm, prompts
from .artifacts import ArtifactStore

# The exact brief keys the generation pipeline already consumes
# (see generation._brief_text). The intake agent must fill these on completion.
BRIEF_KEYS = [
    "business_goal",
    "scale",
    "availability",
    "compliance",
    "cloud",
    "budget_sensitivity",
    "timeline",
    "constraints",
]


def _clean(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def normalize_turn(raw: Any) -> dict[str, Any]:
    """Coerce a (possibly messy) model dict into a well-formed turn.

    Tolerant by design: missing keys get safe defaults, options may be dicts or
    bare strings, and the brief — when present — is forced onto exactly the keys
    the pipeline expects.
    """
    raw = raw if isinstance(raw, dict) else {}

    options: list[dict[str, str]] = []
    for opt in raw.get("options") or []:
        if isinstance(opt, dict) and opt.get("label"):
            options.append({"label": str(opt["label"]), "advantage": str(opt.get("advantage", "") or "")})
        elif isinstance(opt, str) and opt.strip():
            options.append({"label": opt.strip(), "advantage": ""})

    brief = raw.get("brief")
    if isinstance(brief, dict):
        brief = {k: str(brief.get(k, "") or "") for k in BRIEF_KEYS}
    else:
        brief = None

    return {
        "message": str(raw.get("message", "") or ""),
        "options": options,
        "allow_free_text": bool(raw.get("allow_free_text", True)),
        "done": bool(raw.get("done")),
        "brief": brief,
        "title": _clean(raw.get("title")),
        "client_name": _clean(raw.get("client_name")),
        "consulting_org": _clean(raw.get("consulting_org")),
        "requirements_detail": str(raw.get("requirements_detail", "") or "").strip(),
    }


def _format_history(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return (
            "The conversation has not started yet. Greet the user in one short "
            "sentence and ask your FIRST question — start by asking what they want "
            "to build and what to name the project. Then produce the turn JSON."
        )
    lines: list[str] = []
    for msg in messages:
        who = "User" if msg.get("role") == "user" else "You (intake agent)"
        lines.append(f"{who}: {msg.get('content', '')}")
    lines.append("\nProduce the next turn as a single JSON object.")
    return "\n".join(lines)


def run_intake_turn(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Call the model with the running history and return one normalized turn."""
    store = ArtifactStore(config.RUNS_DIR / "intake_chat", f"intake_chat_{uuid.uuid4().hex[:12]}")
    raw_text, sources = llm.run_text(
        system=prompts.INTAKE_SYSTEM,
        user=_format_history(messages),
        model=config.MODEL,
        max_tokens=2000,
        json_mode=True,
    )
    store.write_text("turn.raw", raw_text)
    meta = {
        "model": config.MODEL,
        "json_mode": True,
        "tool_loop": False,
        "web_search": False,
        "raw_chars": len(raw_text),
        "source_count": len(sources),
    }
    try:
        raw = llm.extract_json(raw_text)
    except Exception as exc:
        store.write_json("turn.meta", {**meta, "parse_error": str(exc)})
        raise
    store.write_json("turn.meta", {**meta, "parsed": True})
    return normalize_turn(raw)
