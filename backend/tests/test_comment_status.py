from app import config, db
from fastapi.testclient import TestClient

from app import main


def test_comments_table_has_status_column(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "status.db")
    db.init_db()
    with db.connect() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(comments)").fetchall()}
    assert "status" in cols


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
        (poc_id, pid, 1, "T", "## Executive summary\nhi", "{}", db.now(), db.now()),
    )
    sh = db.new_id("s_")
    conn.execute(
        "INSERT INTO stakeholders (id, name, role, org, created_at) VALUES (?,?,?,?,?)",
        (sh, "Rev", "security", "O", db.now()),
    )
    cid = db.new_id("cm_")
    conn.execute(
        "INSERT INTO comments (id, poc_id, stakeholder_id, body, created_at) VALUES (?,?,?,?,?)",
        (cid, poc_id, sh, "fix this", db.now()),
    )
    return pid, poc_id, cid


def test_status_round_trip_architect_only(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "rt.db")
    db.init_db()
    with db.connect() as conn:
        pid, poc_id, cid = _seed(conn)
    client = TestClient(main.app)
    arch = {"X-Apoc-Role": "architect"}

    # open -> accepted -> closed -> open
    for status in ("accepted", "closed", "open"):
        r = client.post(f"/api/pocs/{poc_id}/comments/{cid}/status", json={"status": status}, headers=arch)
        assert r.status_code == 200
        b = client.get(f"/api/projects/{pid}/poc").json()
        assert b["comments"][0]["status"] == status


def test_status_rejects_non_architect(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gate.db")
    db.init_db()
    with db.connect() as conn:
        _, poc_id, cid = _seed(conn)
    client = TestClient(main.app)
    r = client.post(f"/api/pocs/{poc_id}/comments/{cid}/status",
                    json={"status": "accepted"}, headers={"X-Apoc-Role": "security"})
    assert r.status_code == 403


def test_status_rejects_bad_value(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "bad.db")
    db.init_db()
    with db.connect() as conn:
        _, poc_id, cid = _seed(conn)
    client = TestClient(main.app)
    r = client.post(f"/api/pocs/{poc_id}/comments/{cid}/status",
                    json={"status": "deleted"}, headers={"X-Apoc-Role": "architect"})
    assert r.status_code == 422


def test_bulk_status(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "bulk.db")
    db.init_db()
    with db.connect() as conn:
        pid, poc_id, c1 = _seed(conn)
        c2 = db.new_id("cm_")
        conn.execute("INSERT INTO comments (id, poc_id, stakeholder_id, body, created_at) VALUES (?,?,?,?,?)",
                     (c2, poc_id, "x", "b", db.now()))
    client = TestClient(main.app)
    r = client.post(f"/api/pocs/{poc_id}/comments/status",
                    json={"ids": [c1, c2], "status": "closed"}, headers={"X-Apoc-Role": "architect"})
    assert r.status_code == 200
    statuses = {c["status"] for c in client.get(f"/api/projects/{pid}/poc").json()["comments"]}
    assert statuses == {"closed"}
