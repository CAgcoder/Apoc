import json
import logging

from app.graph import nodes
from app import config, db


def test_research_node_passes_fusion_model(monkeypatch):
    monkeypatch.setattr(config, "RUNS_DIR", config.RUNS_DIR)
    seen = {}

    def fake_run_research(brief, title, model=None, raw_sink=None):
        seen["model"] = model
        return ("DIGEST", [{"url": "u", "title": "t"}])

    monkeypatch.setattr(nodes.research, "run_research", fake_run_research)
    out = nodes.research_node({"brief_text": "b", "title": "T", "project_id": "p1"})
    assert out["digest"] == "DIGEST"
    assert out["sources"][0]["url"] == "u"
    assert seen["model"] == config.RESEARCH_MODEL_FUSION


def test_research_node_writes_raw_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)

    monkeypatch.setattr(
        nodes.research,
        "run_research",
        lambda brief, title, model=None, raw_sink=None: ("RAW DIGEST", [{"url": "u", "title": "t"}]),
    )

    out = nodes.research_node({"brief_text": "b", "title": "T", "project_id": "p1", "run_id": "r1"})

    run_dir = tmp_path / "r1"
    assert out["digest"] == "RAW DIGEST"
    assert (run_dir / "research.raw.txt").read_text(encoding="utf-8") == "RAW DIGEST"
    meta = json.loads((run_dir / "research.meta.json").read_text(encoding="utf-8"))
    assert meta["model"] == config.RESEARCH_MODEL_FUSION
    assert meta["raw_chars"] == len("RAW DIGEST")
    assert meta["source_count"] == 1


def test_candidate_node_factory_uses_assigned_model(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    caplog.set_level(logging.INFO, logger="app.graph.nodes")
    seen = {}

    def fake_run_text(*, system, user, model, max_tokens, json_mode, **kwargs):
        seen["model"] = model
        seen["json_mode"] = json_mode
        return '{"title": "Cand", "executive_summary": "s", "components": []}', []

    monkeypatch.setattr(nodes.llm, "run_text", fake_run_text)
    node = nodes.make_candidate_node(index=1, model="claude-haiku-4-5")
    out = node({"brief_text": "b", "title": "T", "digest": "D", "run_id": "r1", "project_id": "p1"})
    assert seen["model"] == "claude-haiku-4-5"
    assert seen["json_mode"] is True
    assert out["candidates"][0]["model"] == "claude-haiku-4-5"
    assert out["candidates"][0]["id"] == "B"
    assert out["candidates"][0]["design"]["title"] == "Cand"
    assert (tmp_path / "r1" / "candidate_B.raw.txt").read_text(encoding="utf-8").startswith("{")
    messages = [record.getMessage() for record in caplog.records]
    assert "candidate raw response saved" in messages
    assert "candidate JSON artifact saved" in messages
    raw_record = next(record for record in caplog.records if record.getMessage() == "candidate raw response saved")
    assert raw_record.candidate_id == "B"
    assert raw_record.model == "claude-haiku-4-5"
    assert raw_record.run_id == "r1"
    assert raw_record.raw_path.endswith("candidate_B.raw.txt")


def test_candidate_node_enables_deepseek_thinking_for_deepseek_v4(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    seen = {}

    def fake_run_text(*, system, user, model, max_tokens, json_mode, **kwargs):
        seen.update(kwargs)
        seen["model"] = model
        seen["json_mode"] = json_mode
        return '{"title": "Cand", "executive_summary": "s", "components": []}', []

    monkeypatch.setattr(nodes.llm, "run_text", fake_run_text)
    node = nodes.make_candidate_node(index=0, model="deepseek-v4-pro")
    node({"brief_text": "b", "title": "T", "digest": "D", "run_id": "r1", "project_id": "p1"})

    assert seen["model"] == "deepseek-v4-pro"
    assert seen["json_mode"] is True
    assert seen["deepseek_thinking"] == "enabled"
    assert seen["effort"] == "max"


def test_candidate_node_adds_strict_json_constraints_for_haiku(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    seen = {}

    def fake_run_text(*, system, user, model, max_tokens, json_mode, **kwargs):
        seen["system"] = system
        seen["model"] = model
        return '{"title": "Cand", "executive_summary": "s", "components": []}', []

    monkeypatch.setattr(nodes.llm, "run_text", fake_run_text)
    node = nodes.make_candidate_node(index=1, model="claude-haiku-4-5")
    node({"brief_text": "b", "title": "T", "digest": "D", "run_id": "r1", "project_id": "p1"})

    assert seen["model"] == "claude-haiku-4-5"
    assert "JSON validity contract for Claude Haiku" in seen["system"]
    assert "Do not wrap the JSON in markdown or code fences" in seen["system"]
    assert "Escape every literal double quote inside string values as \\\"" in seen["system"]
    assert "The first character must be { and the final character must be }" in seen["system"]


def test_candidate_node_preserves_raw_output_when_json_parse_fails(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    caplog.set_level(logging.INFO, logger="app.graph.nodes")

    def fake_run_text(*, system, user, model, max_tokens, json_mode, **kwargs):
        return "I cannot produce that as JSON.", []

    monkeypatch.setattr(nodes.llm, "run_text", fake_run_text)
    node = nodes.make_candidate_node(index=1, model="claude-haiku-4-5")

    try:
        node({"brief_text": "b", "title": "T", "digest": "D", "run_id": "r1", "project_id": "p1"})
    except ValueError as exc:
        assert str(exc) == "no JSON found in model response"
    else:
        raise AssertionError("candidate node should surface JSON parse failures")

    run_dir = tmp_path / "r1"
    assert (run_dir / "candidate_B.raw.txt").read_text(encoding="utf-8") == "I cannot produce that as JSON."
    meta = (run_dir / "candidate_B.meta.json").read_text(encoding="utf-8")
    assert '"model": "claude-haiku-4-5"' in meta
    assert '"parse_error": "no JSON found in model response"' in meta
    assert not (run_dir / "candidate_B.json").exists()
    failure_record = next(
        record for record in caplog.records
        if record.getMessage() == "candidate JSON parse failed"
    )
    assert failure_record.candidate_id == "B"
    assert failure_record.model == "claude-haiku-4-5"
    assert failure_record.run_id == "r1"
    assert failure_record.raw_path.endswith("candidate_B.raw.txt")
    assert failure_record.parse_error == "no JSON found in model response"


def test_judge_node_writes_canonical_and_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)

    def fake_run_text(*, system, user, model, max_tokens, json_mode):
        assert model == config.JUDGE_MODEL
        assert json_mode is True
        return json.dumps({
            "selected_baseline": "B",
            "rationale": "B covers risk better",
            "canonical": {"title": "T", "executive_summary": "es", "components": [],
                          "risks": [{"title": "r", "severity": "high", "mitigation": "m"}]},
            "guidance": {"emphasis": ["cost"], "must_fix": [], "section_notes": {}},
        }), []

    monkeypatch.setattr(nodes.llm, "run_text", fake_run_text)
    state = {
        "project_id": "p1", "run_id": "r1", "brief_text": "b", "title": "T",
        "digest": "D",
        "candidates": [
            {"id": "A", "model": "deepseek-chat", "design": {"title": "A"}},
            {"id": "B", "model": "claude-haiku-4-5", "design": {"title": "B"}},
        ],
    }
    out = nodes.judge_node(state)
    assert out["canonical"]["title"] == "T"
    assert out["guidance"]["emphasis"] == ["cost"]
    keys = {e["section"] for e in out["manifest"]}
    assert "executive_summary" in keys and "risks" in keys


def test_judge_node_preserves_raw_output_when_json_parse_fails(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    caplog.set_level(logging.INFO, logger="app.graph.nodes")

    def fake_run_text(**kwargs):
        assert kwargs["model"] == config.JUDGE_MODEL
        assert kwargs["json_mode"] is True
        return "The stronger candidate is B, but this is not JSON.", []

    monkeypatch.setattr(nodes.llm, "run_text", fake_run_text)
    state = {
        "project_id": "p1", "run_id": "r1", "brief_text": "b", "title": "T",
        "digest": "D",
        "candidates": [
            {"id": "A", "model": "deepseek-v4-pro", "design": {"title": "A"}},
            {"id": "B", "model": "claude-haiku-4-5", "design": {"title": "B"}},
        ],
    }

    try:
        nodes.judge_node(state)
    except ValueError as exc:
        assert str(exc) == "no JSON found in model response"
    else:
        raise AssertionError("judge node should surface JSON parse failures")

    run_dir = tmp_path / "r1"
    assert (run_dir / "judge.raw.txt").read_text(encoding="utf-8") == (
        "The stronger candidate is B, but this is not JSON."
    )
    meta = (run_dir / "judge.meta.json").read_text(encoding="utf-8")
    assert '"model": "' + config.JUDGE_MODEL + '"' in meta
    assert '"parse_error": "no JSON found in model response"' in meta
    assert not (run_dir / "judgment.json").exists()
    failure_record = next(
        record for record in caplog.records
        if record.getMessage() == "judge JSON parse failed"
    )
    assert failure_record.run_id == "r1"
    assert failure_record.raw_path.endswith("judge.raw.txt")


def test_judge_node_adds_strict_json_constraints(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    seen = {}

    def fake_run_text(**kwargs):
        seen["system"] = kwargs["system"]
        return (
            '{"selected_baseline": "B", "rationale": "r", '
            '"canonical": {"title": "T"}, "guidance": {}}'
        ), []

    monkeypatch.setattr(nodes.llm, "run_text", fake_run_text)
    state = {
        "project_id": "p1", "run_id": "r1", "brief_text": "b", "title": "T",
        "digest": "D",
        "candidates": [
            {"id": "A", "model": "deepseek-v4-pro", "design": {"title": "A"}},
            {"id": "B", "model": "claude-haiku-4-5", "design": {"title": "B"}},
        ],
    }
    nodes.judge_node(state)

    assert "JSON validity contract for judge output" in seen["system"]
    assert "Do not wrap the JSON in markdown or code fences" in seen["system"]
    assert "Escape every literal double quote inside string values as \\\"" in seen["system"]


def test_document_node_writes_all_sections(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    calls = []

    def fake_run_text(*, system, user, model, max_tokens, **kwargs):
        assert model == config.DOCUMENT_MODEL
        # document sections reason at medium effort (the design is already settled)
        assert kwargs.get("deepseek_thinking") == "enabled"
        assert kwargs.get("effort") == "medium"
        # heading is embedded directly in the user for DeepSeek path
        heading = user.split("Write the section titled: ")[1].splitlines()[0].strip()
        calls.append(heading)
        return f"## {heading}\n\nok", []

    monkeypatch.setattr(nodes.llm, "run_text", fake_run_text)
    state = {
        "project_id": "p1", "run_id": "r1", "title": "T", "digest": "D",
        "manifest": [{"section": "risks", "chars": 10, "summary": "1 risk"}],
        "guidance": {"emphasis": ["cost"], "must_fix": [], "section_notes": {}},
        "canonical": {"risks": [{"title": "r"}]},
    }
    # pre-write a section file so read_section returns content
    nodes._store(state).write_section("risks", "## Risks\nlock-in")
    out = nodes.document_node(state)
    assert len(calls) == len(config.DOC_SECTIONS)
    assert "## Executive summary" in out["document_md"]
    assert "## Key decisions, risks & open questions" in out["document_md"]
    run_dir = tmp_path / "r1"
    assert (run_dir / "document_executive_summary.raw.txt").read_text(encoding="utf-8") == (
        "## Executive summary\n\nok"
    )
    meta = json.loads((run_dir / "document_executive_summary.meta.json").read_text(encoding="utf-8"))
    assert meta["model"] == config.DOCUMENT_MODEL
    assert meta["tool_loop"] is False
    assert meta["section"] == "executive_summary"
    assert (run_dir / "document.raw.txt").exists()


def test_deck_node_disables_deepseek_thinking_for_deepseek_v4(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    seen = {}

    def fake_run_text(*, system, user, model, max_tokens, json_mode, **kwargs):
        seen.update(kwargs)
        seen["model"] = model
        seen["json_mode"] = json_mode
        return json.dumps({"theme_css": "", "slides": ["<section class=\"slide\">Slide</section>"]}), []

    monkeypatch.setattr(nodes.llm, "run_text", fake_run_text)
    out = nodes.deck_node({
        "project_id": "p1",
        "run_id": "r1",
        "title": "T",
        "document_md": "## Executive summary\n\ndoc",
    })

    assert seen["model"] == config.DECK_MODEL
    assert seen["json_mode"] is True
    # deck is pure text->slides reformatting — thinking disabled for speed
    assert seen["deepseek_thinking"] == "disabled"
    assert "slide" in out["deck_html"]


def test_reviews_node_runs_each_lens(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    seen_lenses = []

    def fake_run_text(*, system, user, model, max_tokens, json_mode, **kwargs):
        assert json_mode is True
        # each lens is reviewed with DeepSeek thinking at max effort
        assert kwargs.get("deepseek_thinking") == "enabled"
        assert kwargs.get("effort") == "max"
        # the lens label is interpolated into the system prompt
        seen_lenses.append(system)
        return json.dumps({
            "summary": "s", "verdict": "comment", "report_md": "r",
            "annotations": [{"anchor": "Risks", "domain": "cost", "severity": "warn",
                             "title": "t", "body": "b", "suggestion": "sg"}],
        }), []

    monkeypatch.setattr(nodes.llm, "run_text", fake_run_text)
    out = nodes.reviews_node({"project_id": "p1", "run_id": "r1", "document_md": "## Risks"})
    assert len(out["reviews"]) == len(config.STAKEHOLDER_LENSES)
    assert len(out["annotations"]) == len(config.STAKEHOLDER_LENSES)
    # every configured lens role is present
    assert {r["role"] for r in out["reviews"]} == set(config.STAKEHOLDER_LENSES)
    for lens in config.STAKEHOLDER_LENSES:
        assert (tmp_path / "r1" / f"review_{lens}.raw.txt").exists()
        meta = json.loads((tmp_path / "r1" / f"review_{lens}.meta.json").read_text(encoding="utf-8"))
        assert meta["model"] == config.REVIEW_MODEL_FUSION
        assert meta["lens"] == lens
        assert meta["parsed"] is True


def test_reviews_node_preserves_raw_output_when_lens_parse_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(config, "STAKEHOLDER_LENSES", {"security": "security focus"})

    def fake_run_text(**kwargs):
        return "not json", []

    monkeypatch.setattr(nodes.llm, "run_text", fake_run_text)
    out = nodes.reviews_node({"project_id": "p1", "run_id": "r1", "document_md": "## Risks"})

    assert out["reviews"][0]["summary"] == "(review failed: no JSON found in model response)"
    run_dir = tmp_path / "r1"
    assert (run_dir / "review_security.raw.txt").read_text(encoding="utf-8") == "not json"
    meta = json.loads((run_dir / "review_security.meta.json").read_text(encoding="utf-8"))
    assert meta["parse_error"] == "no JSON found in model response"


def test_persist_node_writes_document_md_without_diagrams(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "graph.db")
    db.init_db()
    project_id = db.new_id("prj_")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO projects (id, title, brief_json, created_at, updated_at) VALUES (?,?,?,?,?)",
            (project_id, "Graph POC", "{}", db.now(), db.now()),
        )

    out = nodes.persist_node({
        "project_id": project_id,
        "run_id": "r1",
        "title": "Graph POC",
        "canonical": {"title": "Graph POC", "components": [{"name": "API"}]},
        "document_md": "## Executive summary\n\n```mermaid\nflowchart LR\nA-->B\n```",
        "deck_html": "<section class=\"slide\">Slide</section>",
        "deck_css": "",
        "reviews": [],
        "annotations": [],
        "candidates": [],
    })

    with db.connect() as conn:
        poc = conn.execute("SELECT document_md, document_html, diagrams_json FROM pocs WHERE id=?", (out["poc_id"],)).fetchone()
    assert poc["document_md"].startswith("## Executive summary")
    assert "```mermaid" in poc["document_md"]
    assert poc["document_html"] == ""
    assert poc["diagrams_json"] == "[]"
