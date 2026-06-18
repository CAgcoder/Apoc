from pathlib import Path
from unittest.mock import patch

from eval import opus_solo


def test_generate_uses_run_digest_and_writes_json(tmp_path):
    (tmp_path / "research.raw.txt").write_text("DIGEST-TEXT", encoding="utf-8")

    captured = {}

    def fake_run_text(*, system, user, model, max_tokens, json_mode, **kw):
        captured["user"] = user
        captured["model"] = model
        return '{"title": "Opus solo design", "decisions": []}', []

    with patch("eval.opus_solo.llm.run_text", side_effect=fake_run_text):
        design = opus_solo.generate(tmp_path, brief_text="BRIEF", model="claude-opus-4-8")

    assert "DIGEST-TEXT" in captured["user"]
    assert "BRIEF" in captured["user"]
    assert captured["model"] == "claude-opus-4-8"
    assert design["title"] == "Opus solo design"
    assert (tmp_path / "opus_solo.json").exists()


def test_missing_digest_raises(tmp_path):
    try:
        opus_solo.generate(tmp_path, brief_text="BRIEF", model="claude-opus-4-8")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass
