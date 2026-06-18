# Design: Diagram focus-mode + deterministic auto-layout

Date: 2026-06-14
Branch: `apoc`
Status: Approved design (pending implementation plan)

## Problem

The architecture diagram in the POC document renders with messy node positions
and tangled edges. The mess does **not** come from the LLM — the model only
emits semantic `design.components` and `data_flows` (no coordinates). Positions
are computed by an insertion-order grid in `backend/app/diagrams.py`
(`(i % _COLS) * _COL_W`), which ignores which node connects to which, so related
nodes land far apart and edges cross. Edges also use React Flow's default bezier
rendering with default handles, which tangles.

A skill constraining the LLM cannot fix this: a Claude Code skill constrains the
development agent, not APoc's runtime generation call, and the runtime call does
not produce positions in the first place. The fix is product code: a real graph
layout pass plus semantic node/edge rendering.

## Goals

- Clean, deterministic, stable layout that does not drift across regeneration or
  edits.
- Clicking the diagram zooms it into a centered focus modal; the architect can
  edit structure there, other roles get a read-only enlarged view.
- Modern, polished node/edge visuals.

## Non-goals

- Manual coordinate dragging (explicitly removed — see Edit Scope).
- SVG/PNG export and deck embedding (a separate later phase; noted below).
- A diagram authoring skill (revisit only when multiple diagram types exist).

## Decisions (locked)

| Area | Decision |
| --- | --- |
| Focus interaction | Click inline diagram → shared-element zoom into a **centered modal at ~60%** of the page; review interface dimmed behind. Esc / backdrop click closes. |
| Role gate | Only `architect` edits; all other roles get read-only zoom. Reuse existing gate `me.role === "architect"` (`frontend/src/ProjectView.tsx:120`). No new permission system. |
| LLM contract | Each `design.components` entry gains a semantic `type`. The model outputs nodes (id, label, type) + edges (source, target, label). It never outputs positions. |
| Edit scope | **Structure only.** Architect can add/remove nodes, change node label + type, add/remove edges, change edge direction + label. No manual dragging. dagre recomputes on every structural change. |
| Coordinates | Never persisted. `diagrams_json` stores the structural node/edge list without positions; positions are recomputed client-side on load and after each edit. |
| Layout engine | **dagre, in the frontend.** Reads React Flow v12 cached `node.measured` sizes (no DOM reflow). pretext is not used now — measurement is not the bottleneck and React Flow already caches sizes; reconsider pretext only for a future DOM-free SVG export path. |
| Layout direction | **LR** (left-to-right), fixed. No direction toggle in v1. |
| Node type enum | 8 categories: `frontend`, `backend`, `database`, `cloud`, `security`, `messagebus`, `external`, `gateway`. Fallback to `backend` for unmatched/missing. Nodes remain 1:1 with POC-document components; `type` is only a visual category. |
| Controls | Reuse React Flow's existing `<Controls>` (provides fitView). No custom layout control widget. |
| Styling | Tailwind v4 (already installed), hand-rolled to a shadcn/Vercel aesthetic. **Do not add shadcn/ui** (overkill for a node card + Tailwind-v4 setup friction). |
| Animation | Add **framer-motion**, scoped to the modal shared-element zoom (`layoutId`) and node micro-interactions (select/connect). This is the one new runtime dependency. |

## Architecture

### 1. Data contract (backend + DB)

- **Generation** (`backend/app/generation.py`): the design prompt requires a
  `type` per component from the 8-value enum. On parse, validate each `type`;
  illegal or missing values fall back to `backend` (or a keyword guess). The
  diagram is always valid by construction.
- **`build_architecture_diagram`** (`backend/app/diagrams.py`): remove the grid
  coordinate formula. Emit nodes as `{id, data: {label, type, subtitle?}}` with
  **no `position`**. `subtitle` is the component's `tech` (the old `detail`
  string, kept as a short secondary line). Emit edges as
  `{id, source, target, label}`. Fix the
  existing `resolve()` bug that **silently drops** an edge whose endpoint
  matches no component — unmatched endpoints must be surfaced (logged / counted),
  not disappeared.
- **Persistence**: nodes saved to `diagrams_json` carry no `position`. The
  frontend save path (`PocDocument.tsx` `saveDocument` → `cleanDiagrams`) strips
  coordinates before persisting.

### 2. Layout pipeline (frontend)

- New `frontend/src/diagramLayout.ts`: pure function `layout(nodes, edges) ->
  positionedNodes`. Runs dagre with `rankdir: "LR"`. Node sizes read from React
  Flow's cached `node.measured.width/height`; first paint uses a label-length
  estimate as fallback.
- Invoked (a) on diagram load and (b) after every structural edit. Output is
  deterministic for a given node/edge set.

### 3. Focus modal + interaction (frontend)

- Inline diagram renders as a **read-only preview** (React Flow interaction off).
- Click → framer-motion `layoutId` shared-element transition from the inline
  thumbnail into a centered modal (~60% of viewport), review dimmed behind.
  Esc / backdrop closes with the reverse transition.
- The modal hosts an interactive React Flow instance. `editable = me.role ===
  "architect"`. Architect: structural editing (add/remove nodes & edges, edit
  label/type/direction). Other roles: same zoom, `editable=false`, read-only.
- Save reuses `api.saveDocument(pocId, {document_html, diagrams}, "architect")`
  (`PocDocument.tsx:68`); diagrams carry no coordinates.

### 4. Node / edge components (frontend)

- `nodeTypes`: one `ArchitectureNode` that switches color token, icon, and
  left/right typed handles by `data.type`. Tailwind for the card (rounded, thin
  border, subtle gradient/shadow, backdrop-blur) — shadcn aesthetic without the
  shadcn dependency.
- `edgeTypes`: a single polished edge style ships in v1 — smoothstep/orthogonal
  routing with a label background mask so labels don't sit on the line. Semantic
  variants (`emphasis / security / async`) are defined as available styles, but
  **auto-assignment of variants is deferred** (no LLM contract change for edges
  in v1); all edges render `default`.
- The inline preview and the modal reuse the same custom node for visual
  consistency.

## Testing

- **Backend** (`backend/tests/test_diagrams.py`): `build_architecture_diagram`
  emits nodes without positions, `type` always within the enum, every edge
  endpoint resolves to an existing node, and unmatched endpoints are surfaced
  rather than silently dropped.
- **Frontend** (`diagramLayout` unit test): a given node/edge set yields stable,
  deterministic coordinates with no overlap; re-layout after a structural change
  remains stable.

## Deferred / future

- IR→SVG renderer for deck embedding + SVG/PNG export. That DOM-free path is
  where pretext (JS text measurement) and a Graphfi-style export pipeline become
  relevant. Out of scope here.
- A `apoc-diagrams` skill — revisit once more than one diagram type exists.
