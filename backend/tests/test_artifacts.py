import json
import pytest
from app.artifacts import ArtifactStore


def test_write_and_read_section(tmp_path):
    store = ArtifactStore(tmp_path, run_id="r1")
    store.write_section("risks", "## Risks\nvendor lock-in")
    assert "vendor lock-in" in store.read_section("risks")


def test_read_section_unknown_returns_marker(tmp_path):
    store = ArtifactStore(tmp_path, run_id="r1")
    out = store.read_section("does_not_exist")
    assert "no such section" in out.lower()


def test_read_section_is_path_jailed(tmp_path):
    store = ArtifactStore(tmp_path, run_id="r1")
    out = store.read_section("../../etc/passwd")
    assert "no such section" in out.lower()  # traversal rejected, not raised


def test_manifest_from_canonical_design(tmp_path):
    store = ArtifactStore(tmp_path, run_id="r1")
    canonical = {
        "title": "X",
        "executive_summary": "We propose a queue-based pipeline.",
        "risks": [{"title": "lock-in", "severity": "high", "mitigation": "abstract"}],
    }
    manifest = store.build_manifest(canonical, summaries={"risks": "1 high risk"})
    keys = {e["section"] for e in manifest}
    assert "executive_summary" in keys and "risks" in keys
    risks_entry = next(e for e in manifest if e["section"] == "risks")
    assert risks_entry["chars"] > 0
    assert risks_entry["summary"] == "1 high risk"
    # build_manifest also persisted each section as a readable file
    assert "lock-in" in store.read_section("risks")
    # and wrote manifest.json
    assert json.loads((store.dir / "manifest.json").read_text())[0]["section"]


def test_doc_sections_all_resolve_after_manifest(tmp_path):
    """Every DOC_SECTIONS key's canonical source files must exist after the
    manifest is built — otherwise the document writer reads '(no such section)'."""
    from app import config
    from app.artifacts import ArtifactStore

    # A canonical design populated with every field the judge can emit.
    canonical = {
        "title": "T", "executive_summary": "es", "context": "ctx",
        "requirements_mapping": [{"requirement": "r", "how_addressed": "h"}],
        "components": [{"name": "c", "responsibility": "x", "tech": "y", "type": "backend"}],
        "data_flows": [{"from": "a", "to": "b", "description": "d"}],
        "tech_stack": [{"layer": "l", "choice": "ch", "rationale": "rt"}],
        "nfrs": [{"name": "n", "target": "t"}],
        "decisions": [{"id": "d1", "decision": "de", "rationale": "ra", "alternatives": "al", "risk": "ri"}],
        "risks": [{"title": "rt", "severity": "high", "mitigation": "m"}],
        "cost_estimate": {"summary": "s", "monthly_range": "$"},
        "open_questions": ["q"],
    }
    store = ArtifactStore(tmp_path, run_id="r1")
    store.build_manifest(canonical)
    for key, _heading in config.DOC_SECTIONS:
        for source in config.DOC_SECTION_SOURCES.get(key, [key]):
            content = store.read_section(source)
            assert "no such section" not in content.lower(), (
                f"DOC_SECTIONS key '{key}' -> source '{source}' did not resolve"
            )
