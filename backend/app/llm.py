"""Model access with a small provider abstraction.

Two providers:

* ``anthropic`` — ``claude-opus-4-8`` with adaptive thinking, effort, and the
  server-side ``web_search`` tool (citations come for free).
* ``deepseek`` — OpenAI-compatible ``/chat/completions`` over httpx. DeepSeek has
  no server-side web search; the legacy DuckDuckGo title-search path remains as a
  final fallback, while default research grounding lives in ``app.research`` /
  ``app.search``. JSON mode + a truncation-repair pass keep structured steps
  parseable under DeepSeek's 8K output cap.

Public API is provider-agnostic: :func:`run_text` and :func:`run_json`.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from html import unescape
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from . import config, models

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}
DEEPSEEK_MAX_OUTPUT = 16300


# --- Anthropic --------------------------------------------------------------

@lru_cache(maxsize=1)
def _anthropic_client():
    import anthropic

    return anthropic.Anthropic()


def _anthropic_sources(content: list[Any]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for block in content:
        btype = getattr(block, "type", "")
        if btype == "web_search_tool_result":
            for item in getattr(block, "content", []) or []:
                url = getattr(item, "url", None)
                if url:
                    sources.append({"title": getattr(item, "title", None) or url, "url": url})
        elif btype == "text":
            for cit in getattr(block, "citations", None) or []:
                url = getattr(cit, "url", None)
                if url:
                    sources.append({"title": getattr(cit, "title", None) or url, "url": url})
    return sources


def _anthropic_run(system, user, model, effort, web_search, max_tokens, temperature=None):
    client = _anthropic_client()
    tools = [WEB_SEARCH_TOOL] if web_search else None
    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    sources: list[dict[str, str]] = []
    text_parts: list[str] = []
    for _ in range(6):
        kwargs: dict[str, Any] = dict(
            model=model, max_tokens=max_tokens, system=system, messages=messages,
        )
        if temperature is not None:
            kwargs["temperature"] = temperature
        if models.is_adaptive_thinking_model(model):
            kwargs["thinking"] = {"type": "adaptive"}
        if models.supports_effort(model):
            kwargs["output_config"] = {"effort": effort or config.EFFORT}
        if tools:
            kwargs["tools"] = tools
        with client.messages.stream(**kwargs) as stream:
            final = stream.get_final_message()
        sources.extend(_anthropic_sources(final.content))
        text_parts.extend(b.text for b in final.content if getattr(b, "type", "") == "text")
        if final.stop_reason == "pause_turn":
            messages = [{"role": "user", "content": user}, {"role": "assistant", "content": final.content}]
            continue
        break
    return "\n".join(p for p in text_parts if p).strip(), sources


# --- DeepSeek ---------------------------------------------------------------

def _deepseek_chat(
    system: str, user: str, model: str, max_tokens: int, json_mode: bool,
    temperature: float = 0.4, effort: str | None = None,
    deepseek_thinking: str | None = None,
) -> str:
    # DeepSeek's JSON mode requires the word "json" to appear in the prompt.
    if json_mode and "json" not in (system + user).lower():
        system = system + " Respond with a single valid JSON object."
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": min(max_tokens, DEEPSEEK_MAX_OUTPUT),
        "temperature": temperature,
        "stream": False,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if (model or "").lower().startswith("deepseek-v4"):
        # Reasoning tokens and the JSON body share the same 16300-token output cap
        # (DEEPSEEK_MAX_OUTPUT). On a large structured response — deck, candidate,
        # judgment — thinking can swallow the whole budget and leave the JSON empty
        # or truncated ("no JSON found"). So JSON-mode calls default to no thinking
        # unless the caller explicitly opts in; free-text calls keep the configured
        # default, where reasoning improves quality and there is room for it.
        thinking = deepseek_thinking or ("disabled" if json_mode else config.DEEPSEEK_THINKING)
        body["thinking"] = {"type": thinking}
        body["reasoning_effort"] = effort or config.DEEPSEEK_REASONING_EFFORT
    r = httpx.post(
        f"{config.DEEPSEEK_API_BASE}/chat/completions",
        json=body,
        headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
        timeout=300,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"DeepSeek {r.status_code}: {r.text[:500]}")
    return r.json()["choices"][0]["message"]["content"] or ""


def _ddg_search(query: str, k: int = 5) -> list[dict[str, str]]:
    """Best-effort DuckDuckGo HTML search. Returns [] on any failure."""
    try:
        r = httpx.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (APoc research)"},
            timeout=20,
            follow_redirects=True,
        )
        r.raise_for_status()
    except Exception:
        return []
    out: list[dict[str, str]] = []
    pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>', re.DOTALL
    )
    for m in pattern.finditer(r.text):
        href = unescape(m.group("href"))
        if "uddg=" in href:  # DDG redirect wrapper
            qs = parse_qs(urlparse(href).query)
            href = unquote(qs.get("uddg", [href])[0])
        title = unescape(re.sub(r"<[^>]+>", "", m.group("title"))).strip()
        if href.startswith("http"):
            out.append({"title": title or href, "url": href})
        if len(out) >= k:
            break
    return out


def _deepseek_research(
    system: str,
    user: str,
    model: str,
    max_tokens: int,
    effort: str | None = None,
    deepseek_thinking: str | None = None,
):
    """Query-generation -> web search -> synthesis, returning (digest, sources)."""
    try:
        raw = _deepseek_chat(
            system='You generate web search queries. Output ONLY a JSON object '
            '{"queries": [ ... 3 concise search query strings ... ]}.',
            user=user,
            model=model,
            max_tokens=400,
            json_mode=True,
            effort=effort or config.DEEPSEEK_REASONING_EFFORT,
            deepseek_thinking=deepseek_thinking,
        )
        queries = (extract_json(raw) or {}).get("queries", [])
    except Exception:
        queries = []
    if not isinstance(queries, list) or not queries:
        queries = [user.splitlines()[0][:80] + " architecture best practices"]

    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    blocks: list[str] = []
    for q in queries[:3]:
        for res in _ddg_search(str(q)):
            if res["url"] in seen:
                continue
            seen.add(res["url"])
            sources.append(res)
            blocks.append(f"- {res['title']} — {res['url']}")
    findings = "\n".join(blocks) if blocks else "(web search returned no results; rely on your own knowledge)"
    digest = _deepseek_chat(
        system=system,
        user=f"{user}\n\n--- Web search findings (cite where relevant) ---\n{findings}",
        model=model,
        max_tokens=max_tokens,
        json_mode=False,
        effort=effort or config.DEEPSEEK_REASONING_EFFORT,
        deepseek_thinking=deepseek_thinking,
    )
    return digest, sources


# --- JSON helpers -----------------------------------------------------------

def _repair_json(text: str) -> Any | None:
    """Best-effort repair of truncated JSON (close open strings/brackets)."""
    start = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
    if start == -1:
        return None
    s = text[start:]
    stack: list[str] = []
    in_str = esc = False
    for ch in s:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()
    repaired = s
    if in_str:
        repaired += '"'
    repaired = repaired.rstrip()
    # Drop a dangling trailing key that never got a value, e.g. a response cut off
    # right after `"how_addressed":` — that fragment is unrepairable, but the
    # object up to it is salvageable, so we strip the orphan key and its comma.
    repaired = re.sub(r',?\s*"(?:[^"\\]|\\.)*"\s*:\s*$', "", repaired)
    repaired = re.sub(r",\s*$", "", repaired)
    while stack:
        repaired += stack.pop()
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None


def extract_json(text: str) -> Any:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass
    start = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
    if start != -1:
        for end in range(len(text), start, -1):
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                continue
    repaired = _repair_json(text)
    if repaired is not None:
        return repaired
    raise ValueError("no JSON found in model response")


# --- Public API -------------------------------------------------------------

def run_text(
    *, system: str, user: str, model: str | None = None, effort: str | None = None,
    web_search: bool = False, max_tokens: int = 16000, json_mode: bool = False,
    temperature: float | None = None, deepseek_thinking: str | None = None,
) -> tuple[str, list[dict[str, str]]]:
    model = model or config.MODEL
    if models.provider_for_model(model) == "deepseek":
        if web_search:
            return _deepseek_research(system, user, model, max_tokens, effort, deepseek_thinking)
        return _deepseek_chat(
            system, user, model, max_tokens, json_mode,
            0.4 if temperature is None else temperature, effort, deepseek_thinking,
        ), []
    text, sources = _anthropic_run(system, user, model, effort, web_search, max_tokens, temperature)
    seen: set[str] = set()
    return text, [s for s in sources if not (s["url"] in seen or seen.add(s["url"]))]


READ_SECTION_TOOL = {
    "name": "read_section",
    "description": (
        "Read the full text of one section of the canonical design by its key "
        "(e.g. 'risks', 'components', 'tech_stack'). Use the manifest to decide "
        "which sections you need, then read only those."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"section": {"type": "string", "description": "Section key from the manifest"}},
        "required": ["section"],
    },
}


def run_tool_loop(
    *, system: str, user: str, model: str, read_section: Callable[[str], str],
    max_tokens: int = 16000, max_iterations: int = 8,
) -> str:
    """Anthropic manual agentic loop exposing only the read_section tool.

    The model decides which canonical-design sections to read; ``read_section``
    (a controller callback, typically ArtifactStore.read_section) executes the
    read. Returns the concatenated final text once the model stops calling tools.
    """
    client = _anthropic_client()
    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    text_parts: list[str] = []
    for _ in range(max_iterations):
        kwargs: dict[str, Any] = dict(
            model=model, max_tokens=max_tokens, system=system,
            messages=messages, tools=[READ_SECTION_TOOL],
        )
        if models.is_adaptive_thinking_model(model):
            kwargs["thinking"] = {"type": "adaptive"}
        if models.supports_effort(model):
            kwargs["output_config"] = {"effort": config.EFFORT}
        with client.messages.stream(**kwargs) as stream:
            final = stream.get_final_message()

        tool_uses = [b for b in final.content if getattr(b, "type", "") == "tool_use"]
        text_parts.extend(b.text for b in final.content if getattr(b, "type", "") == "text")
        if not tool_uses:
            break

        messages.append({"role": "assistant", "content": final.content})
        results = []
        for tu in tool_uses:
            section = (getattr(tu, "input", {}) or {}).get("section", "")
            results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": read_section(section),
            })
        messages.append({"role": "user", "content": results})
    return "\n".join(p for p in text_parts if p).strip()


def run_json(
    *, system: str, user: str, model: str | None = None, effort: str | None = None,
    web_search: bool = False, max_tokens: int = 16000, temperature: float | None = None,
) -> tuple[Any, list[dict[str, str]]]:
    text, sources = run_text(
        system=system, user=user, model=model, effort=effort,
        web_search=web_search, max_tokens=max_tokens, json_mode=True,
        temperature=temperature,
    )
    return extract_json(text), sources
