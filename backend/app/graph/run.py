"""Entry point for the fusion generation graph (background-thread target).

Mirrors generation.run_generation's lifecycle bookkeeping (status, audit,
progress) but delegates the actual work to the LangGraph StateGraph.
"""

from __future__ import annotations

import json
import logging

from .. import cancel, config, db, progress

logger = logging.getLogger(__name__)
from ..cancel import GenerationCancelled
from ..generation import _brief_text  # reuse the legacy brief formatter
from .build import build_graph


def run_generation_graph(project_id: str) -> None:
    cancel.clear(project_id)
    progress.reset(project_id)
    progress.publish(project_id, "queued", message="Starting POC generation (fusion)")
    with db.connect() as conn:
        prow = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if prow is None:
            progress.publish(project_id, "failed", message="Project not found")
            return
        project = dict(prow)
        brief = json.loads(project["brief_json"] or "{}")
        conn.execute("UPDATE projects SET status='generating', updated_at=? WHERE id=?",
                     (db.now(), project_id))
        db.record_audit(conn, action="generation.started", project_id=project_id,
                        detail={"mode": "fusion"})

    run_id = db.new_id("run_")
    brief_text = _brief_text(project, brief)
    try:
        graph = build_graph()
        callbacks = []
        if config.LANGFUSE_ENABLED:
            try:
                from langfuse.callback import CallbackHandler
                callbacks.append(CallbackHandler())  # reads LANGFUSE_* from env
            except Exception:  # pragma: no cover - tracing must never abort generation
                logger.warning("langfuse tracing unavailable", exc_info=True)
        graph.invoke(
            {"project_id": project_id, "run_id": run_id, "brief_text": brief_text,
             "title": project["title"],
             "client_name": project.get("client_name") or "",
             "consulting_org": project.get("consulting_org") or ""},
            config={"configurable": {"thread_id": run_id}, "callbacks": callbacks},
        )
    except GenerationCancelled:
        with db.connect() as conn:
            conn.execute("UPDATE projects SET status='draft', updated_at=? WHERE id=?",
                         (db.now(), project_id))
            db.record_audit(conn, action="generation.cancelled", project_id=project_id,
                            detail={"run_id": run_id})
        progress.publish(project_id, "cancelled", message="Generation cancelled")
        cancel.clear(project_id)
    except Exception as exc:  # noqa: BLE001 — surface to UI + audit, same as legacy
        with db.connect() as conn:
            conn.execute("UPDATE projects SET status='failed', updated_at=? WHERE id=?",
                         (db.now(), project_id))
            db.record_audit(conn, action="generation.failed", project_id=project_id,
                            detail={"error": str(exc), "run_id": run_id})
        progress.publish(project_id, "failed", message=f"Generation failed: {exc}")
