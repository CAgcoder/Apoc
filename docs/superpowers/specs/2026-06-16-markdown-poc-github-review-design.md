# Design: Markdown POC document + beautiful-mermaid + GitHub-style review refactor

Date: 2026-06-16
Branch: `apoc`
Status: Approved design (pending implementation plan)

## Problem / Motivation

Two coupled limitations of the current POC review experience:

1. **The POC document is LLM-emitted HTML** (`pocs.document_html`), rendered with
   `dangerouslySetInnerHTML` + `contenteditable` inline editing. HTML is not native
   to export, is awkward to diff/anchor at fine granularity, and the hand-rolled
   editing path is fiddly.
2. **Diagrams are React Flow** (`@xyflow/react`): the architecture graph is built
   deterministically in `diagrams.py`, laid out with dagre, and edited in a focus
   modal. This is a lot of machinery (two representations, structural editor,
   custom nodes, edge inference, layout engine) for diagrams that — now that an
   auto-layout engine is in play — no longer need a bespoke deterministic builder.

The user wants a **complete refactor of the review frontend** so that creating a
new POC yields a screen that reads like **GitHub's pull-request code-review (file
diff) view**: a readable document on the left with a line-number gutter and
hover-to-comment, position-aligned AI findings in the middle, and a GitHub-style
markdown comment composer.

## Goals

- POC document is **Markdown** (single source of truth, natively exportable).
- All diagrams (architecture **and** process/sequence flowcharts) are authored as
  ` ```mermaid ` fenced blocks **inside the Markdown** by the LLM, and rendered to
  polished SVG at display time via **beautiful-mermaid** (`renderMermaidSVG`).
  The SVG is ephemeral (computed in-browser, never stored).
- A GitHub-PR-review-style left column: rendered Markdown + line-number gutter +
  hover "+" → inline Markdown comment composer (Write/Preview), comments anchored
  to specific source lines.
- A middle column of AI annotations **vertically aligned** to the spot in the
  document they refer to; multiple findings at one spot are merged into one card.
- Drop React Flow entirely; "enlarge a diagram" = a zoom/pan lightbox over the
  Mermaid SVG.
- Architect edits the **Markdown text** (including the mermaid blocks) with a live
  preview; Save persists the markdown.

## Non-goals (this round)

- The **right column** (committee comments → future stakeholder ↔ AI chat). Left
  untouched / reserved.
- Backward-compatible rendering of legacy HTML POCs. Consistent with prior
  precedent ("regenerate to get the new renderer"), POCs created before this
  change will need regeneration.
- Real diff semantics (red/green add/remove gutters). The POC is not a
  before/after diff; we adopt GitHub's **visual language** (file header, line
  gutter, inline threads), not literal diff coloring.
- Manual node dragging / a structural diagram editor (removed with React Flow).
- An offline/server-side SVG or PNG export of diagrams (revisit later).

## Decisions (locked during brainstorming)

| Area | Decision |
| --- | --- |
| Document format | LLM emits **Markdown** (not HTML). Stored in new `pocs.document_md`. |
| Document view | **Rendered** Markdown (pretty tables/headings/diagrams) **with a line-number gutter**, not raw source. Comments still anchor to source lines via `markdown-it` token `.map`. |
| Diagrams | All diagrams are ` ```mermaid ` blocks **written by the LLM** inside the document. No `diagrams.py`, no `diagrams_json`. |
| Diagram render | **beautiful-mermaid** `renderMermaidSVG(code, theme)` — synchronous, `useMemo`, GitHub theme. SVG is ephemeral, never persisted. |
| Enlarge | Click a diagram → zoom/pan **lightbox** over the same SVG. No React Flow. |
| React Flow | **Removed** (`@xyflow/react`, `dagre`, `DiagramCanvas`, `DiagramFocusModal`, `diagramLayout`, `diagramEdges`, `ArchitectureNode`). |
| Editing | Architect toggles edit → **Markdown textarea + live preview**; Save → `POST /api/pocs/{id}/document {document_md}`. Replaces `contenteditable`. |
| Comments (this round) | GitHub-style **inline, line-anchored** comments with a Write/Preview Markdown composer; bodies rendered as Markdown. |
| AI annotations | Keep **section-level** anchoring (H2 slug), but **position-align** the cards to their section in the document, and **merge** multiple findings at one anchor into a single card. |
| Right column | Out of scope; reserved for future stakeholder/AI chat. |

## Architecture overview

```
POC bundle (api.pocBundle)
  poc.document_md  ── Markdown (10 fixed H2 sections, md tables, ```mermaid blocks)
  annotations[]    ── AI findings (anchor = H2 heading text, domain, severity, …)
  comments[]       ── now carry { anchor_line, anchor_slug } for line anchoring

Frontend ReviewPane (full rewrite)
  ┌ shared vertical scroll container ─────────────────────────────┐
  │  LEFT: MarkdownDoc            MIDDLE: AnnotationMargin         │
  │   - markdown-it render         - cards absolutely positioned   │
  │   - line-number gutter           at each anchor's offsetTop     │
  │   - ```mermaid → <Mermaid>      - merged card per anchor        │
  │   - hover "+" → CommentComposer - collision push-down + connector│
  └────────────────────────────────────────────────────────────────┘
  RIGHT: (reserved — future)
```

## Backend changes

### Generation (`generation.py`, `prompts.py`)
- Rewrite `prompts.DOCUMENT_SYSTEM` to output **Markdown**:
  - Same 10 fixed H2 sections, in order (reviews/annotations still anchor to the
    heading text): Executive summary, Context & goals, Requirements mapping,
    Proposed architecture, Technology choices, Non-functional requirements,
    Key decisions, Risks, Cost outlook, Open questions.
  - Tables as GitHub-flavored Markdown tables.
  - Diagrams as ` ```mermaid ` fenced blocks. The "Proposed architecture" section
    contains the system architecture (`graph`/`flowchart` mermaid). Other sections
    may include a sequence/state/flow diagram where it clarifies (e.g. a request
    flow). Prompt guidance: prefer `flowchart LR`/`graph TD`; keep labels short;
    every node connected; no styling directives (theme comes from the renderer).
  - Remove the `<figure data-diagram="architecture">` marker instruction.
- `generation.py`: remove the `diagrams.build_architecture_diagram(design)` call
  and the `diagrams` import; stop writing `diagrams_json`. Persist `document_md`.
  Replace `_clean_html_doc` with a light Markdown cleanup (strip stray code fences
  around the whole doc, trim). Downstream consumers that read `document_html` (deck
  user prompt at `generation.py:265,287`) switch to the Markdown text (strip
  fences/render to text as needed) — verify the deck step still gets sensible input.
- Delete `backend/app/diagrams.py` and `tests/test_diagrams.py`.

### Data model (`db.py`)
- Add migration entries (auto-applied on startup via `db._MIGRATIONS`):
  - `("pocs", "document_md", "TEXT NOT NULL DEFAULT ''")`
  - `("comments", "anchor_line", "INTEGER")`
  - `("comments", "anchor_slug", "TEXT")`
- `document_html` and `diagrams_json` columns remain (legacy) but are no longer
  written or read by new code. (Dropping columns in SQLite is intrusive; leaving
  them inert is cleaner and harmless.)

### Endpoints (`main.py`)
- `get_poc_bundle`: include `poc.document_md`; stop deriving `poc["diagrams"]`
  from `diagrams_json`. Comments already returned; they now include the two anchor
  fields.
- `POST /api/pocs/{id}/document` (architect-only, unchanged gate): accept
  `{document_md}` and persist it. Drop the `document_html` / `diagrams` branches.
- `POST /api/pocs/{id}/comments`: accept optional `anchor_line` (int) and
  `anchor_slug` (str) in addition to the existing `annotation_id`; persist them.

## Frontend changes

### Dependencies
- **Add:** `beautiful-mermaid`, `markdown-it` (+ `@types/markdown-it`).
- **Remove:** `@xyflow/react`, `dagre` (+ types). `framer-motion` stays only if
  still used elsewhere (the lightbox can use it for the zoom transition; otherwise
  drop it too).

### Files removed
`DiagramCanvas.tsx`, `DiagramFocusModal.tsx`, `diagramLayout.ts(.test.ts)`,
`diagramEdges.ts(.test.ts)`, `ArchitectureNode.tsx`, and the diagram-specific
parts of `docHtml.ts` (the whole file likely goes away — its figure-marker /
heading-id logic is replaced by markdown-it rendering).

### New / rewritten modules
- **`markdown.ts` (rewrite):** wrap `markdown-it` configured for GFM tables +
  fenced code. Expose:
  - `renderDoc(md)` → `{ html, lineMap }` where `lineMap` ties rendered
    top-level blocks to their source line range (from token `.map`), and each H2
    gets `id="sec-<slug>"` (keep `slugify`). Mermaid fences are rendered to a
    placeholder element (e.g. `<div class="mermaid-block" data-code="…">`) that
    React swaps for `<Mermaid>`.
  - `renderInline(md)` → sanitized HTML for comment bodies / preview.
  - Sanitize output (markdown-it `html:false` + escape) so user comment Markdown
    can't inject scripts.
- **`Mermaid.tsx`:** `useMemo(() => renderMermaidSVG(code, theme))` (theme uses
  CSS vars: `bg`/`fg`/`accent` from the app palette, `transparent:true`, GitHub
  dark). Renders the SVG; on error shows the raw code in a `<pre>`. Click →
  `MermaidLightbox`.
- **`MermaidLightbox.tsx`:** centered modal with the enlarged SVG; wheel/buttons
  zoom, drag to pan; Esc / backdrop closes.
- **`MarkdownDoc.tsx`** (replaces `PocDocument.tsx`): the left column.
  - Renders `renderDoc(document_md)`; mounts `<Mermaid>` into mermaid placeholders.
  - **Line gutter:** a left rail showing line numbers aligned to blocks; each row
    hover reveals a "+" that opens `CommentComposer` anchored to that line
    (`anchor_line` + the enclosing H2 `anchor_slug`).
  - **Existing comments** render as inline threads beneath their anchored line.
  - **Edit mode (architect):** toggle → split view (Markdown `<textarea>` left,
    live `renderDoc` preview right); Save → `api.saveDocument(pocId,{document_md})`.
  - Keeps the section-finding decorations (dashed underline + `⚠ n` badge on
    flagged H2s) driven by `annotations`, and the `activeAnchor` highlight band.
- **`CommentComposer.tsx`:** GitHub-style box with **Write / Preview** tabs
  (Preview = `renderInline`), Cancel / Comment buttons; submit →
  `api.addComment(pocId,{stakeholder_id, body, anchor_line, anchor_slug})`.
- **`AnnotationMargin.tsx`** (middle column, see next section).

### Middle column: position-aligned, merged AI annotations
- **Alignment:** left `MarkdownDoc` and middle `AnnotationMargin` live in **one
  shared vertical scroll container** so they scroll together. Each annotation
  card is **absolutely positioned**; its `top` = the `offsetTop` of its anchored
  H2 section within the scroll container. Recompute on: initial layout, window
  resize, and after Mermaid SVGs render (they change document height) — via a
  `ResizeObserver` on the document content + a layout effect.
- **One spot, multiple problems** (e.g. finance **and** compliance flag the same
  section): merge all findings for an anchor into **one card** at that anchor:
  - Header: `⚠ {n} findings` + one colored dot per **domain** present
    (compliance / security / cost / architecture / legal each a fixed color).
  - Body: one row per finding, prefixed with its domain color bar + severity;
    show `title`, `body`, optional `suggestion`.
  - Card border color = the **worst** severity among them (block > warn > info).
  - Collapse when many rows; expand on click.
- **Collision avoidance:** when two cards (different, nearby anchors) would
  overlap in Y, push the lower card down past the previous card's bottom (so it
  may sit slightly below its true anchor). On hover/active, draw the existing
  highlight band + a thin connector line from the card to its section so the
  association stays clear despite drift.
- **Linkage (kept):** click a card → highlight + scroll its section; click a
  section's `⚠` badge → highlight + scroll its card.

### `api.ts`
- `PocBundle.poc` gains `document_md`; drop `diagrams`.
- `Comment` gains `anchor_line?: number`, `anchor_slug?: string`.
- `addComment` payload gains `anchor_line?`, `anchor_slug?`.
- `saveDocument` payload becomes `{ document_md }`.

### `ProjectView.tsx`
- Rewrite `ReviewPane` to the two-column shared-scroll layout above (right column
  reserved). `DeckPane`, `ApprovalsPane`, `TracePane` unchanged.

## Data flow

1. Generation: LLM → Markdown (with ` ```mermaid ` blocks) → `pocs.document_md`.
2. Bundle load → `MarkdownDoc` renders Markdown; `<Mermaid>` turns each fenced
   block into an SVG in-browser (nothing stored).
3. AI review → `annotations` (anchor = H2 heading) → `AnnotationMargin` positions
   & merges them beside the document.
4. Reviewer hovers a line → `CommentComposer` → `POST comments {anchor_line,
   anchor_slug}` → reload → inline thread under that line.
5. Architect Edit → Markdown textarea + preview → Save → `document_md` persisted.

## Error handling

- **Mermaid render failure:** `renderMermaidSVG` throws → `<Mermaid>` catches and
  shows the raw mermaid code in a `<pre>` with a subtle "diagram failed to render"
  note, so a bad LLM diagram never blanks the document.
- **Markdown sanitize:** comment bodies and doc are rendered with HTML disabled +
  escaping; no raw HTML injection.
- **Anchor drift after edits:** `anchor_line` may move when the architect edits
  the doc; `anchor_slug` (the enclosing H2) is the fallback so a comment can still
  re-locate to its section. Acceptable for the demo; no diff-rebase machinery.
- **Legacy POCs:** if `document_md` is empty (pre-refactor POC), show an empty
  state prompting regeneration rather than attempting to render old HTML.

## Testing

- **Backend:** `prompts`/generation test that a generated/representative document
  is Markdown with the 10 H2 sections and at least one ` ```mermaid ` block;
  document save round-trips `document_md`; comment create persists `anchor_line` /
  `anchor_slug`. Remove `tests/test_diagrams.py`.
- **Frontend (vitest):**
  - `markdown.ts`: `renderDoc` produces section ids, a correct `lineMap`, and
    mermaid placeholders; `renderInline` escapes scripts.
  - `AnnotationMargin`: merges multiple findings at one anchor into one card with
    the right domain dots + worst-severity border; collision push-down keeps cards
    non-overlapping.
  - `Mermaid`: falls back to `<pre>` on a bad diagram.
- **Runtime verification:** create a fresh POC; confirm the GitHub-style review
  renders (gutter, mermaid SVGs, lightbox zoom), AI cards align to their sections,
  a multi-domain section shows one merged card, a line comment posts and renders,
  and architect edit/preview/save works.

## Open questions

None blocking. Tunable during implementation: exact gutter granularity
(per-source-line vs per-rendered-block) and the precise mermaid theme palette;
both are visual polish, not architecture.
