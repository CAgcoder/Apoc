"""SQLite data layer.

One file, no migrations framework — ``init_db`` creates everything idempotently.
Every mutation of consequence also writes an ``audit_events`` row so a finished
POC can be traced end to end.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS stakeholders (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    role        TEXT NOT NULL,
    org         TEXT NOT NULL DEFAULT 'client',   -- 'client' | 'consulting'
    email       TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    client_name   TEXT NOT NULL DEFAULT '',
    consulting_org TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'draft',  -- draft|generating|in_review|ready_to_align|failed
    brief_json    TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pocs (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    title       TEXT NOT NULL DEFAULT '',
    deck_html   TEXT NOT NULL DEFAULT '',   -- editable slide fragments + theme, assembled on serve
    deck_css    TEXT NOT NULL DEFAULT '',
    markdown    TEXT NOT NULL DEFAULT '',   -- legacy plain-text POC (kept for back-compat)
    document_html TEXT NOT NULL DEFAULT '', -- LEGACY HTML POC document (superseded by document_md)
    document_md TEXT NOT NULL DEFAULT '',   -- Markdown POC document (review source of truth)
    diagrams_json TEXT NOT NULL DEFAULT '[]', -- LEGACY React Flow diagrams (diagrams now inline mermaid)
    design_json TEXT NOT NULL DEFAULT '{}', -- structured architecture
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_notes (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL,
    poc_id      TEXT,
    topic       TEXT NOT NULL DEFAULT '',
    digest      TEXT NOT NULL DEFAULT '',
    citations_json TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_reports (
    id          TEXT PRIMARY KEY,
    poc_id      TEXT NOT NULL,
    role        TEXT NOT NULL,
    summary     TEXT NOT NULL DEFAULT '',
    verdict     TEXT NOT NULL DEFAULT 'comment',  -- approve|revise|block|comment
    report_md   TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS annotations (
    id          TEXT PRIMARY KEY,
    poc_id      TEXT NOT NULL,
    anchor      TEXT NOT NULL DEFAULT '',   -- section heading / slug the note attaches to
    domain      TEXT NOT NULL DEFAULT '',   -- compliance|security|cost|architecture|...
    severity    TEXT NOT NULL DEFAULT 'info', -- block|warn|info
    title       TEXT NOT NULL DEFAULT '',
    body        TEXT NOT NULL DEFAULT '',
    suggestion  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS comments (
    id            TEXT PRIMARY KEY,
    poc_id        TEXT NOT NULL,
    annotation_id TEXT,                    -- nullable: a general comment or a reply to an annotation
    stakeholder_id TEXT NOT NULL,
    body          TEXT NOT NULL,
    anchor_line   INTEGER,
    anchor_slug   TEXT,
    status        TEXT NOT NULL DEFAULT 'open',  -- open|accepted|closed
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    id            TEXT PRIMARY KEY,
    poc_id        TEXT NOT NULL,
    stakeholder_id TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending', -- pending|approved|changes_requested
    note          TEXT NOT NULL DEFAULT '',
    updated_at    TEXT NOT NULL,
    UNIQUE(poc_id, stakeholder_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id          TEXT PRIMARY KEY,
    project_id  TEXT,
    poc_id      TEXT,
    actor       TEXT NOT NULL DEFAULT 'system',
    action      TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Columns added after the initial schema — applied idempotently to existing DBs.
_MIGRATIONS = [
    ("pocs", "document_html", "TEXT NOT NULL DEFAULT ''"),
    ("pocs", "diagrams_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("projects", "intake_chat_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("projects", "requirements_detail", "TEXT NOT NULL DEFAULT ''"),
    ("projects", "source_provenance_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("pocs", "document_md", "TEXT NOT NULL DEFAULT ''"),
    ("comments", "anchor_line", "INTEGER"),
    ("comments", "anchor_slug", "TEXT"),
    ("comments", "status", "TEXT NOT NULL DEFAULT 'open'"),
]


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        for table, column, decl in _MIGRATIONS:
            try:
                conn.execute(f'ALTER TABLE "{table}" ADD COLUMN {column} {decl}')
            except sqlite3.OperationalError:
                pass  # column already exists


def record_audit(
    conn: sqlite3.Connection,
    *,
    action: str,
    project_id: str | None = None,
    poc_id: str | None = None,
    actor: str = "system",
    detail: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        "INSERT INTO audit_events (id, project_id, poc_id, actor, action, detail_json, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (new_id("ev_"), project_id, poc_id, actor, action, json.dumps(detail or {}), now()),
    )


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]
