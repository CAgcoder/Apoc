from fastapi.testclient import TestClient

from app import ai_assist, config, db, main


def test_full_edit_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "flow.db")
    db.init_db()
    pid = db.new_id("p_")
    poc_id = db.new_id("poc_")
    sh = db.new_id("s_")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO projects (id, title, client_name, consulting_org, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)", (pid, "T", "C", "O", "in_review", db.now(), db.now()))
        conn.execute(
            "INSERT INTO pocs (id, project_id, version, title, document_md, design_json, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)", (poc_id, pid, 1, "T", "## Risks\nold", "{}", db.now(), db.now()))
        conn.execute("INSERT INTO stakeholders (id, name, role, org, created_at) VALUES (?,?,?,?,?)",
                     (sh, "Rev", "security", "O", db.now()))
        c1, c2, c3 = db.new_id("cm_"), db.new_id("cm_"), db.new_id("cm_")
        for cid, body in ((c1, "fix auth"), (c2, "fix cost"), (c3, "untouched")):
            conn.execute("INSERT INTO comments (id, poc_id, stakeholder_id, body, status, created_at)"
                         " VALUES (?,?,?,?,?,?)", (cid, poc_id, sh, body, "open", db.now()))

    client = TestClient(main.app)
    arch = {"X-Apoc-Role": "architect"}

    # accept two comments
    for cid in (c1, c2):
        assert client.post(f"/api/pocs/{poc_id}/comments/{cid}/status",
                           json={"status": "accepted"}, headers=arch).status_code == 200

    # ai-edit addresses both
    def fake_run_text(*, system, user, model, **kwargs):
        return ('## Risks\nrevised\n\n```json\n{"addressed": ["%s","%s"]}\n```' % (c1, c2), [])
    monkeypatch.setattr(ai_assist.llm, "run_text", fake_run_text)
    res = client.post(f"/api/pocs/{poc_id}/ai-edit", json={}, headers=arch).json()
    assert res["addressed_comment_ids"] == [c1, c2]

    # save the proposed doc, then bulk-close the addressed ids
    assert client.post(f"/api/pocs/{poc_id}/document",
                       json={"document_md": res["proposed_md"]}, headers=arch).status_code == 200
    assert client.post(f"/api/pocs/{poc_id}/comments/status",
                       json={"ids": res["addressed_comment_ids"], "status": "closed"},
                       headers=arch).status_code == 200

    bundle = client.get(f"/api/projects/{pid}/poc").json()
    by_id = {c["id"]: c for c in bundle["comments"]}
    assert bundle["poc"]["document_md"] == "## Risks\nrevised"
    assert by_id[c1]["status"] == "closed"
    assert by_id[c2]["status"] == "closed"
    assert by_id[c3]["status"] == "open"  # un-accepted comment untouched
