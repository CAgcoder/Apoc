"""Tests for SearXNG + Crawl4AI research grounding helpers."""

from __future__ import annotations

from app import search


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_discover_parses_dedupes_normalizes_and_sorts():
    original_get = search.httpx.get

    def fake_get(*_, **__):
        return FakeResponse(
            {
                "results": [
                    {
                        "url": "https://example.com/a?utm_source=x&keep=1#frag",
                        "title": "Low duplicate",
                        "content": "old",
                        "score": 0.1,
                    },
                    {
                        "url": "https://vendor.test/ref?utm_campaign=y",
                        "title": "Vendor ref",
                        "content": "snippet",
                        "publishedDate": "2026-01-02",
                        "engine": "test",
                        "score": 0.9,
                    },
                    {
                        "url": "https://example.com/a?keep=1",
                        "title": "High duplicate",
                        "content": "new",
                        "score": 0.8,
                    },
                    {"url": "not-a-url", "title": "Ignored", "score": 1.0},
                ]
            }
        )

    search.httpx.get = fake_get
    try:
        results = search.discover("architecture", k=2)
    finally:
        search.httpx.get = original_get

    assert [r["title"] for r in results] == ["Vendor ref", "High duplicate"]
    assert results[0]["url"] == "https://vendor.test/ref"
    assert results[1]["url"] == "https://example.com/a?keep=1"
    assert results[0]["publishedDate"] == "2026-01-02"


def test_gather_assigns_stable_source_ids_and_falls_back_to_snippet():
    original_discover = search.discover
    original_crawl = search.crawl

    def fake_discover(query, k=None):
        if query == "q1":
            return [
                {
                    "url": "https://example.com/a?utm_source=x",
                    "title": "A",
                    "snippet": "Snippet A",
                    "publishedDate": "2026-02-03",
                    "score": 1.0,
                }
            ]
        return [
            {
                "url": "https://example.com/b",
                "title": "B",
                "snippet": "Snippet B",
                "publishedDate": "",
                "score": 1.0,
            }
        ]

    def fake_crawl(urls):
        return [
            {
                "url": "https://example.com/a",
                "content_md": "Crawled body A",
                "metadata": {"og:site_name": "Example"},
                "html": "",
            },
            {
                "url": "https://example.com/b",
                "content_md": "",
                "metadata": {},
                "html": "",
            },
        ]

    search.discover = fake_discover
    search.crawl = fake_crawl
    try:
        fragments, sources = search.gather(["q1", "q2"])
    finally:
        search.discover = original_discover
        search.crawl = original_crawl

    assert [f["source_id"] for f in fragments] == ["s1", "s2"]
    assert fragments[0]["content_md"] == "Crawled body A"
    assert fragments[1]["content_md"].startswith(search.LOW_QUALITY_PREFIX)
    assert "Snippet B" in fragments[1]["content_md"]
    assert sources[0]["source_id"] == "s1"
    assert sources[0]["date"] == "2026-02-03"
    assert sources[0]["sitename"] == "Example"


def test_merge_metadata_prefers_searx_date_and_hostname_fallback():
    meta = search._merge_metadata(
        {"url": "https://docs.example.com/path?utm_medium=email#x", "title": "SearX title", "publishedDate": "2026-05-01"},
        {"datePublished": "2025-01-01", "author": {"name": "Jane Doe"}},
        "",
        "https://docs.example.com/path",
    )

    assert meta["date"] == "2026-05-01"
    assert meta["author"] == "Jane Doe"
    assert meta["sitename"] == "docs.example.com"
    assert meta["title"] == "SearX title"
    assert meta["url"] == "https://docs.example.com/path"


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
