import json

from app import config, db, generation, prompts


def test_legacy_generation_writes_raw_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path / "runs")
    db.init_db()
    project_id = db.new_id("proj_")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO projects (id, title, brief_json, created_at, updated_at) VALUES (?,?,?,?,?)",
            (
                project_id,
                "Legacy POC",
                json.dumps({"business_goal": "g", "scale": "s"}),
                db.now(),
                db.now(),
            ),
        )

    monkeypatch.setattr(
        generation.research,
        "run_research",
        lambda brief, title, raw_sink=None: ("RESEARCH DIGEST", [{"url": "u", "title": "t"}]),
    )

    def fake_run_json(*, system, user, model, max_tokens):
        if system == prompts.DESIGN_SYSTEM:
            return {
                "title": "Legacy POC",
                "executive_summary": "summary",
                "components": [],
                "markdown": "markdown",
            }, []
        if system == prompts.DECK_SYSTEM:
            return {"theme_css": "", "slides": ["<section class=\"slide\">Slide</section>"]}, []
        if system == prompts.REVIEW_SYSTEM:
            return {"reviews": [], "annotations": []}, []
        raise AssertionError(f"unexpected JSON system: {system[:80]}")

    model_kwargs = {}

    def fake_run_text(*, system, user, model, max_tokens, json_mode=False, **kwargs):
        if system == prompts.DESIGN_SYSTEM:
            model_kwargs["design"] = kwargs
            return json.dumps({
                "title": "Legacy POC",
                "executive_summary": "summary",
                "components": [],
                "markdown": "markdown",
            }), []
        if system == prompts.DOCUMENT_SYSTEM:
            model_kwargs["document"] = kwargs
            return "## Executive summary\n\nDoc\n\n```mermaid\nflowchart LR\nA-->B\n```", []
        if system == prompts.DECK_SYSTEM:
            model_kwargs["deck"] = kwargs
            return json.dumps({"theme_css": "", "slides": ["<section class=\"slide\">Slide</section>"]}), []
        if system == prompts.REVIEW_SYSTEM:
            model_kwargs["reviews"] = kwargs
            return json.dumps({"reviews": [], "annotations": []}), []
        raise AssertionError(f"unexpected text system: {system[:80]}")

    monkeypatch.setattr(generation.llm, "run_json", fake_run_json)
    monkeypatch.setattr(generation.llm, "run_text", fake_run_text)

    generation.run_generation(project_id)

    with db.connect() as conn:
        detail = conn.execute(
            "SELECT detail_json FROM audit_events WHERE project_id=? AND action='generation.started'",
            (project_id,),
        ).fetchone()["detail_json"]
    run_id = json.loads(detail)["run_id"]
    run_dir = config.RUNS_DIR / run_id
    assert (run_dir / "research.raw.txt").read_text(encoding="utf-8") == "RESEARCH DIGEST"
    assert (run_dir / "design.raw.txt").exists()
    assert (run_dir / "document.raw.txt").exists()
    assert (run_dir / "deck.raw.txt").exists()
    assert (run_dir / "reviews.raw.txt").exists()
    assert json.loads((run_dir / "design.meta.json").read_text(encoding="utf-8"))["parsed"] is True
    with db.connect() as conn:
        poc = conn.execute("SELECT document_md, document_html, diagrams_json FROM pocs WHERE project_id=?", (project_id,)).fetchone()
    assert poc["document_md"].startswith("## Executive summary")
    assert "```mermaid" in poc["document_md"]
    assert poc["document_html"] == ""
    assert poc["diagrams_json"] == "[]"
    assert model_kwargs["document"]["deepseek_thinking"] == "enabled"
    assert model_kwargs["document"]["effort"] == "max"
    assert model_kwargs["deck"]["deepseek_thinking"] == "enabled"
    assert model_kwargs["deck"]["effort"] == "max"
    assert model_kwargs["reviews"]["deepseek_thinking"] == "enabled"
    assert model_kwargs["reviews"]["effort"] == "max"
