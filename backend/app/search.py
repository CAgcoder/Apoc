"""Provider-neutral web grounding via SearXNG discovery + Crawl4AI crawling."""

from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from . import config

MAX_FRAGMENT_CHARS = 6000
LOW_QUALITY_PREFIX = (
    "Low-quality fallback: the page body could not be crawled, so this content "
    "comes from the search result snippet.\n\n"
)


def normalize_url(url: str) -> str:
    """Drop fragments and tracking params so source IDs stay stable."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith("utm_")],
        doseq=True,
    )
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "", parsed.params, query, ""))


def discover(query: str, k: int | None = None) -> list[dict[str, Any]]:
    """Return normalized, de-duplicated SearXNG search results for one query."""
    top_k = k or config.SEARCH_TOPK
    try:
        response = httpx.get(
            f"{config.SEARXNG_URL}/search",
            params={"q": query, "format": "json"},
            headers={"Accept": "application/json", "User-Agent": "APoc research/0.1"},
            timeout=config.CRAWL_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    by_url: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(payload.get("results", []) if isinstance(payload, dict) else []):
        if not isinstance(item, dict):
            continue
        url = normalize_url(str(item.get("url") or ""))
        if not url:
            continue
        score = _float(item.get("score"))
        if url in by_url and score <= by_url[url]["score"]:
            continue
        by_url[url] = {
            "url": url,
            "title": str(item.get("title") or url).strip(),
            "snippet": str(item.get("content") or item.get("snippet") or "").strip(),
            "publishedDate": item.get("publishedDate") or item.get("published_date") or "",
            "engine": item.get("engine") or item.get("engines") or "",
            "score": score,
            "_index": index,
        }
    results = list(by_url.values())
    results.sort(key=lambda r: (r["score"], -r["_index"]), reverse=True)
    for item in results:
        item.pop("_index", None)
    return results[:top_k]


def crawl(urls: list[str]) -> list[dict[str, Any]]:
    """Crawl URLs with Crawl4AI and return best-effort page bodies + metadata."""
    clean_urls = [normalize_url(url) for url in urls]
    clean_urls = [url for url in clean_urls if url]
    if not clean_urls:
        return []
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            return asyncio.run(_crawl_many(clean_urls))
        except Exception:
            return []
    try:
        return _run_crawl_in_thread(clean_urls)
    except Exception:
        return []


def _run_crawl_in_thread(urls: list[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    error: BaseException | None = None

    def runner() -> None:
        nonlocal result, error
        try:
            result = asyncio.run(_crawl_many(urls))
        except BaseException as exc:  # noqa: BLE001 - converted to [] by caller
            error = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error
    return result


async def _crawl_many(urls: list[str]) -> list[dict[str, Any]]:
    from crawl4ai import AsyncWebCrawler

    output: list[dict[str, Any]] = []
    async with AsyncWebCrawler() as crawler:
        for start in range(0, len(urls), max(1, config.CRAWL_CONCURRENCY)):
            batch = urls[start:start + max(1, config.CRAWL_CONCURRENCY)]
            try:
                raw = await asyncio.wait_for(_maybe_await(crawler.arun_many(batch)), timeout=config.CRAWL_TIMEOUT * len(batch))
            except Exception:
                raw = []
            output.extend(_coerce_crawl_results(raw, batch))
    return output


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _coerce_crawl_results(raw: Any, urls: list[str]) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes, dict)):
        items = list(raw)
    else:
        items = [raw]
    results: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        url = normalize_url(str(_attr(item, "url", "") or (urls[index] if index < len(urls) else "")))
        if not url:
            continue
        results.append(
            {
                "url": url,
                "content_md": _extract_markdown(item),
                "metadata": _extract_metadata_dict(item),
                "html": str(_attr(item, "html", "") or _attr(item, "cleaned_html", "") or ""),
                "success": bool(_attr(item, "success", True)),
                "error": str(_attr(item, "error_message", "") or _attr(item, "error", "") or ""),
            }
        )
    return results


def _extract_markdown(item: Any) -> str:
    markdown = _attr(item, "markdown", "")
    fit = _attr(markdown, "fit_markdown", None)
    if fit:
        return str(fit).strip()
    if isinstance(markdown, dict):
        for key in ("fit_markdown", "raw_markdown", "markdown"):
            if markdown.get(key):
                return str(markdown[key]).strip()
    if markdown:
        return str(markdown).strip()
    return ""


def _extract_metadata_dict(item: Any) -> dict[str, Any]:
    metadata = _attr(item, "metadata", {}) or {}
    return metadata if isinstance(metadata, dict) else {}


def gather(queries: list[str], k: int | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Discover, crawl, merge metadata, and assign stable ``s1`` source IDs."""
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in queries:
        for result in discover(str(query), k=k):
            url = normalize_url(str(result.get("url") or ""))
            if not url or url in seen:
                continue
            seen.add(url)
            result["url"] = url
            candidates.append(result)

    crawled_by_url = {item["url"]: item for item in crawl([c["url"] for c in candidates])}
    fragments: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for candidate in candidates:
        crawled = crawled_by_url.get(candidate["url"], {})
        content = str(crawled.get("content_md") or "").strip()
        if not content:
            fallback = str(candidate.get("snippet") or candidate.get("title") or "").strip()
            if not fallback:
                continue
            content = LOW_QUALITY_PREFIX + fallback
        content = content[:MAX_FRAGMENT_CHARS]
        metadata = _merge_metadata(candidate, crawled.get("metadata") or {}, crawled.get("html") or "", candidate["url"])
        source_id = f"s{len(fragments) + 1}"
        fragments.append(
            {
                "source_id": source_id,
                "url": metadata["url"],
                "title": metadata["title"],
                "date": metadata["date"],
                "sitename": metadata["sitename"],
                "content_md": content,
            }
        )
        sources.append(
            {
                "source_id": source_id,
                "title": metadata["title"],
                "url": metadata["url"],
                "date": metadata["date"],
                "sitename": metadata["sitename"],
                "author": metadata["author"],
            }
        )
    return fragments, sources


def _merge_metadata(searx: dict[str, Any], crawl_meta: dict[str, Any], html: str, url: str) -> dict[str, str]:
    """Merge SearXNG, Crawl4AI metadata, and light trafilatura fallbacks."""
    normalized = normalize_url(str(searx.get("url") or url))
    hostname = urlparse(normalized).hostname or normalized
    date = _clean(searx.get("publishedDate")) or _metadata_value(
        crawl_meta,
        "article:published_time",
        "published_time",
        "publishedDate",
        "datePublished",
        "dateModified",
        "published_date",
        "publish_date",
        "publication_date",
        "date",
    )
    author = _metadata_value(crawl_meta, "author", "article:author", "byline", "dc.creator", "creator")
    if html and (not date or not author):
        tmeta = _trafilatura_metadata(html)
        date = date or _clean(getattr(tmeta, "date", None))
        author = author or _clean(getattr(tmeta, "author", None))
    sitename = _metadata_value(crawl_meta, "og:site_name", "site_name", "sitename", "application-name") or hostname
    title = _clean(searx.get("title")) or _metadata_value(crawl_meta, "title", "og:title") or normalized
    return {
        "source_id": "",
        "title": title,
        "url": normalized,
        "date": date or "",
        "sitename": sitename or "",
        "author": author or "",
    }


def _trafilatura_metadata(html: str) -> Any | None:
    try:
        import trafilatura

        return trafilatura.extract_metadata(html)
    except Exception:
        return None


def _metadata_value(meta: Any, *keys: str) -> str:
    wanted = {_norm_key(key) for key in keys}
    found = _find_metadata_value(meta, wanted)
    return _clean(found)


def _find_metadata_value(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        for key, child in value.items():
            if _norm_key(str(key)) in keys:
                scalar = _as_scalar(child)
                if scalar:
                    return scalar
        for child in value.values():
            found = _find_metadata_value(child, keys)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_metadata_value(child, keys)
            if found:
                return found
    return None


def _as_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in ("name", "@value", "value", "content"):
            if value.get(key):
                return _as_scalar(value[key])
    if isinstance(value, list):
        for item in value:
            scalar = _as_scalar(item)
            if scalar:
                return scalar
    return ""


def _norm_key(key: str) -> str:
    return key.lower().replace("_", "").replace("-", "").replace(":", "").replace("@", "")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _attr(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)
