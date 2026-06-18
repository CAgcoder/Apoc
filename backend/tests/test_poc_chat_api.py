from fastapi.testclient import TestClient

from app import ai_assist, config, db, main


def _seed(conn):
    pid = db.new_id("p_")
    conn.execute(
        "INSERT INTO projects (id, title, client_name, consulting_org, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (pid, "T", "C", "O", "in_review", db.now(), db.now()),
    )
    poc_id = db.new_id("poc_")
    conn.execute(
        "INSERT INTO pocs (id, project_id, version, title, document_md, design_json, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (poc_id, pid, 1, "T", "## Risks\nauth is weak", "{}", db.now(), db.now()),
    )
    conn.execute(
        "INSERT INTO review_reports (id, poc_id, role, summary, verdict, report_md, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (db.new_id("rr_"), poc_id, "security", "weak auth flagged", "revise", "", db.now()),
    )
    conn.execute(
        "INSERT INTO research_notes (id, project_id, poc_id, topic, digest, citations_json, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (db.new_id("rn_"), pid, poc_id, "auth", "OAuth best practices digest", "[]", db.now()),
    )
    return pid, poc_id


def test_chat_returns_reply_for_any_role(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "chat.db")
    db.init_db()
    with db.connect() as conn:
        _, poc_id = _seed(conn)

    seen = {}

    def fake_run_text(*, system, user, model, **kwargs):
        seen["system"] = system
        return ("here is the answer", [])

    monkeypatch.setattr(ai_assist.llm, "run_text", fake_run_text)
    client = TestClient(main.app)
    # no role header — chat is open to all
    r = client.post(f"/api/pocs/{poc_id}/chat",
                    json={"messages": [{"role": "user", "content": "what did security flag?"}]})
    assert r.status_code == 200
    assert r.json()["reply"] == "here is the answer"
    # grounding context carries document + reviews + research
    assert "auth is weak" in seen["system"]
    assert "weak auth flagged" in seen["system"]
    assert "OAuth best practices digest" in seen["system"]


def test_chat_does_not_write_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "chat_ro.db")
    db.init_db()
    with db.connect() as conn:
        pid, poc_id = _seed(conn)

    monkeypatch.setattr(ai_assist.llm, "run_text", lambda **kw: ("ok", []))
    client = TestClient(main.app)
    with db.connect() as conn:
        before = len(conn.execute("SELECT * FROM audit_events").fetchall())
    client.post(f"/api/pocs/{poc_id}/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    with db.connect() as conn:
        after = len(conn.execute("SELECT * FROM audit_events").fetchall())
    assert after == before


def test_chat_400_on_bad_messages(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "chat_bad.db")
    db.init_db()
    with db.connect() as conn:
        _, poc_id = _seed(conn)
    client = TestClient(main.app)
    r = client.post(f"/api/pocs/{poc_id}/chat", json={"messages": "nope"})
    assert r.status_code == 400
