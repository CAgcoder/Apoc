from app.graph import build as build_mod
from app import config


def test_graph_runs_end_to_end_with_stubbed_nodes(monkeypatch):
    monkeypatch.setattr(config, "CANDIDATE_MODELS", ["deepseek-chat", "claude-haiku-4-5"])

    monkeypatch.setattr(build_mod.nodes, "research_node",
                        lambda s: {"digest": "D", "sources": []})

    def fake_make_candidate(index, model):
        cid = build_mod.nodes._CAND_IDS[index]
        return lambda s: {"candidates": [{"id": cid, "model": model, "design": {"title": cid}}]}

    monkeypatch.setattr(build_mod.nodes, "make_candidate_node", fake_make_candidate)
    monkeypatch.setattr(build_mod.nodes, "judge_node",
                        lambda s: {"canonical": {"title": "T"}, "guidance": {}, "manifest": [], "title": "T"})
    monkeypatch.setattr(build_mod.nodes, "document_node",
                        lambda s: {"document_md": "## Executive summary"})
    monkeypatch.setattr(build_mod.nodes, "deck_node",
                        lambda s: {"deck_html": "<section class=\"slide\">Slide</section>", "deck_css": ""})
    monkeypatch.setattr(build_mod.nodes, "reviews_node",
                        lambda s: {"reviews": [{"role": "cto"}], "annotations": []})
    monkeypatch.setattr(build_mod.nodes, "persist_node", lambda s: {"poc_id": "poc_x"})

    graph = build_mod.build_graph()
    final = graph.invoke(
        {"project_id": "p1", "run_id": "r1", "brief_text": "b", "title": "T"},
        config={"configurable": {"thread_id": "r1"}},
    )
    assert final["poc_id"] == "poc_x"
    assert len(final["candidates"]) == 2  # both parallel candidates collected
    assert final["document_md"].startswith("##")
