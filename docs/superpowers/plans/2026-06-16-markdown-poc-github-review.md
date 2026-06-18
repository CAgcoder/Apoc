# Markdown POC + beautiful-mermaid + GitHub-style review — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the APoc POC review experience so a new POC produces a GitHub-PR-review-style screen: a Markdown document (left) with a line-number gutter, inline Markdown comments, and LLM-authored mermaid diagrams rendered via beautiful-mermaid; with position-aligned, merged AI findings (middle). React Flow is removed.

**Architecture:** The POC document becomes Markdown (`pocs.document_md`), the single source of truth. Diagrams are ` ```mermaid ` fenced blocks the LLM writes inline; the frontend renders them to ephemeral SVG with `beautiful-mermaid`. The left column renders Markdown via `markdown-it` (each block tagged with its source line for anchoring); the middle column absolutely-positions AI annotation cards beside the sections they flag, merging multiple findings per section and pushing colliding cards down.

**Tech Stack:** FastAPI + SQLite (backend), Vite + React 19 + TS + Tailwind v4 (frontend), `markdown-it`, `beautiful-mermaid`. Tests: `pytest` (backend), `vitest` (frontend).

**Spec:** `apoc/docs/superpowers/specs/2026-06-16-markdown-poc-github-review-design.md`

**Conventions:** All paths below are relative to repo root `/Users/automan/Desktop/Arcd/ArcD`. Backend lives in `apoc/backend`, run from there; frontend in `apoc/frontend`. Backend tests: `cd apoc/backend && python -m pytest`. Frontend tests/build: `cd apoc/frontend && npm test` / `npm run build`.

---

## File map

**Backend**
- Modify: `apoc/backend/app/db.py` — schema comment + `_MIGRATIONS` for `document_md`, `comments.anchor_line`, `comments.anchor_slug`.
- Modify: `apoc/backend/app/prompts.py` — rewrite `DOCUMENT_SYSTEM` to Markdown + mermaid.
- Modify: `apoc/backend/app/generation.py` — drop `diagrams`, persist `document_md`, add `_clean_md_doc`, feed deck/reviews with Markdown.
- Modify: `apoc/backend/app/main.py` — bundle returns `document_md` (no `diagrams`); `save_document` accepts `document_md`; `add_comment` accepts `anchor_line`/`anchor_slug`.
- Delete: `apoc/backend/app/diagrams.py`, `apoc/backend/tests/test_diagrams.py`.
- Test: `apoc/backend/tests/test_document_markdown.py` (new).

**Frontend**
- Modify: `apoc/frontend/package.json` — add `markdown-it`, `beautiful-mermaid`; remove `@xyflow/react`, `@dagrejs/dagre`.
- Rewrite: `apoc/frontend/src/markdown.ts` (+ `markdown.test.ts` new).
- Create: `apoc/frontend/src/Mermaid.tsx`, `apoc/frontend/src/MermaidLightbox.tsx`.
- Create: `apoc/frontend/src/CommentComposer.tsx`.
- Create: `apoc/frontend/src/AnnotationMargin.tsx` (+ `AnnotationMargin.test.tsx` new).
- Rewrite: `apoc/frontend/src/PocDocument.tsx` → `apoc/frontend/src/MarkdownDoc.tsx` (delete old, create new).
- Modify: `apoc/frontend/src/api.ts` — types + payloads.
- Modify: `apoc/frontend/src/ProjectView.tsx` — rewrite `ReviewPane`.
- Modify: `apoc/frontend/src/index.css` — GitHub-review styles (gutter, file frame, finding/anchor).
- Delete: `DiagramCanvas.tsx`, `DiagramFocusModal.tsx`, `diagramLayout.ts`, `diagramLayout.test.ts`, `diagramEdges.ts`, `diagramEdges.test.ts`, `ArchitectureNode.tsx`, `docHtml.ts`, `PocDocument.test.tsx`.

---

## Phase A — Backend

### Task 1: DB migrations for markdown doc + comment anchors

**Files:**
- Modify: `apoc/backend/app/db.py:48-49` (schema comments) and `apoc/backend/app/db.py:139-141` (`_MIGRATIONS`).

- [ ] **Step 1: Add the new columns to the `pocs` create-table comment and a `comments` note**

In `apoc/backend/app/db.py`, change the `pocs` columns (lines 48-49) to keep them but mark legacy, and add `document_md`:

```python
    markdown    TEXT NOT NULL DEFAULT '',   -- legacy plain-text POC (kept for back-compat)
    document_html TEXT NOT NULL DEFAULT '', -- LEGACY HTML POC document (superseded by document_md)
    document_md TEXT NOT NULL DEFAULT '',   -- Markdown POC document (review left column, source of truth)
    diagrams_json TEXT NOT NULL DEFAULT '[]', -- LEGACY React Flow diagrams (diagrams now inline mermaid)
```

(The `CREATE TABLE comments (...)` stays as-is; the two new comment columns are added via migration so existing DBs pick them up.)

- [ ] **Step 2: Add migration entries**

In `_MIGRATIONS` (around line 139), append after the existing entries:

```python
_MIGRATIONS = [
    ("pocs", "document_html", "TEXT NOT NULL DEFAULT ''"),
    ("pocs", "diagrams_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("pocs", "document_md", "TEXT NOT NULL DEFAULT ''"),
    ("comments", "anchor_line", "INTEGER"),
    ("comments", "anchor_slug", "TEXT"),
]
```

- [ ] **Step 3: Verify migrations apply on a fresh start**

Run: `cd apoc/backend && python -c "from app import db; db.init_db(); import sqlite3,os; con=sqlite3.connect(db.DB_PATH if hasattr(db,'DB_PATH') else 'apoc.db'); print([r[1] for r in con.execute('PRAGMA table_info(pocs)')]); print([r[1] for r in con.execute('PRAGMA table_info(comments)')])"`

Expected: `pocs` list includes `document_md`; `comments` list includes `anchor_line` and `anchor_slug`. (If `init_db`/`DB_PATH` names differ, just start the server `./run.sh` once and re-check with the PRAGMA queries — startup runs `_MIGRATIONS`.)

- [ ] **Step 4: Commit**

```bash
git add apoc/backend/app/db.py
git commit -m "feat(db): add document_md + comment anchor columns"
```

---

### Task 2: Rewrite DOCUMENT_SYSTEM prompt to Markdown + mermaid

**Files:**
- Modify: `apoc/backend/app/prompts.py:166-195` (`DOCUMENT_SYSTEM`).

- [ ] **Step 1: Replace the `DOCUMENT_SYSTEM` string**

Replace the whole `DOCUMENT_SYSTEM = """..."""` block (lines 166-195) with:

```python
DOCUMENT_SYSTEM = """You write the FULL architecture POC document that a client \
review board (compliance, security, FinOps, CTO) will read and that the architect \
will edit. This is the detailed companion to the slide deck — go DEEPER than \
slides: explain reasoning, trade-offs, and evidence. Ground it in the structured \
design and research provided.

Output ONLY the document as clean GitHub-Flavored Markdown. No HTML, no <script>, \
no front-matter, no surrounding code fences around the whole document.

Use EXACTLY these level-2 headings (`## `), in order (reviews anchor to them):
"Executive summary", "Context & goals", "Requirements mapping", \
"Proposed architecture", "Technology choices", "Non-functional requirements", \
"Key decisions", "Risks", "Cost outlook", "Open questions".

Requirements:
- Be thorough and specific. Requirements mapping, Technology choices, NFRs, Key \
  decisions, Risks and Cost outlook MUST use Markdown tables (pipe syntax with a \
  header separator row) with real rows from the design. Key decisions must give \
  the decision, the rationale, alternatives considered, and the trade-off/risk.
- Respect the user's stated platform preference from the brief's `cloud` field. \
  Self-hosted/open-source means OSS and self-managed components, not a default \
  hyperscaler managed-services architecture. Other/regional providers should use \
  that provider's services/ecosystem. Hybrid/undecided recommendations must call \
  out vendor-lock-in trade-offs.
- DIAGRAMS — author them directly as Mermaid fenced code blocks (```mermaid ... ```):
  * In "Proposed architecture", include the system architecture as a Mermaid \
    `flowchart LR` (or `graph TD`) showing every component as a node and every \
    real data flow as an edge. Then add prose explaining the components and flows.
  * Where it clarifies a section, you MAY add one more Mermaid diagram (e.g. a \
    `sequenceDiagram` for a request flow, or a `stateDiagram-v2`).
  * Keep node/edge labels SHORT. Every node must connect to at least one other. \
    Do NOT put styling/`classDef`/`style`/theme directives in the mermaid — the \
    renderer themes it. Use only structure (nodes, edges, labels).
- Architecture artifact only: no implementation code, IaC, or deploy manifests."""
```

- [ ] **Step 2: Sanity-check it imports**

Run: `cd apoc/backend && python -c "from app import prompts; assert 'mermaid' in prompts.DOCUMENT_SYSTEM and 'Markdown' in prompts.DOCUMENT_SYSTEM; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add apoc/backend/app/prompts.py
git commit -m "feat(prompts): DOCUMENT_SYSTEM emits Markdown with inline mermaid"
```

---

### Task 3: Generation — drop diagrams, persist document_md

**Files:**
- Modify: `apoc/backend/app/generation.py` (imports line 22; helper near line 35; doc step lines 222-256; deck step line 265; reviews step line 287).
- Delete: `apoc/backend/app/diagrams.py`, `apoc/backend/tests/test_diagrams.py`.

- [ ] **Step 1: Add a Markdown cleanup helper**

In `apoc/backend/app/generation.py`, just after `_clean_html_doc` (around line 41), add:

```python
def _clean_md_doc(text: str) -> str:
    """Strip a stray wrapping code fence a model may put around the whole doc."""
    t = (text or "").strip()
    m = re.fullmatch(r"```(?:markdown|md)?\s*\n(.+?)\n```", t, re.DOTALL)
    if m:
        t = m.group(1).strip()
    return t
```

- [ ] **Step 2: Remove the `diagrams` import**

Change `apoc/backend/app/generation.py:22` from:

```python
from . import cancel, config, db, diagrams, llm, models, progress, prompts, research
```
to:
```python
from . import cancel, config, db, llm, models, progress, prompts, research
```

- [ ] **Step 3: Replace the document step (lines 222-256)**

Replace the block starting at `# 3. Editable diagram (deterministic) + detailed HTML document` through the `progress.publish(... "designed" ...)` line with:

```python
        # 3. Detailed Markdown POC document (diagrams are inline mermaid) ------
        cancel.raise_if_cancelled(project_id)
        progress.publish(project_id, "writing_document", message="Writing the detailed POC document")
        doc_user = (
            f"POC title: {title}\n\nStructured design (JSON):\n{json.dumps(design)[:6000]}"
            f"\n\nResearch digest:\n{digest[:1500]}"
        )
        document_raw, document_sources = llm.run_text(
            system=prompts.DOCUMENT_SYSTEM, user=doc_user, model=config.MODEL, max_tokens=16000,
            **_deepseek_reasoning_kwargs(config.MODEL),
        )
        _write_raw(store, "document", document_raw, {
            "model": config.MODEL,
            "json_mode": False,
            "tool_loop": False,
            "web_search": False,
            "source_count": len(document_sources),
            "parsed": True,
        })
        document_md = _clean_md_doc(document_raw)

        poc_id = db.new_id("poc_")
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO pocs (id, project_id, version, title, markdown, document_md,"
                " design_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (poc_id, project_id, 1, title, markdown, document_md,
                 json.dumps(design), db.now(), db.now()),
            )
            conn.execute("UPDATE research_notes SET poc_id=? WHERE project_id=? AND poc_id IS NULL",
                         (poc_id, project_id))
            mermaid_count = document_md.count("```mermaid")
            db.record_audit(conn, action="document.completed", project_id=project_id, poc_id=poc_id,
                            detail={"diagrams": mermaid_count, "doc_chars": len(document_md)})
        progress.publish(project_id, "designed", message="Design & document ready", poc_id=poc_id)
```

- [ ] **Step 4: Feed the deck + reviews steps with Markdown**

Change `apoc/backend/app/generation.py:265` from:
```python
            user=_deck_user(project, title, _html_to_text(document_html) or markdown),
```
to:
```python
            user=_deck_user(project, title, document_md or markdown),
```

Change `apoc/backend/app/generation.py:287` from:
```python
            user=document_html or markdown,
```
to:
```python
            user=document_md or markdown,
```

(`_html_to_text` and `_clean_html_doc` are now unused — leave them; a later cleanup task removes them. They do no harm.)

- [ ] **Step 5: Delete the diagrams module + its test**

```bash
git rm apoc/backend/app/diagrams.py apoc/backend/tests/test_diagrams.py
```

- [ ] **Step 6: Verify the backend imports and existing suite still loads**

Run: `cd apoc/backend && python -c "from app import generation; print('ok')"`
Expected: `ok` (no ImportError for `diagrams`).

Run: `cd apoc/backend && python -m pytest -q`
Expected: collection succeeds; no errors referencing `diagrams`. (Other tests should pass as before.)

- [ ] **Step 7: Commit**

```bash
git add apoc/backend/app/generation.py
git commit -m "feat(generation): persist document_md, remove deterministic diagrams"
```

---

### Task 4: Endpoints — bundle, save_document, add_comment

**Files:**
- Modify: `apoc/backend/app/main.py:234-236` (bundle), `:313-336` (save_document), `:341-357` (add_comment).
- Test: `apoc/backend/tests/test_document_markdown.py` (new).

- [ ] **Step 1: Write the failing endpoint test**

Create `apoc/backend/tests/test_document_markdown.py`:

```python
import os, sqlite3
from fastapi.testclient import TestClient
from app import db, main


def _seed_poc(conn):
    pid = db.new_id("p_")
    conn.execute(
        "INSERT INTO projects (id, title, client_name, consulting_org, status, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (pid, "T", "C", "O", "designed", db.now()),
    )
    poc_id = db.new_id("poc_")
    conn.execute(
        "INSERT INTO pocs (id, project_id, version, title, markdown, document_md, design_json,"
        " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (poc_id, pid, 1, "T", "", "## Executive summary\nhi", "{}", db.now(), db.now()),
    )
    sh = db.new_id("s_")
    conn.execute(
        "INSERT INTO stakeholders (id, name, role, org) VALUES (?,?,?,?)",
        (sh, "Arch", "architect", "O"),
    )
    return pid, poc_id, sh


def test_bundle_returns_document_md(tmp_path, monkeypatch):
    db.init_db()
    with db.connect() as conn:
        pid, poc_id, _ = _seed_poc(conn)
    client = TestClient(main.app)
    r = client.get(f"/api/projects/{pid}/poc")
    assert r.status_code == 200
    poc = r.json()["poc"]
    assert poc["document_md"].startswith("## Executive summary")
    assert "diagrams" not in poc


def test_save_document_md_and_comment_anchor():
    db.init_db()
    with db.connect() as conn:
        pid, poc_id, sh = _seed_poc(conn)
    client = TestClient(main.app)
    # save markdown as architect
    r = client.post(f"/api/pocs/{poc_id}/document", json={"document_md": "## Risks\nnew"},
                    headers={"X-Apoc-Role": "architect"})
    assert r.status_code == 200
    # line-anchored comment
    r = client.post(f"/api/pocs/{poc_id}/comments",
                    json={"stakeholder_id": sh, "body": "see line", "anchor_line": 12, "anchor_slug": "risks"})
    assert r.status_code == 200
    b = client.get(f"/api/projects/{pid}/poc").json()
    assert b["poc"]["document_md"] == "## Risks\nnew"
    c = b["comments"][0]
    assert c["anchor_line"] == 12 and c["anchor_slug"] == "risks"
```

- [ ] **Step 2: Run it — expect failure**

Run: `cd apoc/backend && python -m pytest tests/test_document_markdown.py -q`
Expected: FAIL — bundle still exposes `diagrams` / lacks `document_md` plumbing; comment columns not persisted.

- [ ] **Step 3: Update the bundle**

In `apoc/backend/app/main.py`, replace line 236:
```python
        poc["diagrams"] = json.loads(poc.pop("diagrams_json", "[]") or "[]")
```
with:
```python
        poc.pop("diagrams_json", None)
        poc.pop("document_html", None)
```
(`document_md` is already in `SELECT *`, so it stays in the dict. We drop the legacy fields from the response.)

- [ ] **Step 4: Update `save_document`**

Replace the `sets`/`vals` branches (lines 322-327) with:
```python
        sets, vals = [], []
        if "document_md" in payload:
            sets.append("document_md=?")
            vals.append(payload["document_md"] or "")
```
(Keep the surrounding `if not sets: raise 400`, `updated_at`, audit, and return.)

- [ ] **Step 5: Update `add_comment`**

Replace the INSERT (lines 352-355) with:
```python
        conn.execute(
            "INSERT INTO comments (id, poc_id, annotation_id, stakeholder_id, body, anchor_line,"
            " anchor_slug, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (cid, poc_id, payload.get("annotation_id"), sh, body,
             payload.get("anchor_line"), payload.get("anchor_slug"), db.now()),
        )
```

- [ ] **Step 6: Run the test — expect pass**

Run: `cd apoc/backend && python -m pytest tests/test_document_markdown.py -q`
Expected: PASS (2 passed).

- [ ] **Step 7: Run full backend suite**

Run: `cd apoc/backend && python -m pytest -q`
Expected: all pass (no diagrams references).

- [ ] **Step 8: Commit**

```bash
git add apoc/backend/app/main.py apoc/backend/tests/test_document_markdown.py
git commit -m "feat(api): document_md bundle/save + line-anchored comments"
```

---

## Phase B — Frontend

### Task 5: Dependencies

**Files:**
- Modify: `apoc/frontend/package.json`.

- [ ] **Step 1: Install new deps, remove old**

Run:
```bash
cd apoc/frontend
npm install markdown-it beautiful-mermaid
npm install -D @types/markdown-it
npm uninstall @xyflow/react @dagrejs/dagre
```

- [ ] **Step 2: Verify the package resolves and renders**

Run: `cd apoc/frontend && node -e "const {renderMermaidSVG}=require('beautiful-mermaid'); const s=renderMermaidSVG('graph LR; A-->B'); console.log(s.slice(0,40))"`
Expected: prints the start of an `<svg ...>` string. (If the package is ESM-only and `require` fails, instead verify with: `node --input-type=module -e "import('beautiful-mermaid').then(m=>console.log(typeof m.renderMermaidSVG))"` → prints `function`.)

- [ ] **Step 3: Commit**

```bash
git add apoc/frontend/package.json apoc/frontend/package-lock.json
git commit -m "build(frontend): add markdown-it + beautiful-mermaid, drop react-flow/dagre"
```

---

### Task 6: `markdown.ts` rewrite (renderDoc / renderInline / slugify)

**Files:**
- Rewrite: `apoc/frontend/src/markdown.ts`.
- Test: `apoc/frontend/src/markdown.test.ts` (new).

- [ ] **Step 1: Write the failing tests**

Create `apoc/frontend/src/markdown.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { renderDoc, renderInline, slugify } from "./markdown";

describe("slugify", () => {
  it("kebab-cases headings", () => {
    expect(slugify("Context & goals")).toBe("context-goals");
  });
});

describe("renderDoc", () => {
  it("gives h2 a sec- id and a source line", () => {
    const { html } = renderDoc("## Risks\n\ntext");
    expect(html).toContain('id="sec-risks"');
    expect(html).toMatch(/data-line="\d+"/);
  });

  it("turns a mermaid fence into a placeholder carrying the code", () => {
    const { html } = renderDoc("```mermaid\ngraph LR; A-->B\n```");
    expect(html).toContain('class="mermaid-block"');
    expect(html).toContain("graph LR");
    expect(html).not.toContain("<svg"); // SVG is rendered later, in React
  });

  it("renders GFM tables", () => {
    const { html } = renderDoc("| a | b |\n|---|---|\n| 1 | 2 |");
    expect(html).toContain("<table");
  });
});

describe("renderInline", () => {
  it("renders markdown but escapes raw html", () => {
    const html = renderInline("**bold** <script>x</script>");
    expect(html).toContain("<strong>bold</strong>");
    expect(html).not.toContain("<script>");
  });
});
```

- [ ] **Step 2: Run — expect failure**

Run: `cd apoc/frontend && npx vitest run src/markdown.test.ts`
Expected: FAIL — current `markdown.ts` has no `renderDoc`/`renderInline`.

- [ ] **Step 3: Implement `markdown.ts`**

Replace the entire contents of `apoc/frontend/src/markdown.ts` with:

```ts
// Markdown rendering for the POC document and comments.
// Built on markdown-it. Top-level blocks carry their source line (`data-line`)
// so the review can anchor comments to lines; h2 headings get stable `sec-<slug>`
// ids so AI annotations can locate them; ```mermaid fences become placeholders
// that React swaps for live-rendered SVG.
import MarkdownIt from "markdown-it";

export function slugify(s: string): string {
  return s.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function escapeAttr(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function makeMd(): MarkdownIt {
  const md = new MarkdownIt({ html: false, linkify: true, breaks: false });

  // Tag every top-level (level 0) block-open token with its 1-based source line.
  md.core.ruler.push("source_lines", (state) => {
    for (const t of state.tokens) {
      if (t.level === 0 && t.map && /_open$/.test(t.type)) {
        t.attrSet("data-line", String(t.map[0] + 1));
      }
      // fence/code are self-contained level-0 tokens (no _open) — tag them too.
      if (t.level === 0 && t.map && (t.type === "fence" || t.type === "code_block")) {
        t.attrSet("data-line", String(t.map[0] + 1));
      }
    }
    return true;
  });

  // h2 → add sec-<slug> id derived from its text.
  const defaultHeadingOpen =
    md.renderer.rules.heading_open ||
    ((tokens, idx, opts, _env, self) => self.renderToken(tokens, idx, opts));
  md.renderer.rules.heading_open = (tokens, idx, opts, env, self) => {
    const tok = tokens[idx];
    if (tok.tag === "h2") {
      const inline = tokens[idx + 1];
      const text = inline && inline.type === "inline" ? inline.content : "";
      tok.attrSet("id", `sec-${slugify(text)}`);
    }
    return defaultHeadingOpen(tokens, idx, opts, env, self);
  };

  // ```mermaid → placeholder div carrying the raw code (+ data-line).
  const defaultFence =
    md.renderer.rules.fence ||
    ((tokens, idx, opts, _env, self) => self.renderToken(tokens, idx, opts));
  md.renderer.rules.fence = (tokens, idx, opts, env, self) => {
    const tok = tokens[idx];
    if ((tok.info || "").trim().toLowerCase() === "mermaid") {
      const line = tok.map ? tok.map[0] + 1 : 0;
      return `<div class="mermaid-block" data-line="${line}" data-code="${escapeAttr(tok.content)}"></div>\n`;
    }
    return defaultFence(tokens, idx, opts, env, self);
  };

  return md;
}

const docMd = makeMd();
const inlineMd = new MarkdownIt({ html: false, linkify: true, breaks: true });

export function renderDoc(src: string): { html: string } {
  return { html: docMd.render(src || "") };
}

export function renderInline(src: string): string {
  return inlineMd.render(src || "");
}
```

- [ ] **Step 4: Run — expect pass**

Run: `cd apoc/frontend && npx vitest run src/markdown.test.ts`
Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add apoc/frontend/src/markdown.ts apoc/frontend/src/markdown.test.ts
git commit -m "feat(frontend): markdown-it doc renderer with line/section anchors + mermaid placeholders"
```

---

### Task 7: `Mermaid.tsx` + `MermaidLightbox.tsx`

**Files:**
- Create: `apoc/frontend/src/Mermaid.tsx`, `apoc/frontend/src/MermaidLightbox.tsx`.

- [ ] **Step 1: Create the lightbox**

Create `apoc/frontend/src/MermaidLightbox.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";

// Centered modal that enlarges a Mermaid SVG with wheel-zoom + drag-pan.
export function MermaidLightbox({ svg, onClose }: { svg: string; onClose: () => void }) {
  const [scale, setScale] = useState(1);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative h-[80vh] w-[80vw] overflow-hidden rounded-xl border border-white/10 bg-[#0d1117]"
        onClick={(e) => e.stopPropagation()}
        onWheel={(e) => {
          const next = Math.min(4, Math.max(0.4, scale - e.deltaY * 0.001));
          setScale(next);
        }}
        onMouseDown={(e) => (drag.current = { x: e.clientX - pos.x, y: e.clientY - pos.y })}
        onMouseMove={(e) => {
          if (drag.current) setPos({ x: e.clientX - drag.current.x, y: e.clientY - drag.current.y });
        }}
        onMouseUp={() => (drag.current = null)}
        onMouseLeave={() => (drag.current = null)}
      >
        <button
          onClick={onClose}
          className="absolute right-3 top-3 z-10 rounded-md bg-white/10 px-2 py-1 text-sm text-white/70 hover:text-white"
        >
          ✕
        </button>
        <div
          className="flex h-full w-full cursor-grab items-center justify-center active:cursor-grabbing [&_svg]:h-auto [&_svg]:w-auto"
          style={{ transform: `translate(${pos.x}px, ${pos.y}px) scale(${scale})` }}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create the inline Mermaid component**

Create `apoc/frontend/src/Mermaid.tsx`:

```tsx
import { useMemo, useState } from "react";
import { renderMermaidSVG } from "beautiful-mermaid";
import { MermaidLightbox } from "./MermaidLightbox";

// Theme tuned to the app's dark surfaces; transparent so it sits on any panel.
const THEME = {
  bg: "transparent",
  fg: "#c9d1d9",
  accent: "#4493f8",
  muted: "#8b949e",
  line: "#30363d",
  border: "#30363d",
  transparent: true,
} as const;

export function Mermaid({ code }: { code: string }) {
  const [open, setOpen] = useState(false);
  const { svg, error } = useMemo(() => {
    try {
      return { svg: renderMermaidSVG(code, THEME as any), error: null as string | null };
    } catch (e) {
      return { svg: null, error: e instanceof Error ? e.message : String(e) };
    }
  }, [code]);

  if (error || !svg) {
    return (
      <div className="my-3 rounded-lg border border-amber-500/30 bg-amber-500/[0.06] p-3">
        <div className="mb-1 text-xs text-amber-300/80">diagram failed to render</div>
        <pre className="overflow-x-auto text-xs text-white/60">{code}</pre>
      </div>
    );
  }

  return (
    <>
      <div
        className="my-3 cursor-zoom-in rounded-lg border border-white/8 bg-white/[0.02] p-3 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full"
        title="Click to enlarge"
        onClick={() => setOpen(true)}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
      {open && <MermaidLightbox svg={svg} onClose={() => setOpen(false)} />}
    </>
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `cd apoc/frontend && npx tsc --noEmit`
Expected: no errors. (If `beautiful-mermaid` ships no types, add `apoc/frontend/src/beautiful-mermaid.d.ts` with `declare module "beautiful-mermaid" { export function renderMermaidSVG(code: string, theme?: any): string; export const THEMES: Record<string, any>; }` and re-run.)

- [ ] **Step 4: Commit**

```bash
git add apoc/frontend/src/Mermaid.tsx apoc/frontend/src/MermaidLightbox.tsx apoc/frontend/src/beautiful-mermaid.d.ts 2>/dev/null
git commit -m "feat(frontend): Mermaid renderer + zoom/pan lightbox"
```

---

### Task 8: `CommentComposer.tsx` (GitHub Write/Preview)

**Files:**
- Create: `apoc/frontend/src/CommentComposer.tsx`.

- [ ] **Step 1: Create the composer**

Create `apoc/frontend/src/CommentComposer.tsx`:

```tsx
import { useState } from "react";
import { renderInline } from "./markdown";

// GitHub-style comment box: Write / Preview tabs over a Markdown textarea.
export function CommentComposer({
  placeholder,
  onSubmit,
  onCancel,
  submitting,
}: {
  placeholder: string;
  onSubmit: (body: string) => void;
  onCancel?: () => void;
  submitting?: boolean;
}) {
  const [tab, setTab] = useState<"write" | "preview">("write");
  const [body, setBody] = useState("");

  return (
    <div className="rounded-lg border border-white/12 bg-[#0d1117]">
      <div className="flex gap-1 border-b border-white/10 px-2 pt-2 text-xs">
        {(["write", "preview"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-t-md px-3 py-1.5 capitalize ${
              tab === t ? "bg-[#161b22] text-white" : "text-white/50 hover:text-white"
            }`}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="p-2">
        {tab === "write" ? (
          <textarea
            autoFocus
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder={placeholder}
            className="h-24 w-full resize-y rounded-md border border-white/12 bg-[#0d1117] px-3 py-2 text-sm text-white outline-none focus:border-blue-500/50"
          />
        ) : (
          <div
            className="md min-h-[6rem] rounded-md border border-white/8 px-3 py-2 text-sm text-white/85"
            dangerouslySetInnerHTML={{ __html: renderInline(body) || "<em>Nothing to preview</em>" }}
          />
        )}
        <div className="mt-2 flex justify-end gap-2">
          {onCancel && (
            <button
              onClick={onCancel}
              className="rounded-md border border-white/15 px-3 py-1.5 text-sm text-white/60 hover:bg-white/5"
            >
              Cancel
            </button>
          )}
          <button
            disabled={!body.trim() || submitting}
            onClick={() => onSubmit(body.trim())}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            {submitting ? "…" : "Comment"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd apoc/frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apoc/frontend/src/CommentComposer.tsx
git commit -m "feat(frontend): GitHub-style Write/Preview comment composer"
```

---

### Task 9: `AnnotationMargin.tsx` (merge + align + collide)

**Files:**
- Create: `apoc/frontend/src/AnnotationMargin.tsx`.
- Test: `apoc/frontend/src/AnnotationMargin.test.tsx` (new).

- [ ] **Step 1: Write the failing test for grouping + collision math**

Create `apoc/frontend/src/AnnotationMargin.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { groupByAnchor, layoutTops, type AnnoGroup } from "./AnnotationMargin";
import type { Annotation } from "./api";

const anno = (id: string, anchor: string, domain: string, severity: string): Annotation => ({
  id, poc_id: "p", anchor, domain, severity, title: id, body: "", suggestion: "", created_at: "",
});

describe("groupByAnchor", () => {
  it("merges multiple findings at one section into one group, worst severity wins", () => {
    const groups = groupByAnchor([
      anno("a", "Cost outlook", "cost", "warn"),
      anno("b", "Cost outlook", "compliance", "block"),
      anno("c", "Risks", "security", "info"),
    ]);
    const cost = groups.find((g) => g.slug === "cost-outlook")!;
    expect(cost.items).toHaveLength(2);
    expect(cost.worst).toBe("block");
    expect(new Set(cost.domains)).toEqual(new Set(["cost", "compliance"]));
    expect(groups).toHaveLength(2);
  });
});

describe("layoutTops", () => {
  it("honors desired tops but pushes colliding cards down", () => {
    const groups = [
      { slug: "a", desiredTop: 0, height: 80 },
      { slug: "b", desiredTop: 40, height: 80 }, // would overlap a
      { slug: "c", desiredTop: 400, height: 80 },
    ] as unknown as (AnnoGroup & { desiredTop: number; height: number })[];
    const tops = layoutTops(groups, 12);
    expect(tops[0]).toBe(0);
    expect(tops[1]).toBe(92); // 0 + 80 + 12 gap
    expect(tops[2]).toBe(400); // no collision, stays at anchor
  });
});
```

- [ ] **Step 2: Run — expect failure**

Run: `cd apoc/frontend && npx vitest run src/AnnotationMargin.test.tsx`
Expected: FAIL — module/exports do not exist.

- [ ] **Step 3: Implement `AnnotationMargin.tsx`**

Create `apoc/frontend/src/AnnotationMargin.tsx`:

```tsx
import { useLayoutEffect, useRef, useState } from "react";
import type { Annotation } from "./api";
import { slugify } from "./markdown";

const SEV_RANK: Record<string, number> = { block: 3, warn: 2, info: 1 };
const SEV_BORDER: Record<string, string> = {
  block: "border-red-500/50",
  warn: "border-amber-500/50",
  info: "border-blue-500/40",
};
export const DOMAIN_COLOR: Record<string, string> = {
  compliance: "#a371f7",
  legal: "#a371f7",
  security: "#f85149",
  cost: "#d29922",
  architecture: "#4493f8",
};

export type AnnoGroup = {
  slug: string;
  anchor: string;
  items: Annotation[];
  domains: string[];
  worst: string;
};

// Merge findings that share an anchor (H2 section) into one group.
export function groupByAnchor(annotations: Annotation[]): AnnoGroup[] {
  const m = new Map<string, AnnoGroup>();
  for (const a of annotations) {
    const slug = slugify(a.anchor || "");
    if (!slug) continue;
    let g = m.get(slug);
    if (!g) {
      g = { slug, anchor: a.anchor, items: [], domains: [], worst: "info" };
      m.set(slug, g);
    }
    g.items.push(a);
    if (!g.domains.includes(a.domain)) g.domains.push(a.domain);
    if ((SEV_RANK[a.severity] ?? 1) > (SEV_RANK[g.worst] ?? 1)) g.worst = a.severity;
  }
  return [...m.values()];
}

// Place each card at its desiredTop, but never overlapping the previous card.
export function layoutTops(
  groups: { desiredTop: number; height: number }[],
  gap: number,
): number[] {
  const sorted = [...groups].sort((a, b) => a.desiredTop - b.desiredTop);
  let prevBottom = -Infinity;
  const topBySorted = sorted.map((g) => {
    const top = Math.max(g.desiredTop, prevBottom + gap);
    prevBottom = top + g.height;
    return top;
  });
  // map back to original order
  const tops = new Array<number>(groups.length);
  sorted.forEach((g, i) => {
    const orig = groups.indexOf(g);
    tops[orig] = topBySorted[i];
  });
  return tops;
}

export function AnnotationMargin({
  annotations,
  scrollRef,
  activeSlug,
  onActivate,
}: {
  annotations: Annotation[];
  scrollRef: React.RefObject<HTMLElement | null>; // the shared scroll container
  activeSlug: string | null;
  onActivate: (slug: string) => void;
}) {
  const groups = groupByAnchor(annotations);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);
  const [tops, setTops] = useState<number[]>([]);
  const [maxH, setMaxH] = useState(0);

  // Recompute card tops from the live document layout: desiredTop = section
  // offsetTop within the shared scroll container; then collision push-down.
  useLayoutEffect(() => {
    const root = scrollRef.current;
    if (!root) return;
    const recompute = () => {
      const measured = groups.map((g, i) => {
        const sec = root.querySelector<HTMLElement>(`#sec-${g.slug}`);
        const desiredTop = sec ? sec.offsetTop : 0;
        const height = cardRefs.current[i]?.offsetHeight ?? 80;
        return { desiredTop, height };
      });
      const next = layoutTops(measured, 12);
      setTops(next);
      setMaxH(next.reduce((m, t, i) => Math.max(m, t + measured[i].height), 0) + 40);
    };
    recompute();
    const ro = new ResizeObserver(recompute);
    ro.observe(root);
    window.addEventListener("resize", recompute);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", recompute);
    };
  }, [annotations, scrollRef, groups.length]);

  if (groups.length === 0)
    return <div className="px-3 py-4 text-sm text-white/35">No AI findings.</div>;

  return (
    <div className="relative" style={{ minHeight: maxH }}>
      {groups.map((g, i) => (
        <div
          key={g.slug}
          ref={(el) => {
            cardRefs.current[i] = el;
          }}
          id={`anno-${g.slug}`}
          onClick={() => onActivate(g.slug)}
          style={{ position: "absolute", top: tops[i] ?? 0, left: 0, right: 0 }}
          className={`mx-2 cursor-pointer rounded-lg border bg-[#0d1117] px-3 py-2 transition ${
            SEV_BORDER[g.worst] ?? SEV_BORDER.info
          } ${activeSlug === g.slug ? "ring-2 ring-white/40" : ""}`}
        >
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-white/55">
            <span>⚠ {g.items.length} finding{g.items.length > 1 ? "s" : ""}</span>
            <span className="ml-auto flex gap-1">
              {g.domains.map((d) => (
                <span
                  key={d}
                  title={d}
                  className="h-2 w-2 rounded-full"
                  style={{ background: DOMAIN_COLOR[d] ?? "#8b949e" }}
                />
              ))}
            </span>
          </div>
          <div className="mt-1 truncate text-[11px] text-white/40">in “{g.anchor}”</div>
          <div className="mt-1 grid gap-1.5">
            {g.items.map((a) => (
              <div
                key={a.id}
                className="border-l-2 pl-2"
                style={{ borderColor: DOMAIN_COLOR[a.domain] ?? "#8b949e" }}
              >
                <div className="text-[11px] uppercase tracking-wide text-white/45">
                  {a.domain} · {a.severity}
                </div>
                <div className="text-sm font-medium text-white">{a.title}</div>
                {a.body && <div className="text-xs text-white/70">{a.body}</div>}
                {a.suggestion && (
                  <div className="text-xs text-white/55">
                    <b>Suggestion:</b> {a.suggestion}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run — expect pass**

Run: `cd apoc/frontend && npx vitest run src/AnnotationMargin.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apoc/frontend/src/AnnotationMargin.tsx apoc/frontend/src/AnnotationMargin.test.tsx
git commit -m "feat(frontend): position-aligned, merged AI annotation margin"
```

---

### Task 10: `MarkdownDoc.tsx` (left column)

**Files:**
- Create: `apoc/frontend/src/MarkdownDoc.tsx`.
- Delete: `apoc/frontend/src/PocDocument.tsx`, `apoc/frontend/src/PocDocument.test.tsx`.

- [ ] **Step 1: Create `MarkdownDoc.tsx`**

Create `apoc/frontend/src/MarkdownDoc.tsx`:

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { api, Annotation, Comment, Stakeholder } from "./api";
import { renderDoc, renderInline, slugify } from "./markdown";
import { Mermaid } from "./Mermaid";
import { CommentComposer } from "./CommentComposer";

// Find the slug of the nearest preceding <h2 id="sec-..."> for a node.
function enclosingSlug(el: HTMLElement, root: HTMLElement): string {
  let h: Element | null = el;
  while (h && h !== root) {
    let p: Element | null = h;
    while (p) {
      if (p.tagName === "H2" && p.id.startsWith("sec-")) return p.id.slice(4);
      p = p.previousElementSibling;
    }
    h = h.parentElement;
  }
  return "";
}

export function MarkdownDoc({
  pocId,
  documentMd,
  canEdit,
  reload,
  annotations,
  comments,
  stakeholders,
  me,
  activeSlug,
  onSlugActivate,
}: {
  pocId: string;
  documentMd: string;
  canEdit: boolean;
  reload: () => void;
  annotations: Annotation[];
  comments: Comment[];
  stakeholders: Stakeholder[];
  me: Stakeholder;
  activeSlug: string | null;
  onSlugActivate: (slug: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(documentMd);
  const [saving, setSaving] = useState(false);
  const [composer, setComposer] = useState<{ line: number; slug: string } | null>(null);
  const [posting, setPosting] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const mermaidRoots = useRef<Root[]>([]);

  useEffect(() => setDraft(documentMd), [documentMd]);
  const { html } = useMemo(() => renderDoc(documentMd), [documentMd]);

  const shName = (id: string) => stakeholders.find((s) => s.id === id)?.name ?? "Someone";
  const commentsByLine = useMemo(() => {
    const m = new Map<number, Comment[]>();
    for (const c of comments) {
      if (c.anchor_line == null) continue;
      const l = m.get(c.anchor_line);
      if (l) l.push(c);
      else m.set(c.anchor_line, [c]);
    }
    return m;
  }, [comments]);

  // Mount <Mermaid> into each placeholder after the HTML lands in the DOM.
  useEffect(() => {
    const root = contentRef.current;
    if (!root || editing) return;
    mermaidRoots.current.forEach((r) => r.unmount());
    mermaidRoots.current = [];
    root.querySelectorAll<HTMLElement>(".mermaid-block").forEach((el) => {
      const code = el.getAttribute("data-code") || "";
      const r = createRoot(el);
      r.render(<Mermaid code={code} />);
      mermaidRoots.current.push(r);
    });
    return () => {
      mermaidRoots.current.forEach((r) => r.unmount());
      mermaidRoots.current = [];
    };
  }, [html, editing]);

  // Decorate flagged sections with a finding badge (click → activate slug).
  useEffect(() => {
    const root = contentRef.current;
    if (!root || editing) return;
    root.querySelectorAll(".finding-badge").forEach((b) => b.remove());
    const slugs = new Set(annotations.map((a) => slugify(a.anchor || "")));
    slugs.forEach((slug) => {
      const h = root.querySelector<HTMLElement>(`#sec-${slug}`);
      if (!h) return;
      const n = annotations.filter((a) => slugify(a.anchor || "") === slug).length;
      const badge = document.createElement("button");
      badge.type = "button";
      badge.className = "finding-badge";
      badge.textContent = `⚠ ${n}`;
      badge.onclick = (e) => {
        e.preventDefault();
        onSlugActivate(slug);
      };
      h.appendChild(badge);
    });
  }, [html, annotations, editing, onSlugActivate]);

  // Active-section highlight band.
  useEffect(() => {
    const root = contentRef.current;
    if (!root) return;
    root.querySelectorAll(".anno-active").forEach((e) => e.classList.remove("anno-active"));
    if (!activeSlug || editing) return;
    const h = root.querySelector<HTMLElement>(`#sec-${activeSlug}`);
    if (!h) return;
    h.classList.add("anno-active");
    let el = h.nextElementSibling;
    while (el && el.tagName !== "H2") {
      el.classList.add("anno-active");
      el = el.nextElementSibling;
    }
    const rect = h.getBoundingClientRect();
    if (rect.top < 64 || rect.bottom > window.innerHeight - 24)
      h.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [activeSlug, html, editing]);

  // Hover gutter "+" → open composer for that block's line.
  const onContentClick = (e: React.MouseEvent) => {
    const t = e.target as HTMLElement;
    const plus = t.closest(".gutter-add") as HTMLElement | null;
    if (!plus) return;
    const block = plus.closest("[data-line]") as HTMLElement | null;
    if (!block || !contentRef.current) return;
    const line = parseInt(block.getAttribute("data-line") || "0", 10);
    setComposer({ line, slug: enclosingSlug(block, contentRef.current) });
  };

  // Inject a "+" affordance into every block that has a source line.
  useEffect(() => {
    const root = contentRef.current;
    if (!root || editing) return;
    root.querySelectorAll<HTMLElement>("[data-line]").forEach((b) => {
      if (b.querySelector(":scope > .gutter-add")) return;
      const add = document.createElement("button");
      add.type = "button";
      add.className = "gutter-add";
      add.textContent = "+";
      add.title = "Comment on this line";
      b.appendChild(add);
    });
  }, [html, editing]);

  const submitComment = async (body: string) => {
    if (!composer) return;
    setPosting(true);
    try {
      await api.addComment(
        pocId,
        { stakeholder_id: me.id, body, anchor_line: composer.line, anchor_slug: composer.slug },
        me.role,
      );
      setComposer(null);
      reload();
    } finally {
      setPosting(false);
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.saveDocument(pocId, { document_md: draft }, "architect");
      setEditing(false);
      reload();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="relative">
      {canEdit && (
        <div className="sticky top-0 z-30 mb-3 flex items-center gap-2 border-b border-white/10 bg-[#0c0e16] py-2">
          {!editing ? (
            <button
              onClick={() => setEditing(true)}
              className="rounded-lg border border-white/15 px-3 py-1.5 text-sm text-white/80 hover:bg-white/5"
            >
              Edit document
            </button>
          ) : (
            <>
              <button
                onClick={save}
                disabled={saving}
                className="rounded-lg bg-blue-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-400 disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save"}
              </button>
              <button
                onClick={() => {
                  setEditing(false);
                  setDraft(documentMd);
                }}
                className="rounded-lg border border-white/15 px-3 py-1.5 text-sm text-white/60 hover:bg-white/5"
              >
                Cancel
              </button>
              <span className="text-xs text-blue-300/80">Editing Markdown — Mermaid blocks render on save.</span>
            </>
          )}
        </div>
      )}

      {editing ? (
        <div className="grid grid-cols-2 gap-3">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="h-[70vh] w-full resize-none rounded-lg border border-white/12 bg-[#0d1117] p-3 font-mono text-xs text-white outline-none"
          />
          <div
            className="md doc-html h-[70vh] overflow-y-auto rounded-lg border border-white/8 p-3"
            dangerouslySetInnerHTML={{ __html: renderDoc(draft).html }}
          />
        </div>
      ) : (
        <div
          ref={contentRef}
          className="md doc-html gh-doc"
          onClick={onContentClick}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      )}

      {composer && !editing && (
        <div className="fixed bottom-4 left-4 z-40 w-[28rem] max-w-[40vw]">
          <div className="mb-1 text-xs text-blue-300">
            Commenting on line {composer.line}
            {composer.slug && ` · ${composer.slug}`}
          </div>
          <CommentComposer
            placeholder={`Comment as ${me.name}… (Markdown supported)`}
            submitting={posting}
            onCancel={() => setComposer(null)}
            onSubmit={submitComment}
          />
        </div>
      )}

      {/* Inline comment threads, grouped by line, shown under the document */}
      {commentsByLine.size > 0 && !editing && (
        <div className="mt-6 border-t border-white/10 pt-4">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-white/40">
            Inline comments
          </h4>
          <div className="grid gap-2">
            {[...commentsByLine.entries()]
              .sort((a, b) => a[0] - b[0])
              .map(([line, list]) => (
                <div key={line} className="rounded-lg border border-white/8 bg-white/[0.02] p-2">
                  <div className="text-[11px] text-blue-300/70">line {line}</div>
                  {list.map((c) => (
                    <div key={c.id} className="mt-1">
                      <div className="text-xs text-white/50">{shName(c.stakeholder_id)}</div>
                      <div
                        className="md text-sm text-white/85"
                        dangerouslySetInnerHTML={{ __html: renderInline(c.body) }}
                      />
                    </div>
                  ))}
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Delete the old document component + its test**

```bash
git rm apoc/frontend/src/PocDocument.tsx apoc/frontend/src/PocDocument.test.tsx
```

- [ ] **Step 3: Typecheck (will still error until api.ts is updated in Task 11)**

Run: `cd apoc/frontend && npx tsc --noEmit`
Expected: errors only about `Comment.anchor_line`, `Poc.document_md`, etc. (resolved in Task 11). No errors inside `MarkdownDoc.tsx` logic itself once those types exist.

- [ ] **Step 4: Commit**

```bash
git add apoc/frontend/src/MarkdownDoc.tsx
git commit -m "feat(frontend): MarkdownDoc left column (render, gutter comments, mermaid mount, edit/preview)"
```

---

### Task 11: `api.ts` types + payloads

**Files:**
- Modify: `apoc/frontend/src/api.ts` (`Annotation` ok; `Comment` lines 74-80; `Poc` lines 111-119).

- [ ] **Step 1: Extend `Comment`**

Replace the `Comment` interface (lines 74-80) with:

```ts
export interface Comment {
  id: string;
  annotation_id: string | null;
  stakeholder_id: string;
  body: string;
  anchor_line?: number | null;
  anchor_slug?: string | null;
  created_at: string;
}
```

- [ ] **Step 2: Update `Poc`**

Replace the `Poc` interface (lines 111-119) with:

```ts
export interface Poc {
  id: string;
  title: string;
  version: number;
  markdown: string;
  document_md: string;
  design: any;
}
```

- [ ] **Step 3: Typecheck**

Run: `cd apoc/frontend && npx tsc --noEmit`
Expected: errors now only in `ProjectView.tsx` (still importing the old `PocDocument` / referencing `poc.diagrams` / `document_html`), fixed next.

- [ ] **Step 4: Commit**

```bash
git add apoc/frontend/src/api.ts
git commit -m "feat(frontend): api types for document_md + comment anchors"
```

---

### Task 12: `ProjectView.tsx` — rewrite `ReviewPane`

**Files:**
- Modify: `apoc/frontend/src/ProjectView.tsx` (imports lines 1-5; `ReviewPane` lines 166-352).

- [ ] **Step 1: Update imports**

Replace lines 1-5 with:

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { api, PocBundle, ResearchNote, Stakeholder } from "./api";
import { slugify } from "./markdown";
import { tokenizeDigest } from "./trace";
import { MarkdownDoc } from "./MarkdownDoc";
import { AnnotationMargin } from "./AnnotationMargin";
```

- [ ] **Step 2: Replace the whole `ReviewPane` function (lines 166-352)**

```tsx
function ReviewPane({
  bundle,
  me,
  reload,
}: {
  bundle: PocBundle;
  me: Stakeholder;
  reload: () => void;
}) {
  const { poc, annotations, stakeholders, comments, reviews } = bundle;
  const scrollRef = useRef<HTMLDivElement>(null);
  const [activeSlug, setActiveSlug] = useState<string | null>(null);

  const myDomain = ROLE_DOMAIN[me.role];
  const myReport = reviews.find((r) => r.role === me.role);
  const [showAll, setShowAll] = useState(!myDomain);
  const shown = useMemo(
    () => (showAll || !myDomain ? annotations : annotations.filter((a) => a.domain === myDomain)),
    [showAll, myDomain, annotations],
  );

  // Activating a section scrolls its card into view, and vice versa.
  const activate = (slug: string) => {
    setActiveSlug(slug);
    window.requestAnimationFrame(() => {
      scrollRef.current?.querySelector(`#anno-${slug}`)?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    });
  };

  return (
    <div className="grid h-full grid-cols-[1fr_24rem_18rem] divide-x divide-white/10">
      {/* Shared scroll container holds the document (left) + aligned margin (middle) */}
      <div ref={scrollRef} className="col-span-2 overflow-y-auto">
        <div className="grid grid-cols-[1fr_24rem]">
          <div className="px-6 pb-24">
            {myReport && (
              <div className="my-3 rounded-lg border border-blue-500/30 bg-blue-500/[0.07] p-3">
                <div className="text-[11px] uppercase tracking-wide text-blue-300/80">
                  Your AI review draft · verdict{" "}
                  <span className={VERDICT[myReport.verdict] ?? ""}>{myReport.verdict}</span>
                </div>
                <div className="mt-1 text-sm text-white/80">{myReport.summary}</div>
              </div>
            )}
            <div className="mb-2 flex items-center gap-2">
              {myDomain && (
                <button
                  onClick={() => setShowAll((v) => !v)}
                  className="rounded-md border border-white/12 px-2 py-0.5 text-[11px] text-white/60 hover:text-white"
                >
                  {showAll ? "all domains" : `my domain: ${myDomain}`}
                </button>
              )}
            </div>
            <MarkdownDoc
              pocId={poc!.id}
              documentMd={poc!.document_md || ""}
              canEdit={me.role === "architect"}
              reload={reload}
              annotations={shown}
              comments={comments}
              stakeholders={stakeholders}
              me={me}
              activeSlug={activeSlug}
              onSlugActivate={activate}
            />
          </div>
          <div className="border-l border-white/10 bg-[#0b0e15] pt-3">
            <AnnotationMargin
              annotations={shown}
              scrollRef={scrollRef}
              activeSlug={activeSlug}
              onActivate={activate}
            />
          </div>
        </div>
      </div>

      {/* Right column: reserved for future stakeholder ↔ AI chat */}
      <div className="flex flex-col items-center justify-center bg-[#0b0e15] px-4 text-center text-sm text-white/30">
        Stakeholder ↔ AI discussion
        <span className="mt-1 text-xs text-white/20">(coming soon)</span>
      </div>
    </div>
  );
}
```

(Remove the now-unused `Annotation`, `Comment` imports if `tsc` flags them; keep `slugify` only if used — if `tsc` says it's unused, drop it from the import in Step 1.)

- [ ] **Step 3: Typecheck + build**

Run: `cd apoc/frontend && npx tsc --noEmit && npm run build`
Expected: no errors; build succeeds.

- [ ] **Step 4: Commit**

```bash
git add apoc/frontend/src/ProjectView.tsx
git commit -m "feat(frontend): GitHub-style ReviewPane (shared-scroll doc + aligned margin)"
```

---

### Task 13: Delete dead React Flow files

**Files:**
- Delete: `DiagramCanvas.tsx`, `DiagramFocusModal.tsx`, `diagramLayout.ts`, `diagramLayout.test.ts`, `diagramEdges.ts`, `diagramEdges.test.ts`, `ArchitectureNode.tsx`, `docHtml.ts`.

- [ ] **Step 1: Confirm nothing imports them**

Run: `cd apoc/frontend && grep -rEn "DiagramCanvas|DiagramFocusModal|diagramLayout|diagramEdges|ArchitectureNode|docHtml|@xyflow|dagre|framer-motion" src` 
Expected: **no matches** (if `framer-motion` still matches and is only used by deleted files, also `npm uninstall framer-motion`). If anything else matches, fix that import before deleting.

- [ ] **Step 2: Delete the files**

```bash
cd apoc/frontend
git rm src/DiagramCanvas.tsx src/DiagramFocusModal.tsx src/diagramLayout.ts src/diagramLayout.test.ts src/diagramEdges.ts src/diagramEdges.test.ts src/ArchitectureNode.tsx src/docHtml.ts
```

- [ ] **Step 3: Build + test**

Run: `cd apoc/frontend && npx tsc --noEmit && npm run build && npm test`
Expected: build + all vitest suites pass.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(frontend): remove React Flow diagram code (superseded by mermaid)"
```

---

### Task 14: GitHub-review CSS

**Files:**
- Modify: `apoc/frontend/src/index.css`.

- [ ] **Step 1: Append the review styles**

Add to the end of `apoc/frontend/src/index.css`:

```css
/* --- GitHub-style POC document ------------------------------------------- */
.gh-doc { position: relative; padding-left: 2.75rem; }
/* line gutter: each anchored block reserves a left rail showing a hover "+". */
.gh-doc [data-line] { position: relative; }
.gh-doc [data-line]::before {
  content: attr(data-line);
  position: absolute; left: -2.75rem; width: 2.25rem;
  text-align: right; color: rgba(255,255,255,0.18);
  font: 11px/1.6 ui-monospace, monospace; user-select: none;
}
.gh-doc .gutter-add {
  position: absolute; left: -2.75rem; top: 0; width: 1.1rem; height: 1.1rem;
  display: none; align-items: center; justify-content: center;
  border-radius: 4px; background: #4493f8; color: white; font-weight: 700;
  line-height: 1; cursor: pointer;
}
.gh-doc [data-line]:hover > .gutter-add { display: flex; }

/* finding badge appended to flagged H2s */
.finding-badge {
  margin-left: 0.5rem; padding: 0 0.4rem; border-radius: 999px;
  background: rgba(210,153,34,0.18); color: #d29922; font-size: 11px; cursor: pointer;
}
/* active-section highlight band */
.anno-active { background: rgba(68,147,248,0.08); border-radius: 6px; }

/* readable markdown tables, like GitHub */
.md.doc-html table { border-collapse: collapse; width: 100%; margin: 0.75rem 0; font-size: 0.85rem; }
.md.doc-html th, .md.doc-html td { border: 1px solid rgba(255,255,255,0.1); padding: 0.4rem 0.6rem; text-align: left; }
.md.doc-html th { background: rgba(255,255,255,0.04); }
.md.doc-html h2 { margin-top: 1.5rem; font-size: 1.15rem; font-weight: 600; }
.md.doc-html h3 { margin-top: 1rem; font-weight: 600; }
.md.doc-html p, .md.doc-html li { line-height: 1.6; }
.md.doc-html ul { list-style: disc; padding-left: 1.25rem; }
.md a { color: #4493f8; text-decoration: underline; }
```

- [ ] **Step 2: Commit**

```bash
git add apoc/frontend/src/index.css
git commit -m "style(frontend): GitHub-review gutter, finding badge, markdown tables"
```

---

### Task 15: Full verification (fresh POC end-to-end)

**Files:** none (verification only).

- [ ] **Step 1: Backend tests**

Run: `cd apoc/backend && python -m pytest -q`
Expected: all pass.

- [ ] **Step 2: Frontend tests + build**

Run: `cd apoc/frontend && npm test && npm run build`
Expected: all pass, build succeeds.

- [ ] **Step 3: Run the app and create a NEW POC**

Start backend + frontend (`apoc/backend/run.sh` and `cd apoc/frontend && npm run dev`). In the UI, run intake → Generate a fresh POC (old POCs lack `document_md`).

- [ ] **Step 4: Verify the review screen** (check each, fix source + re-verify if any fails)
  - Left column renders the Markdown document with a line-number gutter; hovering a line shows a "+".
  - Architecture (and any flow) diagrams render as themed Mermaid SVGs; clicking one opens the zoom/pan lightbox; Esc closes.
  - Middle column AI cards sit beside the sections they flag; a section flagged by two domains shows ONE merged card with two domain dots and the worst-severity border; nearby cards don't overlap.
  - Clicking a card highlights + scrolls its section; clicking a section's `⚠` badge highlights + scrolls its card.
  - Clicking a line "+" opens the Write/Preview composer; posting a comment (as any role) reloads and shows it under "Inline comments" with Markdown rendered.
  - As architect: "Edit document" → Markdown textarea + live preview; Save persists; diagrams re-render.
  - Right column shows the reserved "coming soon" placeholder.

- [ ] **Step 5: Final commit (if any verification fixes were made)**

```bash
git add -A
git commit -m "fix(frontend): review verification adjustments"
```

---

## Self-review (completed during authoring)

- **Spec coverage:** Markdown doc (Tasks 1-4, 6, 10), inline mermaid + render (Tasks 2, 7), drop React Flow (Tasks 3, 5, 13), line gutter + inline markdown comments (Tasks 4, 8, 10, 14), position-aligned + merged annotations (Task 9, 12), edit-as-markdown (Task 10), DB migration (Task 1), endpoints (Task 4), right column reserved (Task 12), error handling — mermaid fallback (Task 7), sanitize (Task 6), legacy POC empty state (Task 10/15). All spec sections map to a task.
- **Placeholders:** none — every code step contains full code; every run step has expected output.
- **Type consistency:** `document_md` (db/api/generation/main/MarkdownDoc), `anchor_line`/`anchor_slug` (db/api/main/CommentComposer flow/MarkdownDoc), `groupByAnchor`/`layoutTops`/`AnnoGroup` (AnnotationMargin + its test), `renderDoc`/`renderInline`/`slugify` (markdown + consumers) all align across tasks.
- **Known tunables (non-blocking):** ESM/CJS shape of `beautiful-mermaid` (Task 5 Step 2 + Task 7 Step 3 cover the `.d.ts` fallback); `framer-motion` removal is conditional on Task 13 Step 1.
