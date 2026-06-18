import pytest

from app import config, prompts


def test_ai_edit_model_default():
    assert config.AI_EDIT_MODEL == "deepseek-v4-pro"


def test_prompts_present():
    assert "addressed" in prompts.AI_EDIT_SYSTEM
    assert "interdependent" in prompts.AI_EDIT_SYSTEM.lower()
    assert "only" in prompts.POC_CHAT_SYSTEM.lower()


def test_strip_tool_artifacts_removes_dsml_block():
    from app import ai_assist
    raw = "<｜｜DSML｜｜tool_calls>junk</｜｜DSML｜｜tool_calls>\n## Real\nbody"
    out = ai_assist.strip_tool_artifacts(raw)
    assert "DSML" not in out
    assert out.startswith("## Real")


def test_split_edit_response_parses_body_and_addressed():
    from app import ai_assist
    raw = '## Doc\nrevised body\n\n```json\n{"addressed": ["cm_1", "cm_2"]}\n```'
    body, addressed = ai_assist.split_edit_response(raw)
    assert body.strip() == "## Doc\nrevised body"
    assert addressed == ["cm_1", "cm_2"]


def test_split_edit_response_raises_on_missing_marker():
    from app import ai_assist
    with pytest.raises(ai_assist.EditTruncatedError):
        ai_assist.split_edit_response("## Doc\nrevised body with no trailing json block")


def test_run_ai_edit_calls_model_and_splits(monkeypatch):
    from app import ai_assist
    captured = {}

    def fake_run_text(*, system, user, model, **kwargs):
        captured["system"] = system
        captured["user"] = user
        captured["model"] = model
        captured["kwargs"] = kwargs
        return ('## Revised\nnew text\n\n```json\n{"addressed": ["cm_9"]}\n```', [])

    monkeypatch.setattr(ai_assist.llm, "run_text", fake_run_text)
    body, addressed = ai_assist.run_ai_edit(
        document_md="## Old\nold text",
        comments=[{"id": "cm_9", "role": "security", "anchor_slug": "risks",
                   "anchor_line": 4, "body": "tighten auth"}],
        instruction="be terse",
    )
    assert body.strip() == "## Revised\nnew text"
    assert addressed == ["cm_9"]
    assert captured["model"] == ai_assist.config.AI_EDIT_MODEL
    assert "tighten auth" in captured["user"]
    assert "be terse" in captured["user"]
    assert captured["kwargs"].get("deepseek_thinking") == "enabled"


def test_run_poc_chat_uses_context(monkeypatch):
    from app import ai_assist
    captured = {}

    def fake_run_text(*, system, user, model, **kwargs):
        captured["system"] = system
        captured["user"] = user
        return ("the answer", [])

    monkeypatch.setattr(ai_assist.llm, "run_text", fake_run_text)
    reply = ai_assist.run_poc_chat(
        messages=[{"role": "user", "content": "what did security flag?"}],
        context="DOCUMENT:\n## Risks\n...\nREVIEWS:\nsecurity: revise — weak auth",
    )
    assert reply == "the answer"
    assert "weak auth" in captured["system"]
    assert "what did security flag?" in captured["user"]
