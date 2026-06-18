import pytest

from app import llm


def test_extract_json_salvages_truncation_on_dangling_key():
    # DeepSeek truncated mid-object right after a key, with no value emitted.
    raw = (
        '{"title": "FinCore", "executive_summary": "es", '
        '"requirements_mapping": [{"requirement": "ACID writes", "how_addressed":'
    )
    design = llm.extract_json(raw)
    assert design["title"] == "FinCore"
    assert design["executive_summary"] == "es"
    # The complete row is preserved; the orphan key is dropped.
    assert design["requirements_mapping"] == [{"requirement": "ACID writes"}]


def test_extract_json_salvages_truncation_inside_value():
    raw = '{"title": "FinCore", "context": "a partial sentence that got cut o'
    design = llm.extract_json(raw)
    assert design["title"] == "FinCore"
    assert design["context"].startswith("a partial sentence")


def test_extract_json_raises_when_no_json_present():
    with pytest.raises(ValueError, match="no JSON found"):
        llm.extract_json("I cannot produce that as JSON.")


def _fake_deepseek(monkeypatch, captured):
    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    def fake_post(url, *, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(llm.config, "DEEPSEEK_API_BASE", "https://deepseek.test")
    monkeypatch.setattr(llm.config, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(llm.httpx, "post", fake_post)


def test_deepseek_v4_pro_uses_thinking_and_max_effort_for_free_text(monkeypatch):
    captured = {}
    _fake_deepseek(monkeypatch, captured)

    text, sources = llm.run_text(
        system="Write a digest.",
        user="Summarise the findings.",
        model="deepseek-v4-pro",
        max_tokens=12000,
        json_mode=False,
    )

    assert text == '{"ok": true}'
    assert sources == []
    assert captured["url"] == "https://deepseek.test/chat/completions"
    body = captured["json"]
    assert body["model"] == "deepseek-v4-pro"
    # Free-text calls have room for reasoning and benefit from it.
    assert body["thinking"] == {"type": "enabled"}
    assert body["reasoning_effort"] == "max"
    assert "response_format" not in body
    assert body["max_tokens"] == 12000


def test_deepseek_v4_pro_disables_thinking_in_json_mode(monkeypatch):
    captured = {}
    _fake_deepseek(monkeypatch, captured)

    # JSON mode shares the 16300-token cap with reasoning, so thinking is off by
    # default to keep the whole budget for the structured body.
    llm.run_text(
        system="Return json.",
        user="Return a JSON object.",
        model="deepseek-v4-pro",
        max_tokens=16000,
        json_mode=True,
    )

    body = captured["json"]
    assert body["thinking"] == {"type": "disabled"}
    assert body["reasoning_effort"] == "max"
    assert body["response_format"] == {"type": "json_object"}


def test_deepseek_v4_pro_allows_thinking_override(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    def fake_post(url, *, json, headers, timeout):
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(llm.config, "DEEPSEEK_API_BASE", "https://deepseek.test")
    monkeypatch.setattr(llm.config, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(llm.httpx, "post", fake_post)

    llm.run_text(
        system="Return json.",
        user="Return a JSON object.",
        model="deepseek-v4-pro",
        max_tokens=4000,
        json_mode=True,
        deepseek_thinking="disabled",
        effort="max",
    )

    assert captured["json"]["thinking"] == {"type": "disabled"}
    assert captured["json"]["reasoning_effort"] == "max"


def test_deepseek_web_search_preserves_thinking_override(monkeypatch):
    captured = {}

    def fake_deepseek_research(system, user, model, max_tokens, effort=None, deepseek_thinking=None):
        captured["effort"] = effort
        captured["deepseek_thinking"] = deepseek_thinking
        return "DIGEST", []

    monkeypatch.setattr(llm.models, "provider_for_model", lambda model: "deepseek")
    monkeypatch.setattr(llm, "_deepseek_research", fake_deepseek_research)

    text, sources = llm.run_text(
        system="Research.",
        user="Find sources.",
        model="deepseek-v4-pro",
        max_tokens=4000,
        web_search=True,
        deepseek_thinking="enabled",
        effort="max",
    )

    assert text == "DIGEST"
    assert sources == []
    assert captured["deepseek_thinking"] == "enabled"
    assert captured["effort"] == "max"
