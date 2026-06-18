# Deck: deterministic diagrams + enforced preset fidelity

Date: 2026-06-16
Branch: `apoc`

## Problem

The editable slide deck is produced by a single automated LLM call
(`prompts.DECK_SYSTEM`, run in both `app/generation.py` and `app/graph/nodes.py`).
The skill `frontend-slides-editable` cannot run its interactive Phase 1–5
discovery here, so its quality bar is not enforced. Two concrete failures show up
on the architecture-overview and data-flow slides:

1. **Broken diagrams.** The LLM hand-authors `.diagram` / `.diagram-row` /
   `.diagram-box` / `.connector` markup. Connectors float, columns don't align,
   and boxes are left unwired — the graph is not faithfully represented.
2. **Generic "AI slop" aesthetic.** No committed preset (cream background + red
   boxes), violating the skill's distinctive-design mandate.

The design step already emits structured `components` and `data_flows`, and
`diagrams.build_architecture_diagram` already turns them into a wired node/edge
graph (with orphan auto-anchoring) for the document's React Flow diagram. The
deck should reuse that data instead of re-deriving the diagram in prose.

## Goals

- Architecture and data-flow **diagram slides are built deterministically** from
  the structured design — every box correctly wired, nothing floating.
- The deck **commits to one distinctive preset** (no AI slop) while staying
  **fully offline** (no external assets/fonts/CDNs), so `Export HTML` remains a
  self-contained file.
- The deterministic diagrams **pick up the LLM's chosen theme** (accent, surface)
  yet look intentional even if the theme ignores the diagram variables.

## Non-goals

- Running the skill's interactive discovery (Phase 1–5) in the automated pipeline.
- Web fonts / external assets in the deck (explicitly kept offline — decided).
- Changing the document's React Flow diagram or the `build_architecture_diagram`
  output shape.

## Design

### 1. Deterministic diagram builder — `app/deck_diagram.py`

New module. Single public function:

```python
def build_deck_diagram_slides(design: dict) -> dict[str, str]:
    """Return {"architecture": <section-html>, "dataflow": <section-html>}."""
```

It reuses the **same node/edge graph** the React Flow diagram uses. To guarantee
the deck and document never disagree on wiring, factor the graph construction in
`diagrams.build_architecture_diagram` into a shared helper
(`diagrams.build_architecture_graph(design) -> {"nodes", "edges"}`) that both
callers use. `build_architecture_diagram` keeps its current return shape by
wrapping that helper; the orphan auto-anchoring logic moves into the helper so the
deck benefits from it too.

**Architecture slide (tiered layout).** Assign each node a tier by component
`type`:

| Tier | Types |
|------|-------|
| 0 | `frontend` |
| 1 | `gateway` |
| 2 | `backend` |
| 3 | `messagebus` |
| 4 | `database` |
| 5 (support) | `cloud`, `security`, `external` |

- Each populated tier renders as one `.diagram-row` of `.diagram-box`es.
- Empty tiers are skipped; adjacent populated tiers are joined by a single
  `<div class="connector">↓</div>`.
- Within a tier, where the graph has an edge between two same-tier boxes, place a
  `<div class="connector">→</div>` between them.
- Each `.diagram-box` is a clickable `<details>`:
  - `<summary>`: component name + `type`-derived label.
  - body: responsibility + tech, then a short **"flows"** list built from the
    node's real inbound/outbound edges (`from → this`, `this → to`, with the edge
    description). This captures precise wiring that flexbox can't draw as arrows.
- Each box carries `data-type="<type>"` so the theme can accent it.
- Orphan boxes are already anchored by the shared helper, so no box is unwired.

**Data-flow slide (chain layout).** Build an ordered, de-duplicated sequence of
boxes by walking `data_flows` in order (first appearance wins). Join consecutive
boxes with `→` connectors. Each box's `<details>` lists the flow step
descriptions it participates in. If `data_flows` is empty, fall back to the same
tiered architecture rendering so the slide is never blank.

Both slides are returned as a full
`<section class="slide" ...><div class="slide-content"> … </div></section>` with a
heading, so they pass `_normalize_slides` untouched.

Density: cap visible boxes per tier/row to keep the viewport fit (e.g. ≤ 6 per
row, wrap or summarize overflow into a "+N more" box). Tiers themselves are
capped by the 8-type enum.

### 2. Marker-based splice

`DECK_SYSTEM` no longer hand-authors the diagrams. It is instructed to emit two
**placeholder** slides where it wants them in the narrative:

```html
<section class="slide" data-apoc-diagram="architecture"></section>
<section class="slide" data-apoc-diagram="dataflow"></section>
```

A new `_splice_diagram_slides(slides, design)` step (shared by both generation
paths) replaces each placeholder `<section … data-apoc-diagram="X">…</section>`
with the deterministic slide for `X`.

- **Fallback:** if a marker is absent, insert that diagram slide after index 1
  (i.e. after the title + context slides) so it always appears.
- Runs **before** `_normalize_slides`.
- De-duplicates: at most one architecture and one data-flow slide in the output.

### 3. Enforced preset fidelity + diagram theming

**`DECK_SYSTEM` rewrite:**

- Remove the long hand-authored-diagram instructions (now deterministic). Replace
  with: "Do NOT author the architecture or data-flow diagrams. Emit exactly two
  placeholder slides `data-apoc-diagram="architecture"` and `…="dataflow"`; the
  runtime fills them. Style them only via the theme variables below."
- **Force one committed preset:** pick ONE distinctive aesthetic suited to an
  enterprise architecture review and commit fully — atmospheric layered/gradient
  background (not a flat fill), a single sharp accent, varied per-slide layouts
  (no repeated title-slide prototype), staggered CSS load animation,
  `prefers-reduced-motion` respected. Name the chosen preset in a leading CSS
  comment.
- **Offline constraint kept:** no external assets/fonts/CDNs/images; commit to a
  distinctive web-safe/system font stack (e.g. a strong serif display + grotesque
  body) rather than Inter/Arial/Roboto defaults.
- **Require diagram theme variables:** the `theme_css` MUST define, in `:root`:
  `--diagram-box-bg`, `--diagram-box-border`, `--diagram-box-ink`,
  `--diagram-accent`, `--diagram-connector`. These style the deterministic
  diagrams to match the preset.

**`PRESENTER_CSS` (in `deck.py`):** add diagram **appearance** rules that consume
those variables with sensible fallbacks, layered after the theme so the theme
wins when it defines them but the diagram still looks intentional when it doesn't:

```css
.slide .diagram-box {
  background: var(--diagram-box-bg, #161922);
  border: 1px solid var(--diagram-box-border, #2b3142);
  color: var(--diagram-box-ink, #e9e9ef);
  border-radius: 12px; padding: clamp(.6rem,1.2vw,1rem);
}
.slide .diagram-box[data-type="database"] { border-left: 3px solid var(--diagram-accent, #4f7cff); }
/* … per-type accent variants … */
.slide .connector { color: var(--diagram-connector, var(--diagram-accent, #4f7cff)); font-weight: 700; }
```

(Existing `.diagram*` **layout** rules are unchanged.)

## Affected files

- `app/diagrams.py` — extract `build_architecture_graph` shared helper.
- `app/deck_diagram.py` — **new** deterministic diagram-slide builder.
- `app/deck.py` — diagram appearance CSS in `PRESENTER_CSS`.
- `app/prompts.py` — rewrite `DECK_SYSTEM` (markers + preset fidelity + theme vars).
- `app/generation.py` — call `_splice_diagram_slides(slides, design)` before
  `_normalize_slides`.
- `app/graph/nodes.py` — same splice, using `state["canonical"]`. The splice
  helper should live in one place and be imported by both (e.g. in
  `deck_diagram.py`).
- Tests: `tests/test_deck_diagram.py` (new) + additions to `tests/test_deck.py`.

## Testing

- **Diagram builder:** tiering order; same-tier `→` and cross-tier `↓`
  connectors; every node appears exactly once; orphan node is anchored (no box
  without a connector); drill-down lists the node's real edges; empty
  `data_flows` falls back to tiered render; row density cap.
- **Splice:** placeholder replaced in place; missing marker → inserted after
  index 1; never more than one of each diagram slide; output still wrapped
  correctly by `_normalize_slides`.
- **Prompt:** `DECK_SYSTEM` contains the marker contract and the required theme
  variable names (guards against silent drift).
- Existing `test_deck.py` normalization/assembly tests keep passing.

## Risks / trade-offs

- Flexbox diagrams can't draw arbitrary crossing edges; precise wiring lives in
  drill-downs. Accepted — far better than the floating-arrow mess, and honest.
- Marker reliance on the LLM is mitigated by the fixed-index fallback.
- Tier-by-type is a heuristic; a component mis-typed by the design step lands in
  the wrong tier. Acceptable and already constrained by the 8-type enum used
  elsewhere.
