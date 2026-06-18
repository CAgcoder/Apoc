"""Research orchestration for APoc generation."""

from __future__ import annotations

import json
from typing import Any, Callable

from . import config, llm, models, prompts, search

MAX_QUERIES = 3
RawSink = Callable[[str, str, dict[str, Any]], None]


def _deepseek_reasoning_kwargs(model: str) -> dict[str, str]:
    if models.provider_for_model(model) != "deepseek":
        return {}
    return {"deepseek_thinking": "enabled", "effort": "max"}


def run_research(
    brief_text: str, topic: str, model: str | None = None, raw_sink: RawSink | None = None
) -> tuple[str, list[dict[str, Any]]]:
    """Produce a grounded digest and citation metadata for a project brief."""
    model = model or config.RESEARCH_MODEL
    if config.ANTHROPIC_NATIVE_SEARCH and models.provider_for_model(model) == "anthropic":
        return llm.run_text(
            system=prompts.RESEARCH_SYSTEM,
            user=brief_text,
            model=model,
            web_search=True,
            max_tokens=4000,
            **_deepseek_reasoning_kwargs(model),
        )

    queries = _generate_queries(brief_text, topic, model, raw_sink=raw_sink)
    fragments, sources = search.gather(queries, k=config.SEARCH_TOPK)
    if not fragments:
        return llm.run_text(
            system=prompts.RESEARCH_SYSTEM,
            user=brief_text,
            model=model,
            web_search=True,
            max_tokens=4000,
            **_deepseek_reasoning_kwargs(model),
        )

    digest, _ = llm.run_text(
        system=prompts.RESEARCH_GROUNDED_SYSTEM,
        user=_grounded_user_prompt(brief_text, topic, fragments),
        model=model,
        web_search=False,
        max_tokens=4000,
        **_deepseek_reasoning_kwargs(model),
    )
    return digest, sources


def _generate_queries(
    brief_text: str, topic: str, model: str | None = None, raw_sink: RawSink | None = None
) -> list[str]:
    model = model or config.RESEARCH_MODEL
    system = (
        "You generate web search queries for architecture proof-of-concept research. "
        "Output ONLY a JSON object like {\"queries\": [\"...\"]}. Include 3 concise "
        "queries targeting current reference architectures, well-architected guidance, "
        "security/compliance, reliability, and cost practices."
    )
    user = f"Project topic: {topic}\n\nRequirement brief:\n{brief_text}"
    try:
        raw_text, sources = llm.run_text(
            system=system,
            user=user,
            model=model,
            max_tokens=500,
            json_mode=True,
            **_deepseek_reasoning_kwargs(model),
        )
        if raw_sink:
            raw_sink("research_queries", raw_text, {
                "model": model,
                "json_mode": True,
                "tool_loop": False,
                "web_search": False,
                "source_count": len(sources),
            })
        data = llm.extract_json(raw_text)
        queries = data.get("queries", []) if isinstance(data, dict) else []
    except Exception:
        queries = []
    clean = []
    seen: set[str] = set()
    for query in queries:
        q = " ".join(str(query).split())
        if q and q.lower() not in seen:
            seen.add(q.lower())
            clean.append(q)
        if len(clean) >= MAX_QUERIES:
            break
    return clean or _fallback_queries(brief_text, topic)


def _fallback_queries(brief_text: str, topic: str) -> list[str]:
    topic = " ".join((topic or brief_text.splitlines()[0] if brief_text else "architecture POC").split())[:100]
    return [
        f"{topic} reference architecture best practices",
        f"{topic} well-architected security reliability cost guidance",
        f"{topic} compliance data residency architecture failure modes",
    ]


def _grounded_user_prompt(brief_text: str, topic: str, fragments: list[dict[str, Any]]) -> str:
    blocks = []
    for fragment in fragments:
        meta = {
            "source_id": fragment.get("source_id", ""),
            "title": fragment.get("title", ""),
            "url": fragment.get("url", ""),
            "date": fragment.get("date", ""),
            "sitename": fragment.get("sitename", ""),
        }
        blocks.append(
            f"### [{fragment.get('source_id')}] {fragment.get('title')}\n"
            f"Metadata: {json.dumps(meta, ensure_ascii=False)}\n\n"
            f"{fragment.get('content_md', '')}"
        )
    return (
        f"Project topic: {topic}\n\n"
        f"Requirement brief:\n{brief_text}\n\n"
        "--- Grounding fragments. Use only these facts and cite source_id in square brackets. ---\n"
        + "\n\n".join(blocks)
    )
