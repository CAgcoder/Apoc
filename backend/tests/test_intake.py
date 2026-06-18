"""Tests for the conversational intake agent and its persistence.

Run: .venv/bin/python -m tests.test_intake   (from apoc/backend)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from app import config

# Point the data layer at a throwaway DB before anything opens a connection.
config.DB_PATH = Path(tempfile.mkdtemp()) / "test_intake.db"

from app import db, intake, prompts  # noqa: E402

db.init_db()


def test_normalize_turn_fills_defaults():
    turn = intake.normalize_turn(
        {"message": "Which cloud?", "options": [{"label": "AWS", "advantage": "wide"}, "Azure"]}
    )
    assert turn["message"] == "Which cloud?"
    assert turn["allow_free_text"] is True
    assert turn["done"] is False
    assert turn["brief"] is None
    assert turn["options"][0] == {"label": "AWS", "advantage": "wide"}
    assert turn["options"][1] == {"label": "Azure", "advantage": ""}  # bare string lifted


def test_normalize_turn_done_forces_brief_keys():
    turn = intake.normalize_turn(
        {"message": "All set.", "done": True, "title": "Tracker",
         "brief": {"cloud": "AWS", "junk": "ignored"}}
    )
    assert turn["done"] is True
    assert turn["title"] == "Tracker"
    assert set(turn["brief"]) == set(intake.BRIEF_KEYS)
    assert turn["brief"]["cloud"] == "AWS"
    assert turn["brief"]["business_goal"] == ""  # missing key filled empty, not absent


def test_normalize_turn_preserves_client_and_org_metadata():
    turn = intake.normalize_turn(
        {
            "message": "All set.",
            "client_name": "  Acme Bank  ",
            "consulting_org": "  ArcD Studio  ",
        }
    )
    assert turn["client_name"] == "Acme Bank"
    assert turn["consulting_org"] == "ArcD Studio"

    missing = intake.normalize_turn({"message": "No names yet."})
    assert missing["client_name"] is None
    assert missing["consulting_org"] is None


def test_normalize_turn_tolerates_garbage():
    turn = intake.normalize_turn("not a dict")
    assert turn["options"] == [] and turn["message"] == "" and turn["brief"] is None


def test_run_intake_turn_passes_history_to_model():
    seen: dict[str, str] = {}
    original = intake.llm.run_text

    def fake_run_text(*, system, user, **_):
        seen["system"] = system
        seen["user"] = user
        return ('{"message": "hi", "options": []}', [])

    intake.llm.run_text = fake_run_text
    try:
        out = intake.run_intake_turn([{"role": "user", "content": "build a tracker"}])
    finally:
        intake.llm.run_text = original

    assert seen["system"] == prompts.INTAKE_SYSTEM
    assert "build a tracker" in seen["user"]
    assert out["message"] == "hi"


def test_run_intake_turn_writes_raw_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)

    def fake_run_text(**kwargs):
        return '{"message": "hi", "options": []}', []

    monkeypatch.setattr(intake.llm, "run_text", fake_run_text)

    out = intake.run_intake_turn([{"role": "user", "content": "build a tracker"}])

    assert out["message"] == "hi"
    [turn_dir] = list((tmp_path / "intake_chat").glob("intake_chat_*"))
    assert (turn_dir / "turn.raw.txt").read_text(encoding="utf-8") == '{"message": "hi", "options": []}'
    meta = (turn_dir / "turn.meta.json").read_text(encoding="utf-8")
    assert '"model": "' + config.MODEL + '"' in meta
    assert '"parsed": true' in meta


def test_create_project_persists_intake_chat():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    chat = [
        {"role": "user", "content": "build a tracker"},
        {"role": "assistant", "content": "which cloud?"},
    ]
    brief = {k: "value-" + k for k in intake.BRIEF_KEYS}
    resp = client.post("/api/projects", json={"title": "T", "brief": brief, "intake_chat": chat})
    assert resp.status_code == 200
    pid = resp.json()["id"]

    got = client.get(f"/api/projects/{pid}").json()
    assert got["intake_chat"] == chat
    assert got["brief"]["cloud"] == "value-cloud"


def test_intake_chat_endpoint_returns_normalized_turn():
    from fastapi.testclient import TestClient

    from app import main

    original = main.intake.run_intake_turn
    main.intake.run_intake_turn = lambda messages: {"message": "Q1", "options": [], "done": False}
    try:
        client = TestClient(main.app)
        resp = client.post("/api/intake/chat", json={"messages": []})
    finally:
        main.intake.run_intake_turn = original
    assert resp.status_code == 200
    assert resp.json()["message"] == "Q1"


def test_normalize_turn_extracts_requirements_detail_on_done():
    turn = intake.normalize_turn(
        {
            "message": "Got it.",
            "done": True,
            "title": "Risk POC",
            "brief": {k: "x" for k in intake.BRIEF_KEYS},
            "requirements_detail": "  Full dense requirements summary.  ",
        }
    )
    assert turn["requirements_detail"] == "Full dense requirements summary."


def test_normalize_turn_requirements_detail_defaults_empty():
    turn = intake.normalize_turn({"message": "Which cloud?"})
    assert turn["requirements_detail"] == ""


def test_brief_text_appends_requirements_detail():
    from app import generation

    project = {
        "title": "T",
        "client_name": "",
        "consulting_org": "",
        "requirements_detail": "DETAIL-MARKER " + ("x" * 9000),
    }
    text = generation._brief_text(project, {"business_goal": "g"})
    assert "DETAIL-MARKER" in text
    assert "Detailed requirements from uploaded document" in text
    assert "x" * 6001 not in text


def test_brief_text_omits_detail_when_absent():
    from app import generation

    project = {"title": "T", "client_name": "", "consulting_org": ""}
    text = generation._brief_text(project, {"business_goal": "g"})
    assert "Detailed requirements from uploaded document" not in text


if __name__ == "__main__":
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {t.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
