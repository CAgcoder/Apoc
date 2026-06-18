from fastapi.testclient import TestClient

from app import config, db, main, prompts


def _seed_poc(conn):
    pid = db.new_id("p_")
    conn.execute(
        "INSERT INTO projects (id, title, client_name, consulting_org, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (pid, "T", "C", "O", "designed", db.now(), db.now()),
    )
    poc_id = db.new_id("poc_")
    conn.execute(
        "INSERT INTO pocs (id, project_id, version, title, markdown, document_md, design_json,"
        " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (poc_id, pid, 1, "T", "", "## Executive summary\nhi", "{}", db.now(), db.now()),
    )
    sh = db.new_id("s_")
    conn.execute(
        "INSERT INTO stakeholders (id, name, role, org, created_at) VALUES (?,?,?,?,?)",
        (sh, "Arch", "architect", "O", db.now()),
    )
    return pid, poc_id, sh


def test_schema_has_markdown_document_and_comment_anchors(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "schema.db")
    db.init_db()

    with db.connect() as conn:
        poc_cols = {r["name"] for r in conn.execute("PRAGMA table_info(pocs)").fetchall()}
        comment_cols = {r["name"] for r in conn.execute("PRAGMA table_info(comments)").fetchall()}

    assert "document_md" in poc_cols
    assert {"anchor_line", "anchor_slug"}.issubset(comment_cols)


def test_document_prompts_require_markdown_and_mermaid():
    assert "GitHub-Flavored Markdown" in prompts.DOCUMENT_SYSTEM
    assert "```mermaid" in prompts.DOCUMENT_SYSTEM
    assert "<figure data-diagram=\"architecture\"" not in prompts.DOCUMENT_SYSTEM
    assert "Markdown" in prompts.DOCUMENT_SECTION_SYSTEM
    assert "```mermaid" in prompts.DOCUMENT_SECTION_SYSTEM
    assert "semantic HTML" not in prompts.DOCUMENT_SECTION_SYSTEM


def test_bundle_returns_document_md(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "bundle.db")
    db.init_db()
    with db.connect() as conn:
        pid, _, _ = _seed_poc(conn)

    client = TestClient(main.app)
    r = client.get(f"/api/projects/{pid}/poc")

    assert r.status_code == 200
    poc = r.json()["poc"]
    assert poc["document_md"].startswith("## Executive summary")
    assert "diagrams" not in poc
    assert "document_html" not in poc


def test_save_document_md_and_comment_anchor(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "save.db")
    db.init_db()
    with db.connect() as conn:
        pid, poc_id, sh = _seed_poc(conn)

    client = TestClient(main.app)
    r = client.post(
        f"/api/pocs/{poc_id}/document",
        json={"document_md": "## Risks\nnew"},
        headers={"X-Apoc-Role": "architect"},
    )
    assert r.status_code == 200

    r = client.post(
        f"/api/pocs/{poc_id}/comments",
        json={"stakeholder_id": sh, "body": "see line", "anchor_line": 12, "anchor_slug": "risks"},
    )
    assert r.status_code == 200

    b = client.get(f"/api/projects/{pid}/poc").json()
    assert b["poc"]["document_md"] == "## Risks\nnew"
    c = b["comments"][0]
    assert c["anchor_line"] == 12
    assert c["anchor_slug"] == "risks"
