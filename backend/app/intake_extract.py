"""Extract structured POC scoping fields from an uploaded requirements PDF.

Text-based PDFs only (no OCR). Uses ``pypdf`` for text extraction and the
pluggable LLM (``app.llm``) for structured extraction, then normalizes the model
output onto the same 8-key brief contract the generation pipeline already
consumes, plus a non-lossy ``requirements_detail``.
"""

from __future__ import annotations

import hashlib
import io
import json
from typing import Any

from . import config, llm, prompts
from .intake import BRIEF_KEYS

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_EXTRACT_CHARS = 12_000
MAX_TOTAL_EXTRACT_CHARS = 60_000
MIN_TEXT_CHARS = 80


class ExtractError(Exception):
    """User-facing extraction failure (maps to HTTP 400)."""


def extract_pages(data: bytes) -> tuple[list[dict[str, Any]], int]:
    """Return page-marked text records and page_count from PDF bytes."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ExtractError("This PDF is encrypted. Please upload an unlocked copy.")
        pdf_pages = reader.pages
        pages = [
            {"page": index + 1, "text": page.extract_text() or ""}
            for index, page in enumerate(pdf_pages)
        ]
    except ExtractError:
        raise
    except PdfReadError as exc:
        raise ExtractError("Could not read this PDF.") from exc
    except Exception as exc:  # noqa: BLE001 - malformed PDFs map to a user-facing error
        raise ExtractError("Could not extract requirements from this PDF.") from exc

    text = "\n".join(str(page["text"]) for page in pages)
    if len(text.strip()) < MIN_TEXT_CHARS:
        raise ExtractError(
            "This PDF has no extractable text. It may be scanned; please upload a "
            "text-based PDF or use the guided chat instead."
        )
    return pages, len(pdf_pages)


def extract_text(data: bytes) -> tuple[str, int]:
    """Return (text, page_count) from PDF bytes. Raise ExtractError on no text."""
    pages, page_count = extract_pages(data)
    return "\n".join(str(page["text"]) for page in pages), page_count


def _normalize_field_evidence(raw: Any) -> dict[str, dict[str, Any]]:
    raw = raw if isinstance(raw, dict) else {}
    allowed = {"title", "client_name", "consulting_org"} | {f"brief.{key}" for key in BRIEF_KEYS}
    out: dict[str, dict[str, Any]] = {}
    for field, evidence in raw.items():
        if field not in allowed or not isinstance(evidence, dict):
            continue
        quote = str(evidence.get("quote", "") or "").strip()
        if not quote:
            continue
        page_raw = evidence.get("page")
        try:
            page = int(page_raw) if page_raw not in (None, "") else None
        except (TypeError, ValueError):
            page = None
        confidence = str(evidence.get("confidence", "") or "").strip().lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "low"
        out[field] = {"quote": quote, "page": page, "confidence": confidence}
    return out


def normalize_extract(raw: Any) -> dict[str, Any]:
    """Force the model dict onto the response contract with empty defaults."""
    raw = raw if isinstance(raw, dict) else {}
    brief_in = raw.get("brief")
    brief_in = brief_in if isinstance(brief_in, dict) else {}
    brief = {k: str(brief_in.get(k, "") or "").strip() for k in BRIEF_KEYS}
    return {
        "title": str(raw.get("title", "") or "").strip(),
        "client_name": str(raw.get("client_name", "") or "").strip(),
        "consulting_org": str(raw.get("consulting_org", "") or "").strip(),
        "brief": brief,
        "requirements_detail": str(raw.get("requirements_detail", "") or "").strip(),
        "field_evidence": _normalize_field_evidence(raw.get("field_evidence")),
    }


def _format_pages(pages: list[dict[str, Any]], max_total_chars: int) -> tuple[str, int, bool]:
    blocks: list[str] = []
    used_chars = 0
    truncated = False
    for page in pages:
        if used_chars >= max_total_chars:
            truncated = True
            break
        text = str(page.get("text", "") or "")
        remaining = max_total_chars - used_chars
        if len(text) > remaining:
            text = text[:remaining]
            truncated = True
        used_chars += len(text)
        blocks.append(f"### Page {page.get('page')}\n{text.strip()}")
    return "\n\n".join(blocks), used_chars, truncated


def _chunk_text(text: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for block in text.split("\n\n### Page "):
        block = block if block.startswith("### Page ") else f"### Page {block}"
        if current and current_len + len(block) + 2 > max_chars:
            chunks.append("\n\n".join(current))
            current = [block]
            current_len = len(block)
        else:
            current.append(block)
            current_len += len(block) + (2 if current_len else 0)
    if current:
        chunks.append("\n\n".join(current))
    return chunks or [text]


def _merge_extracts(parts: list[dict[str, Any]]) -> dict[str, Any]:
    merged = {
        "title": "",
        "client_name": "",
        "consulting_org": "",
        "brief": {key: "" for key in BRIEF_KEYS},
        "requirements_detail": "",
        "field_evidence": {},
    }
    details: list[str] = []
    evidence: dict[str, dict[str, Any]] = {}
    for part in parts:
        for key in ("title", "client_name", "consulting_org"):
            if not merged[key] and part.get(key):
                merged[key] = part[key]
        for key in BRIEF_KEYS:
            value = (part.get("brief") or {}).get(key, "")
            if not merged["brief"][key] and value:
                merged["brief"][key] = value
        detail = str(part.get("requirements_detail", "") or "").strip()
        if detail:
            details.append(detail)
        for field, item in (part.get("field_evidence") or {}).items():
            evidence.setdefault(field, item)
    merged["requirements_detail"] = "\n\n---\n\n".join(details)
    merged["field_evidence"] = evidence
    return merged


def extract_from_pdf(data: bytes, *, filename: str) -> dict[str, Any]:
    """Full pipeline: validate, extract text, call LLM, normalize, add provenance."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ExtractError("PDF is too large (max 10 MB).")

    pages, page_count = extract_pages(data)
    text = "\n".join(str(page["text"]) for page in pages)
    chars_extracted = sum(len(str(page["text"])) for page in pages)
    text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    used, chars_used, truncated = _format_pages(pages, MAX_TOTAL_EXTRACT_CHARS)
    artifact_dir = config.RUNS_DIR / "intake" / f"intake_{text_sha[:16]}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    extracted_text_path = artifact_dir / "extracted_text.txt"
    extracted_text_path.write_text(used, encoding="utf-8")

    chunks = _chunk_text(used, MAX_EXTRACT_CHARS)
    raw_paths: list[str] = []
    parts: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        raw_text, _ = llm.run_text(
            system=prompts.EXTRACT_SYSTEM,
            user=chunk,
            model=config.EXTRACTION_MODEL,
            max_tokens=4000,
            json_mode=True,
            temperature=0,
            effort=config.EXTRACTION_REASONING_EFFORT,
            deepseek_thinking=config.EXTRACTION_DEEPSEEK_THINKING,
        )
        raw_path = artifact_dir / f"chunk_{index:03d}.raw.txt"
        raw_path.write_text(raw_text, encoding="utf-8")
        raw_paths.append(str(raw_path))
        parts.append(normalize_extract(llm.extract_json(raw_text)))

    result = _merge_extracts(parts)
    merged_path = artifact_dir / "merged_extract.json"
    merged_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["extraction_meta"] = {
        "source_type": "uploaded_pdf",
        "filename": filename,
        "size_bytes": len(data),
        "page_count": page_count,
        "text_sha256": text_sha,
        "chars_extracted": chars_extracted,
        "chars_used": chars_used,
        "truncated": truncated,
        "chunk_count": len(chunks),
        "artifact_dir": str(artifact_dir),
        "extracted_text_path": str(extracted_text_path),
        "raw_response_paths": raw_paths,
        "merged_extract_path": str(merged_path),
        "model": config.EXTRACTION_MODEL,
        "provider": config.PROVIDER,
        "deepseek_thinking": config.EXTRACTION_DEEPSEEK_THINKING,
        "reasoning_effort": config.EXTRACTION_REASONING_EFFORT,
    }
    return result
