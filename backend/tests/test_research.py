from app import research


def test_run_research_exposes_query_generation_raw(monkeypatch):
    records = []
    calls = []

    def raw_sink(name, raw_text, meta):
        records.append((name, raw_text, meta))

    def fake_run_text(**kwargs):
        calls.append(kwargs)
        if kwargs.get("json_mode"):
            return '{"queries": ["reference architecture"]}', []
        return "DIGEST", []

    monkeypatch.setattr(research.config, "ANTHROPIC_NATIVE_SEARCH", False)
    monkeypatch.setattr(research.llm, "run_text", fake_run_text)
    monkeypatch.setattr(research.search, "gather", lambda queries, k: (
        [{"source_id": "S1", "title": "Ref", "url": "https://example.test", "content_md": "body"}],
        [{"url": "https://example.test", "title": "Ref"}],
    ))

    digest, sources = research.run_research(
        "brief", "topic", model="deepseek-v4-pro", raw_sink=raw_sink
    )

    assert digest == "DIGEST"
    assert sources == [{"url": "https://example.test", "title": "Ref"}]
    assert records[0][0] == "research_queries"
    assert records[0][1] == '{"queries": ["reference architecture"]}'
    assert records[0][2]["model"] == "deepseek-v4-pro"
    assert records[0][2]["json_mode"] is True
    assert calls[0]["json_mode"] is True
    assert calls[0]["deepseek_thinking"] == "enabled"
    assert calls[0]["effort"] == "max"
    assert calls[1].get("json_mode", False) is False
    assert calls[1]["deepseek_thinking"] == "enabled"
    assert calls[1]["effort"] == "max"
