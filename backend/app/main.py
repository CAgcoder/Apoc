"""APoc FastAPI application.

Routes group into: stakeholders/roles, projects + generation (with SSE
progress), the POC bundle (Markdown document, design, annotations, reviews, approvals,
comments), the editable deck (served + saved), and the audit trail.

Identity is demo-grade: the caller declares a stakeholder via the
``X-Apoc-Role`` header (or ``role`` query param for the deck iframe). The only
capability actually gated on role is *editing the deck* — architect only — which
is the gate the product is meant to demonstrate.
"""

from __future__ import annotations

import asyncio
import json
import threading
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse

from . import ai_assist, cancel, config, db, deck, generation, intake, intake_extract, progress
from .seed import seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    seed_if_empty()
    yield


app = FastAPI(title="APoc", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN, "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _role(request: Request) -> str:
    return request.headers.get("X-Apoc-Role", "") or request.query_params.get("role", "")


# --- stakeholders / roles ---------------------------------------------------

@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "model": config.MODEL, "demo_all_admin": config.DEMO_ALL_ADMIN}


@app.get("/api/roles")
def roles() -> dict[str, Any]:
    return {
        "roles": config.ROLES,
        "review_roles": config.REVIEW_ROLES,
        "approver_roles": config.APPROVER_ROLES,
        "editor_role": config.EDITOR_ROLE,
    }


@app.get("/api/stakeholders")
def stakeholders() -> list[dict[str, Any]]:
    with db.connect() as conn:
        return db.rows_to_dicts(conn.execute("SELECT * FROM stakeholders ORDER BY created_at").fetchall())


# --- conversational intake --------------------------------------------------

@app.post("/api/intake/chat")
def intake_chat(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """One turn of the guided requirement-intake conversation.

    Stateless: the caller sends the full message history and gets back the next
    turn (question + clickable options, or — when complete — a structured brief
    and project title). No DB writes; the transcript is persisted only when the
    project is created.
    """
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise HTTPException(400, "messages must be a list")
    return intake.run_intake_turn(messages)


@app.post("/api/intake/extract")
async def intake_extract_pdf(file: UploadFile = File(...)) -> dict[str, Any]:
    """Extract a prefilled brief + requirements_detail from an uploaded PDF.

    Optional alternative to the guided chat. Text-based PDFs only (no OCR).
    """
    name = (file.filename or "").lower()
    if not name.endswith(".pdf") and (file.content_type or "") != "application/pdf":
        raise HTTPException(400, "Only PDF uploads are supported.")
    data = await file.read()
    try:
        return intake_extract.extract_from_pdf(data, filename=file.filename or "upload.pdf")
    except intake_extract.ExtractError as exc:
        raise HTTPException(400, str(exc)) from exc


# --- projects + generation --------------------------------------------------

@app.post("/api/projects")
def create_project(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "title is required")
    brief = payload.get("brief") or {}
    intake_chat = payload.get("intake_chat") or []
    requirements_detail = str(payload.get("requirements_detail", "") or "")
    provenance = payload.get("source_provenance") or {}
    provenance = provenance if isinstance(provenance, dict) else {}
    pid = db.new_id("prj_")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO projects (id, title, client_name, consulting_org, status, brief_json,"
            " intake_chat_json, requirements_detail, source_provenance_json, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (pid, title, payload.get("client_name", ""), payload.get("consulting_org", ""),
             "draft", json.dumps(brief), json.dumps(intake_chat), requirements_detail,
             json.dumps(provenance), db.now(), db.now()),
        )
        db.record_audit(conn, action="project.created", project_id=pid,
                        detail={"title": title, "intake_turns": len(intake_chat),
                                "source_type": provenance.get("source_type", "guided_chat")})
        if provenance.get("source_type") == "uploaded_pdf":
            db.record_audit(conn, action="intake.pdf_extracted", project_id=pid,
                            detail={**provenance,
                                    "requirements_detail_chars": len(requirements_detail)})
    return {"id": pid}


@app.get("/api/projects")
def list_projects() -> list[dict[str, Any]]:
    with db.connect() as conn:
        return db.rows_to_dicts(
            conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        )


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "project not found")
    project = dict(row)
    project["brief"] = json.loads(project.pop("brief_json", "{}") or "{}")
    project["intake_chat"] = json.loads(project.pop("intake_chat_json", "[]") or "[]")
    project["source_provenance"] = json.loads(project.pop("source_provenance_json", "{}") or "{}")
    return project


@app.delete("/api/projects/{project_id}", status_code=204)
def delete_project(project_id: str) -> None:
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "project not found")
        poc_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM pocs WHERE project_id=?", (project_id,)).fetchall()]
        for poc_id in poc_ids:
            conn.execute("DELETE FROM annotations WHERE poc_id=?", (poc_id,))
            conn.execute("DELETE FROM review_reports WHERE poc_id=?", (poc_id,))
            conn.execute("DELETE FROM comments WHERE poc_id=?", (poc_id,))
            conn.execute("DELETE FROM approvals WHERE poc_id=?", (poc_id,))
        conn.execute("DELETE FROM pocs WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM research_notes WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM audit_events WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))


@app.post("/api/projects/{project_id}/cancel")
def cancel_generation(project_id: str) -> dict[str, Any]:
    with db.connect() as conn:
        row = conn.execute("SELECT status FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "project not found")
    if row["status"] != "generating":
        return {"ok": False, "reason": "not generating"}
    cancel.request_cancel(project_id)
    return {"ok": True}


@app.post("/api/projects/{project_id}/generate")
def start_generation(project_id: str) -> dict[str, Any]:
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "project not found")
    from .graph.run import run_generation_graph
    _target = run_generation_graph if config.GENERATION_MODE == "graph" else generation.run_generation
    threading.Thread(target=_target, args=(project_id,), daemon=True).start()
    return {"status": "started"}


@app.get("/api/projects/{project_id}/stream")
async def stream_progress(project_id: str) -> StreamingResponse:
    async def gen():
        cursor = 0
        for _ in range(1800):  # ~15 min ceiling at 0.5s
            events, cursor = progress.since(project_id, cursor)
            for ev in events:
                yield f"data: {json.dumps(ev)}\n\n"
                if ev.get("phase") in ("done", "failed", "cancelled"):
                    return
            await asyncio.sleep(0.5)
    return StreamingResponse(gen(), media_type="text/event-stream")


# --- POC bundle -------------------------------------------------------------

def _latest_poc_id(conn, project_id: str) -> str | None:
    row = conn.execute(
        "SELECT id FROM pocs WHERE project_id=? ORDER BY version DESC, created_at DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    return row["id"] if row else None


@app.get("/api/projects/{project_id}/poc")
def poc_bundle(project_id: str) -> dict[str, Any]:
    with db.connect() as conn:
        prow = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if prow is None:
            raise HTTPException(404, "project not found")
        poc_id = _latest_poc_id(conn, project_id)
        if poc_id is None:
            return {"project": dict(prow), "poc": None}
        poc = dict(conn.execute("SELECT * FROM pocs WHERE id=?", (poc_id,)).fetchone())
        poc["design"] = json.loads(poc.pop("design_json", "{}") or "{}")
        poc.pop("diagrams_json", None)
        poc.pop("document_html", None)
        poc.pop("deck_html", None)
        poc.pop("deck_css", None)
        annotations = db.rows_to_dicts(
            conn.execute("SELECT * FROM annotations WHERE poc_id=? ORDER BY created_at", (poc_id,)).fetchall())
        reviews = db.rows_to_dicts(
            conn.execute("SELECT * FROM review_reports WHERE poc_id=? ORDER BY created_at", (poc_id,)).fetchall())
        comments = db.rows_to_dicts(
            conn.execute("SELECT * FROM comments WHERE poc_id=? ORDER BY created_at", (poc_id,)).fetchall())
        approvals = db.rows_to_dicts(
            conn.execute("SELECT * FROM approvals WHERE poc_id=?", (poc_id,)).fetchall())
        shs = db.rows_to_dicts(conn.execute("SELECT * FROM stakeholders").fetchall())
        research = db.rows_to_dicts(
            conn.execute("SELECT id, topic, digest, citations_json, created_at FROM research_notes WHERE poc_id=?",
                         (poc_id,)).fetchall())
    for r in research:
        r["citations"] = json.loads(r.pop("citations_json", "[]") or "[]")

    rollup = _approval_rollup(approvals, shs)
    return {
        "project": dict(prow),
        "poc": poc,
        "annotations": annotations,
        "reviews": reviews,
        "comments": comments,
        "approvals": approvals,
        "approval_rollup": rollup,
        "stakeholders": shs,
        "research": research,
    }


def _approval_rollup(approvals: list[dict[str, Any]], shs: list[dict[str, Any]]) -> dict[str, Any]:
    by_sh = {a["stakeholder_id"]: a for a in approvals}
    needed = [s for s in shs if s["role"] in config.APPROVER_ROLES]
    approved = [s for s in needed if by_sh.get(s["id"], {}).get("status") == "approved"]
    return {
        "needed": len(needed),
        "approved": len(approved),
        "ready": len(needed) > 0 and len(approved) == len(needed),
        "approved_roles": [s["role"] for s in approved],
    }


# --- editable deck ----------------------------------------------------------

@app.get("/api/pocs/{poc_id}/deck", response_class=HTMLResponse)
def serve_deck(poc_id: str, request: Request) -> HTMLResponse:
    with db.connect() as conn:
        row = conn.execute("SELECT deck_html, deck_css FROM pocs WHERE id=?", (poc_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "poc not found")
    editable = _role(request) == config.EDITOR_ROLE
    api_base = str(request.base_url).rstrip("/")
    html = deck.assemble_deck(
        deck_html=row["deck_html"], deck_css=row["deck_css"],
        poc_id=poc_id, api_base=api_base, editable=editable,
    )
    return HTMLResponse(html)


@app.post("/api/pocs/{poc_id}/deck")
def save_deck(poc_id: str, request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if request.headers.get("X-Apoc-Role", "") != config.EDITOR_ROLE:
        raise HTTPException(403, "only the architect may edit the POC deck")
    deck_html = payload.get("deck_html", "")
    with db.connect() as conn:
        row = conn.execute("SELECT project_id FROM pocs WHERE id=?", (poc_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "poc not found")
        conn.execute("UPDATE pocs SET deck_html=?, updated_at=? WHERE id=?", (deck_html, db.now(), poc_id))
        db.record_audit(conn, action="deck.edited", project_id=row["project_id"], poc_id=poc_id, actor="architect")
    return {"ok": True}


# --- editable POC document (architect only) ---------------------------------

@app.post("/api/pocs/{poc_id}/document")
def save_document(poc_id: str, request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if request.headers.get("X-Apoc-Role", "") != config.EDITOR_ROLE:
        raise HTTPException(403, "only the architect may edit the POC document")
    with db.connect() as conn:
        row = conn.execute("SELECT project_id FROM pocs WHERE id=?", (poc_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "poc not found")
        sets, vals = [], []
        if "document_md" in payload:
            sets.append("document_md=?")
            vals.append(payload["document_md"] or "")
        if not sets:
            raise HTTPException(400, "nothing to update")
        sets.append("updated_at=?")
        vals.append(db.now())
        vals.append(poc_id)
        conn.execute(f"UPDATE pocs SET {', '.join(sets)} WHERE id=?", vals)
        db.record_audit(conn, action="document.edited", project_id=row["project_id"],
                        poc_id=poc_id, actor="architect")
    return {"ok": True}


# --- comments + approvals ---------------------------------------------------

@app.post("/api/pocs/{poc_id}/comments")
def add_comment(poc_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    body = (payload.get("body") or "").strip()
    sh = payload.get("stakeholder_id") or ""
    if not body or not sh:
        raise HTTPException(400, "stakeholder_id and body are required")
    cid = db.new_id("cm_")
    with db.connect() as conn:
        prow = conn.execute("SELECT project_id FROM pocs WHERE id=?", (poc_id,)).fetchone()
        if prow is None:
            raise HTTPException(404, "poc not found")
        conn.execute(
            "INSERT INTO comments (id, poc_id, annotation_id, stakeholder_id, body, anchor_line,"
            " anchor_slug, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (cid, poc_id, payload.get("annotation_id"), sh, body,
             payload.get("anchor_line"), payload.get("anchor_slug"), db.now()),
        )
        db.record_audit(conn, action="comment.added", project_id=prow["project_id"], poc_id=poc_id, actor=sh)
    return {"id": cid}


_COMMENT_STATUSES = {"open", "accepted", "closed"}


def _require_architect(request: Request) -> None:
    if request.headers.get("X-Apoc-Role", "") != config.EDITOR_ROLE:
        raise HTTPException(403, "only the architect may curate comments")


@app.post("/api/pocs/{poc_id}/comments/{comment_id}/status")
def set_comment_status(poc_id: str, comment_id: str, request: Request,
                       payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _require_architect(request)
    status = payload.get("status")
    if status not in _COMMENT_STATUSES:
        raise HTTPException(422, "status must be one of open|accepted|closed")
    with db.connect() as conn:
        row = conn.execute(
            "SELECT c.id, p.project_id FROM comments c JOIN pocs p ON p.id = c.poc_id"
            " WHERE c.id=? AND c.poc_id=?", (comment_id, poc_id)).fetchone()
        if row is None:
            raise HTTPException(404, "comment not found")
        conn.execute("UPDATE comments SET status=? WHERE id=?", (status, comment_id))
        db.record_audit(conn, action="comment.status_changed", project_id=row["project_id"],
                        poc_id=poc_id, actor="architect",
                        detail={"comment_id": comment_id, "status": status})
    return {"ok": True}


@app.post("/api/pocs/{poc_id}/comments/status")
def set_comments_status_bulk(poc_id: str, request: Request,
                             payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _require_architect(request)
    status = payload.get("status")
    ids = payload.get("ids")
    if status not in _COMMENT_STATUSES:
        raise HTTPException(422, "status must be one of open|accepted|closed")
    if not isinstance(ids, list) or not ids:
        raise HTTPException(422, "ids must be a non-empty list")
    with db.connect() as conn:
        prow = conn.execute("SELECT project_id FROM pocs WHERE id=?", (poc_id,)).fetchone()
        if prow is None:
            raise HTTPException(404, "poc not found")
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"UPDATE comments SET status=? WHERE poc_id=? AND id IN ({placeholders})",
            (status, poc_id, *ids))
        db.record_audit(conn, action="comment.status_changed", project_id=prow["project_id"],
                        poc_id=poc_id, actor="architect",
                        detail={"comment_ids": ids, "status": status, "bulk": True})
    return {"ok": True, "updated": len(ids)}


@app.post("/api/pocs/{poc_id}/ai-edit")
def ai_edit(poc_id: str, request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _require_architect(request)
    instruction = str(payload.get("instruction", "") or "").strip()
    with db.connect() as conn:
        poc = conn.execute("SELECT document_md FROM pocs WHERE id=?", (poc_id,)).fetchone()
        if poc is None:
            raise HTTPException(404, "poc not found")
        rows = conn.execute(
            "SELECT c.id, c.body, c.anchor_slug, c.anchor_line, s.role AS role"
            " FROM comments c LEFT JOIN stakeholders s ON s.id = c.stakeholder_id"
            " WHERE c.poc_id=? AND c.status='accepted' ORDER BY c.created_at", (poc_id,)).fetchall()
    comments = db.rows_to_dicts(rows)
    if not comments and not instruction:
        raise HTTPException(422, "accept some comments (or add guidance) before applying")
    try:
        proposed_md, addressed = ai_assist.run_ai_edit(
            document_md=poc["document_md"], comments=comments, instruction=instruction)
    except ai_assist.EditTruncatedError:
        raise HTTPException(502, "the edit was cut off — try fewer comments at once")
    except Exception as exc:
        raise HTTPException(502, f"AI edit failed: {exc}") from exc
    return {"proposed_md": proposed_md, "addressed_comment_ids": addressed}


def _chat_context(conn, poc_id: str) -> str:
    poc = conn.execute("SELECT document_md FROM pocs WHERE id=?", (poc_id,)).fetchone()
    reviews = conn.execute(
        "SELECT role, verdict, summary FROM review_reports WHERE poc_id=? ORDER BY created_at",
        (poc_id,)).fetchall()
    annotations = conn.execute(
        "SELECT domain, title, body FROM annotations WHERE poc_id=? ORDER BY created_at",
        (poc_id,)).fetchall()
    research = conn.execute(
        "SELECT topic, digest FROM research_notes WHERE poc_id=? ORDER BY created_at",
        (poc_id,)).fetchall()
    parts = [f"DOCUMENT:\n{poc['document_md'] if poc else ''}"]
    if reviews:
        parts.append("REVIEWS:\n" + "\n".join(
            f"- {r['role']} ({r['verdict']}): {r['summary']}" for r in reviews))
    if annotations:
        parts.append("AI ANNOTATIONS:\n" + "\n".join(
            f"- [{a['domain']}] {a['title']}: {a['body']}" for a in annotations))
    if research:
        parts.append("RESEARCH DIGEST:\n" + "\n".join(
            f"- {r['topic']}: {r['digest']}" for r in research))
    return "\n\n".join(parts)


@app.post("/api/pocs/{poc_id}/chat")
def poc_chat(poc_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise HTTPException(400, "messages must be a list")
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM pocs WHERE id=?", (poc_id,)).fetchone() is None:
            raise HTTPException(404, "poc not found")
        context = _chat_context(conn, poc_id)
    try:
        reply = ai_assist.run_poc_chat(messages=messages, context=context)
    except Exception as exc:
        raise HTTPException(502, f"chat failed: {exc}") from exc
    return {"reply": reply}


@app.post("/api/pocs/{poc_id}/approvals")
def set_approval(poc_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    sh = payload.get("stakeholder_id") or ""
    status = payload.get("status") or "approved"
    if status not in ("pending", "approved", "changes_requested"):
        raise HTTPException(400, "invalid status")
    if not sh:
        raise HTTPException(400, "stakeholder_id is required")
    with db.connect() as conn:
        prow = conn.execute("SELECT project_id FROM pocs WHERE id=?", (poc_id,)).fetchone()
        if prow is None:
            raise HTTPException(404, "poc not found")
        conn.execute(
            "INSERT INTO approvals (id, poc_id, stakeholder_id, status, note, updated_at) VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(poc_id, stakeholder_id) DO UPDATE SET status=excluded.status,"
            " note=excluded.note, updated_at=excluded.updated_at",
            (db.new_id("ap_"), poc_id, sh, status, payload.get("note", ""), db.now()),
        )
        db.record_audit(conn, action="approval.set", project_id=prow["project_id"], poc_id=poc_id,
                        actor=sh, detail={"status": status})
        # Recompute roll-up and flip the project to ready_to_align when complete.
        approvals = db.rows_to_dicts(conn.execute("SELECT * FROM approvals WHERE poc_id=?", (poc_id,)).fetchall())
        shs = db.rows_to_dicts(conn.execute("SELECT * FROM stakeholders").fetchall())
        rollup = _approval_rollup(approvals, shs)
        new_status = "ready_to_align" if rollup["ready"] else "in_review"
        conn.execute("UPDATE projects SET status=?, updated_at=? WHERE id=?",
                     (new_status, db.now(), prow["project_id"]))
    return {"ok": True, "rollup": rollup, "project_status": new_status}


# --- audit ------------------------------------------------------------------

@app.get("/api/projects/{project_id}/audit")
def audit(project_id: str) -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = db.rows_to_dicts(
            conn.execute("SELECT * FROM audit_events WHERE project_id=? ORDER BY created_at DESC", (project_id,)).fetchall())
    for r in rows:
        r["detail"] = json.loads(r.pop("detail_json", "{}") or "{}")
    return rows
