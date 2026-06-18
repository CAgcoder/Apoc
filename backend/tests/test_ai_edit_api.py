from fastapi.testclient import TestClient

from app import ai_assist, config, db, main


def _seed(conn, *, with_accepted=True):
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
        (poc_id, pid, 1, "T", "## Risks\nold", "{}", db.now(), db.now()),
    )
    sh = db.new_id("s_")
    conn.execute("INSERT INTO stakeholders (id, name, role, org, created_at) VALUES (?,?,?,?,?)",
                 (sh, "Rev", "security", "O", db.now()))
    accepted_id = db.new_id("cm_")
    open_id = db.new_id("cm_")
    conn.execute("INSERT INTO comments (id, poc_id, stakeholder_id, body, anchor_slug, status, created_at)"
                 " VALUES (?,?,?,?,?,?,?)",
                 (accepted_id, poc_id, sh, "tighten auth", "risks",
                  "accepted" if with_accepted else "open", db.now()))
    conn.execute("INSERT INTO comments (id, poc_id, stakeholder_id, body, status, created_at)"
                 " VALUES (?,?,?,?,?,?)",
                 (open_id, poc_id, sh, "ignored open comment", "open", db.now()))
    return pid, poc_id, accepted_id, open_id


def test_ai_edit_reads_only_accepted_and_returns_proposal(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "edit.db")
    db.init_db()
    with db.connect() as conn:
        _, poc_id, accepted_id, open_id = _seed(conn)

    seen = {}

    def fake_run_text(*, system, user, model, **kwargs):
        seen["user"] = user
        return ('## Risks\nrevised\n\n```json\n{"addressed": ["%s"]}\n```' % accepted_id, [])

    monkeypatch.setattr(ai_assist.llm, "run_text", fake_run_text)
    client = TestClient(main.app)
    r = client.post(f"/api/pocs/{poc_id}/ai-edit", json={"instruction": ""},
                    headers={"X-Apoc-Role": "architect"})
    assert r.status_code == 200
    data = r.json()
    assert data["proposed_md"].strip() == "## Risks\nrevised"
    assert data["addressed_comment_ids"] == [accepted_id]
    assert "tighten auth" in seen["user"]
    assert "ignored open comment" not in seen["user"]


def test_ai_edit_422_when_nothing_to_apply(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "noop.db")
    db.init_db()
    with db.connect() as conn:
        _, poc_id, _, _ = _seed(conn, with_accepted=False)
    client = TestClient(main.app)
    r = client.post(f"/api/pocs/{poc_id}/ai-edit", json={"instruction": ""},
                    headers={"X-Apoc-Role": "architect"})
    assert r.status_code == 422


def test_ai_edit_403_for_non_architect(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gate.db")
    db.init_db()
    with db.connect() as conn:
        _, poc_id, _, _ = _seed(conn)
    client = TestClient(main.app)
    r = client.post(f"/api/pocs/{poc_id}/ai-edit", json={}, headers={"X-Apoc-Role": "security"})
    assert r.status_code == 403


def test_ai_edit_502_on_truncation(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "trunc.db")
    db.init_db()
    with db.connect() as conn:
        _, poc_id, _, _ = _seed(conn)

    def fake_run_text(*, system, user, model, **kwargs):
        return ("## Risks\nrevised but cut off with no trailing json", [])

    monkeypatch.setattr(ai_assist.llm, "run_text", fake_run_text)
    client = TestClient(main.app)
    r = client.post(f"/api/pocs/{poc_id}/ai-edit", json={}, headers={"X-Apoc-Role": "architect"})
    assert r.status_code == 502
    # nothing saved
    with db.connect() as conn:
        assert conn.execute("SELECT document_md FROM pocs WHERE id=?", (poc_id,)).fetchone()[0] == "## Risks\nold"


def test_ai_edit_strips_tool_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "hyg.db")
    db.init_db()
    with db.connect() as conn:
        _, poc_id, accepted_id, _ = _seed(conn)

    def fake_run_text(*, system, user, model, **kwargs):
        dirty = ("<｜｜DSML｜｜tool_calls>x</｜｜DSML｜｜tool_calls>"
                 '## Risks\nclean\n\n```json\n{"addressed": []}\n```')
        return (dirty, [])

    monkeypatch.setattr(ai_assist.llm, "run_text", fake_run_text)
    client = TestClient(main.app)
    r = client.post(f"/api/pocs/{poc_id}/ai-edit", json={}, headers={"X-Apoc-Role": "architect"})
    assert r.status_code == 200
    assert "DSML" not in r.json()["proposed_md"]
