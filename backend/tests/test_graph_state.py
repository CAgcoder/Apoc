from app.graph.state import PocState, merge_candidates


def test_pocstate_is_constructible():
    s: PocState = {
        "project_id": "p1", "run_id": "r1", "brief_text": "b",
        "title": "T", "digest": "", "sources": [], "candidates": [],
        "canonical": {}, "guidance": {}, "manifest": [],
        "document_md": "", "reviews": [], "annotations": [], "poc_id": "",
    }
    assert s["project_id"] == "p1"


def test_merge_candidates_reducer_appends():
    assert merge_candidates([{"id": "A"}], [{"id": "B"}]) == [{"id": "A"}, {"id": "B"}]
    assert merge_candidates(None, [{"id": "A"}]) == [{"id": "A"}]
