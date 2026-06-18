"""Tests for PDF requirements extraction and rich-requirements persistence.

Run: .venv/bin/python -m tests.test_intake_extract   (from apoc/backend)
"""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

from pypdf import PdfWriter

from app import config

# Point the data layer at a throwaway DB before anything opens a connection.
config.DB_PATH = Path(tempfile.mkdtemp()) / "test_intake_extract.db"

from app import db  # noqa: E402
from app import intake_extract  # noqa: E402

db.init_db()


def test_projects_table_has_rich_requirement_columns():
    with db.connect() as conn:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
    assert "requirements_detail" in cols
    assert "source_provenance_json" in cols


def test_pdf_text_empty_layer_raises():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    try:
        intake_extract.extract_text(buf.getvalue())
        assert False, "expected ExtractError"
    except intake_extract.ExtractError as e:
        assert "no extractable text" in str(e).lower()


def test_normalize_extract_forces_eight_brief_keys():
    raw = {
        "title": "Risk POC",
        "client_name": "Acme",
        "brief": {"business_goal": "reduce review load", "bogus": "drop me"},
        "requirements_detail": "dense summary",
        "field_evidence": {
            "brief.business_goal": {"quote": "reduce review load", "page": 2, "confidence": "high"}
        },
    }
    out = intake_extract.normalize_extract(raw)
    assert set(out["brief"].keys()) == set(intake_extract.BRIEF_KEYS)
    assert out["brief"]["business_goal"] == "reduce review load"
    assert out["brief"]["scale"] == ""
    assert "bogus" not in out["brief"]
    assert out["requirements_detail"] == "dense summary"
    assert out["title"] == "Risk POC"
    assert out["consulting_org"] == ""
    assert out["field_evidence"]["brief.business_goal"]["page"] == 2


def test_extract_from_pdf_chunks_merges_and_saves_debug_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(intake_extract, "MAX_EXTRACT_CHARS", 40)
    monkeypatch.setattr(intake_extract, "MAX_TOTAL_EXTRACT_CHARS", 500)
    monkeypatch.setattr(
        intake_extract,
        "extract_pages",
        lambda data: (
            [
                {"page": 1, "text": "business goal page one " * 3},
                {"page": 2, "text": "timeline page two " * 3},
            ],
            2,
        ),
    )
    calls = []

    def fake_run_text(**kwargs):
        calls.append(kwargs)
        assert kwargs["json_mode"] is True
        assert kwargs["temperature"] == 0
        if len(calls) == 1:
            payload = {
                "title": "Chunked POC",
                "brief": {"business_goal": "goal from page one"},
                "requirements_detail": "detail from page one",
                "field_evidence": {
                    "brief.business_goal": {
                        "quote": "business goal page one",
                        "page": 1,
                        "confidence": "high",
                    }
                },
            }
        else:
            payload = {
                "brief": {"timeline": "timeline from page two"},
                "requirements_detail": "detail from page two",
                "field_evidence": {
                    "brief.timeline": {
                        "quote": "timeline page two",
                        "page": 2,
                        "confidence": "medium",
                    }
                },
            }
        return json.dumps(payload), []

    monkeypatch.setattr(intake_extract.llm, "run_text", fake_run_text)

    out = intake_extract.extract_from_pdf(b"%PDF-1.4 fake", filename="requirements.pdf")

    assert len(calls) == 2
    assert all(call["model"] == intake_extract.config.EXTRACTION_MODEL for call in calls)
    assert all(call["deepseek_thinking"] == intake_extract.config.EXTRACTION_DEEPSEEK_THINKING for call in calls)
    assert out["title"] == "Chunked POC"
    assert out["brief"]["business_goal"] == "goal from page one"
    assert out["brief"]["timeline"] == "timeline from page two"
    assert out["requirements_detail"] == "detail from page one\n\n---\n\ndetail from page two"
    assert out["field_evidence"]["brief.timeline"]["confidence"] == "medium"

    meta = out["extraction_meta"]
    assert meta["chunk_count"] == 2
    assert meta["chars_used"] == meta["chars_extracted"]
    assert meta["truncated"] is False
    extracted_path = Path(meta["extracted_text_path"])
    assert extracted_path.exists()
    assert "Page 2" in extracted_path.read_text(encoding="utf-8")
    raw_paths = [Path(p) for p in meta["raw_response_paths"]]
    assert len(raw_paths) == 2
    assert all(path.exists() for path in raw_paths)


def test_extract_endpoint_returns_contract():
    from fastapi.testclient import TestClient

    from app import main

    original_run_text = main.intake_extract.llm.run_text
    main.intake_extract.llm.run_text = lambda **_: (
        json.dumps({
            "title": "Doc POC",
            "brief": {"business_goal": "manage documents"},
            "requirements_detail": "dense",
        }),
        {},
    )
    original_pages = main.intake_extract.extract_pages
    main.intake_extract.extract_pages = lambda data: ([{"page": 1, "text": "requirement text " * 20}], 3)
    try:
        client = TestClient(main.app)
        resp = client.post(
            "/api/intake/extract",
            files={"file": ("requirements.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    finally:
        main.intake_extract.llm.run_text = original_run_text
        main.intake_extract.extract_pages = original_pages
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body["brief"].keys()) == set(main.intake.BRIEF_KEYS)
    assert body["requirements_detail"] == "dense"
    assert body["extraction_meta"]["page_count"] == 3


def test_extract_endpoint_rejects_non_pdf():
    from fastapi.testclient import TestClient

    from app import main

    client = TestClient(main.app)
    resp = client.post(
        "/api/intake/extract",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400
    assert "PDF" in resp.text


def test_create_project_persists_requirements_and_provenance():
    from fastapi.testclient import TestClient

    from app import main

    client = TestClient(main.app)
    resp = client.post(
        "/api/projects",
        json={
            "title": "Doc POC",
            "brief": {k: "" for k in main.intake.BRIEF_KEYS},
            "requirements_detail": "full dense requirements",
            "source_provenance": {"source_type": "uploaded_pdf", "filename": "r.pdf"},
        },
    )
    assert resp.status_code == 200, resp.text
    pid = resp.json()["id"]

    got = client.get(f"/api/projects/{pid}").json()
    assert got["requirements_detail"] == "full dense requirements"
    assert got["source_provenance"]["source_type"] == "uploaded_pdf"

    with db.connect() as conn:
        actions = {
            r["action"]
            for r in conn.execute(
                "SELECT action FROM audit_events WHERE project_id=?", (pid,)
            ).fetchall()
        }
    assert "intake.pdf_extracted" in actions


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
