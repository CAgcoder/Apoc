"""AI panel server logic: comment-driven holistic document edit + grounded chat.

Both functions are server-authoritative and persist nothing — the caller saves
via the existing document/comment-status endpoints. Pinned to ``config.AI_EDIT_MODEL``
(DeepSeek), where reasoning shares the output-cap budget with the response, so the
edit returns the document as a plain-text body and a tiny trailing fenced-JSON block.
"""

from __future__ import annotations

import re
from typing import Any

from . import config, llm, prompts

# Mirror of the frontend tool-artifact stripper (markdown.ts): DeepSeek can leak
# its tool-call DSML syntax into prose. Delimiters: fullwidth bar (U+FF5C) and the
# object-replacement char (U+FFFC).
_DELIM = "[｜￼]"
_DSML_BLOCK = re.compile(
    rf"<{_DELIM}*\s*DSML{_DELIM}*\s*tool_calls>[\s\S]*?</{_DELIM}*\s*DSML{_DELIM}*\s*tool_calls>")
_DSML_TAG = re.compile(rf"</?{_DELIM}*\s*DSML[\s\S]*?>")
# A final fenced JSON block: the addressed-ids marker the edit must end with.
_TRAILING_JSON = re.compile(r"```json\s*(\{[\s\S]*?\})\s*```\s*$")


class EditTruncatedError(Exception):
    """The edit response is missing its trailing JSON marker — treat as truncated."""


def strip_tool_artifacts(src: str) -> str:
    out = _DSML_BLOCK.sub("", src or "")
    out = _DSML_TAG.sub("", out)
    out = out.replace("￼", "")
    return out.lstrip()


def split_edit_response(raw: str) -> tuple[str, list[str]]:
    """Split the model output into (document_body, addressed_ids).

    Raises EditTruncatedError when the required trailing JSON marker is absent —
    the signal that the response was cut off by the output cap.
    """
    text = (raw or "").strip()
    match = _TRAILING_JSON.search(text)
    if not match:
        raise EditTruncatedError("missing trailing addressed-ids JSON block")
    body = strip_tool_artifacts(text[: match.start()])
    # Unwrap an accidental ```markdown ... ``` wrapper around the whole body.
    fence = re.fullmatch(r"```(?:markdown|md)?\s*\n([\s\S]+?)\n```", body.strip())
    if fence:
        body = fence.group(1)
    try:
        parsed = llm.extract_json(match.group(1))
    except ValueError:
        parsed = {}
    addressed = parsed.get("addressed", []) if isinstance(parsed, dict) else []
    addressed = [str(x) for x in addressed] if isinstance(addressed, list) else []
    return body.strip(), addressed


def _format_comments(comments: list[dict[str, Any]]) -> str:
    lines = []
    for c in comments:
        where = c.get("anchor_slug") or (f"line {c['anchor_line']}" if c.get("anchor_line") else "general")
        lines.append(f"- [{c['id']}] ({c.get('role', 'stakeholder')} @ {where}) {c['body']}")
    return "\n".join(lines)


def run_ai_edit(*, document_md: str, comments: list[dict[str, Any]],
                instruction: str = "") -> tuple[str, list[str]]:
    """Holistic comment-driven rewrite. Returns (proposed_md, addressed_ids)."""
    user = (
        "Here is the current POC document:\n\n"
        f"{document_md}\n\n"
        "--- Accepted review comments to address ---\n"
        f"{_format_comments(comments) or '(none)'}\n"
    )
    if instruction.strip():
        user += f"\n--- Additional architect guidance ---\n{instruction.strip()}\n"
    raw, _ = llm.run_text(
        system=prompts.AI_EDIT_SYSTEM,
        user=user,
        model=config.AI_EDIT_MODEL,
        effort="high",
        deepseek_thinking="enabled",
        max_tokens=llm.DEEPSEEK_MAX_OUTPUT,
        json_mode=False,
    )
    return split_edit_response(raw)


def run_poc_chat(*, messages: list[dict[str, Any]], context: str) -> str:
    """One read-only Q&A turn grounded in the POC context. Returns the reply text."""
    system = f"{prompts.POC_CHAT_SYSTEM}\n\n--- POC context ---\n{context}"
    transcript = "\n".join(
        f"{'User' if m.get('role') == 'user' else 'Assistant'}: {m.get('content', '')}"
        for m in messages
    )
    reply, _ = llm.run_text(
        system=system,
        user=f"{transcript}\n\nAssistant:",
        model=config.AI_EDIT_MODEL,
        effort="medium",
        deepseek_thinking="enabled",
        max_tokens=2000,
        json_mode=False,
    )
    return strip_tool_artifacts(reply).strip()
