import json
from app import db, config
from app.graph import run as run_mod


def test_run_generation_graph_invokes_graph(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    pid = db.new_id("proj_")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO projects (id, title, brief_json, created_at, updated_at) VALUES (?,?,?,?,?)",
            (pid, "My POC", json.dumps({"business_goal": "g", "scale": "s"}), db.now(), db.now()),
        )

    captured = {}

    class _FakeGraph:
        def invoke(self, state, config=None):
            captured["state"] = state
            return {**state, "poc_id": "poc_done"}

    monkeypatch.setattr(run_mod, "build_graph", lambda: _FakeGraph())
    run_mod.run_generation_graph(pid)

    assert captured["state"]["project_id"] == pid
    assert "My POC" in captured["state"]["brief_text"]
    assert captured["state"]["run_id"]  # a run id was assigned
    with db.connect() as conn:
        actions = [r["action"] for r in conn.execute(
            "SELECT action FROM audit_events WHERE project_id=?", (pid,)).fetchall()]
    assert "generation.started" in actions
