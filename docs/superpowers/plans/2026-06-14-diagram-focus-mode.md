# Diagram Focus-Mode + Deterministic Auto-Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the messy insertion-order grid diagram with deterministic dagre auto-layout, semantic typed nodes, and a centered focus-modal that the architect can edit (other roles get a read-only zoom).

**Architecture:** The backend stops emitting coordinates — it emits typed nodes (`{id, data:{label, type, subtitle}}`) and edges. The frontend computes positions with dagre (LR) at render time and never persists them. Clicking a diagram zooms it (framer-motion shared-element) into a 60% centered modal; editing is structural only (add/remove nodes & edges, change label/type), gated to the `architect` role via the existing `me.role === "architect"` flag.

**Tech Stack:** Python (backend, hand-rolled test runner), React 19 + TypeScript + Vite, `@xyflow/react` v12, `@dagrejs/dagre` (layout), `framer-motion` (zoom), `vitest` (frontend tests), Tailwind v4 (styling).

---

## Spec

See `apoc/docs/superpowers/specs/2026-06-14-diagram-focus-mode-design.md`.

## File Structure

**Backend**
- `apoc/backend/app/config.py` — add `NODE_TYPES` enum tuple (canonical vocabulary).
- `apoc/backend/app/diagrams.py` — drop grid positions; add typed nodes + `subtitle`; normalize `type`; log unmatched edge endpoints instead of dropping silently.
- `apoc/backend/app/prompts.py` — `DESIGN_SYSTEM`: add `type` to the component schema + list the allowed values.
- `apoc/backend/tests/test_diagrams.py` — update/extend coverage.

**Frontend**
- `apoc/frontend/package.json` — add `@dagrejs/dagre`, `framer-motion` deps; `vitest` dev dep; `test` script.
- `apoc/frontend/src/diagramLayout.ts` — **new**, pure dagre layout function.
- `apoc/frontend/src/diagramLayout.test.ts` — **new**, vitest unit tests.
- `apoc/frontend/src/ArchitectureNode.tsx` — **new**, typed custom node (styling + inline label/type editing).
- `apoc/frontend/src/DiagramCanvas.tsx` — render from unpositioned nodes via layout; register `nodeTypes`; polished edges; structural-only editing.
- `apoc/frontend/src/DiagramFocusModal.tsx` — **new**, centered 60% modal with framer-motion shared-element zoom.
- `apoc/frontend/src/PocDocument.tsx` — inline read-only preview that opens the modal; strip coordinates on save; carry `type`/`subtitle`.

---

## Task 1: Backend — typed nodes, no coordinates, `subtitle`

**Files:**
- Modify: `apoc/backend/app/config.py`
- Modify: `apoc/backend/app/diagrams.py`
- Test: `apoc/backend/tests/test_diagrams.py`

- [ ] **Step 1: Add the canonical node-type vocabulary to config**

In `apoc/backend/app/config.py`, after the `APPROVER_ROLES` block (line 88), append:

```python

# Semantic categories for architecture-diagram nodes. Drives node color/icon in
# the UI. The LLM assigns each component one of these; anything else falls back
# to "backend". Nodes remain 1:1 with the POC document's components.
NODE_TYPES = (
    "frontend",
    "backend",
    "database",
    "cloud",
    "security",
    "messagebus",
    "external",
    "gateway",
)
NODE_TYPE_FALLBACK = "backend"
```

- [ ] **Step 2: Rewrite the failing tests for the new node shape**

Replace `test_components_become_nodes_with_positions_and_detail` in `apoc/backend/tests/test_diagrams.py` (lines 11-25) with:

```python
def test_components_become_typed_nodes_without_positions():
    design = {
        "components": [
            {"name": "Web UI", "responsibility": "serves dashboard", "tech": "React", "type": "frontend"},
            {"name": "Database", "responsibility": "stores data", "tech": "Postgres", "type": "database"},
        ],
        "data_flows": [{"from": "Web UI", "to": "Database", "description": "reads/writes"}],
    }
    diag = build_architecture_diagram(design)
    assert diag["id"] == "architecture"
    assert len(diag["nodes"]) == 2
    n0 = diag["nodes"][0]
    assert n0["id"]
    assert "position" not in n0           # coordinates are computed on the frontend now
    assert n0["data"]["label"] == "Web UI"
    assert n0["data"]["type"] == "frontend"
    assert n0["data"]["subtitle"] == "React"


def test_unknown_or_missing_type_falls_back_to_backend():
    design = {
        "components": [
            {"name": "A", "responsibility": "", "tech": "", "type": "wizardry"},
            {"name": "B", "responsibility": "", "tech": ""},
        ],
        "data_flows": [],
    }
    diag = build_architecture_diagram(design)
    assert diag["nodes"][0]["data"]["type"] == "backend"
    assert diag["nodes"][1]["data"]["type"] == "backend"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd apoc/backend && .venv/bin/python -m tests.test_diagrams`
Expected: FAIL — `test_components_become_typed_nodes_without_positions` (position still present, no `type`/`subtitle` key) and `test_unknown_or_missing_type_falls_back_to_backend` (KeyError/missing `type`).

- [ ] **Step 4: Update `build_architecture_diagram`**

In `apoc/backend/app/diagrams.py`, add the import and a normalizer near the top (after line 10):

```python
from app import config


def _norm_type(value: str) -> str:
    v = (value or "").strip().lower()
    return v if v in config.NODE_TYPES else config.NODE_TYPE_FALLBACK
```

Then replace the node-construction loop body (lines 36-41) with:

```python
        subtitle = (c.get("tech") or "").strip()
        nodes.append({
            "id": nid,
            "data": {
                "label": name,
                "type": _norm_type(c.get("type")),
                "subtitle": subtitle,
            },
        })
```

(Delete the `detail = ...` line and the `position` key entirely. The `_COLS`, `_COL_W`, `_ROW_H` constants on lines 12-14 are now unused — remove them.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd apoc/backend && .venv/bin/python -m tests.test_diagrams`
Expected: PASS — all tests (including the unchanged edge/empty tests) report `passed`.

- [ ] **Step 6: Commit**

```bash
git add apoc/backend/app/config.py apoc/backend/app/diagrams.py apoc/backend/tests/test_diagrams.py
git commit -m "feat(diagrams): typed nodes, drop server-side coordinates"
```

---

## Task 2: Backend — surface unmatched edge endpoints instead of dropping silently

**Files:**
- Modify: `apoc/backend/app/diagrams.py`
- Test: `apoc/backend/tests/test_diagrams.py`

- [ ] **Step 1: Write the failing test**

Append to `apoc/backend/tests/test_diagrams.py` (before the `if __name__` block):

```python
def test_unmatched_edge_endpoint_is_logged_not_silently_dropped():
    import logging

    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    logger = logging.getLogger("app.diagrams")
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    try:
        design = {
            "components": [{"name": "A", "responsibility": "", "tech": "", "type": "backend"}],
            "data_flows": [{"from": "A", "to": "Ghost", "description": "dangling"}],
        }
        diag = build_architecture_diagram(design)
    finally:
        logger.removeHandler(handler)

    assert diag["edges"] == []  # still dropped from the graph...
    assert any("Ghost" in r.getMessage() for r in records)  # ...but surfaced, not silent
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apoc/backend && .venv/bin/python -m tests.test_diagrams`
Expected: FAIL — no log record contains "Ghost" (endpoint is dropped silently).

- [ ] **Step 3: Add logging to the edge loop**

In `apoc/backend/app/diagrams.py`, add at module top (after the existing imports):

```python
import logging

logger = logging.getLogger(__name__)
```

Replace the edge loop (lines 56-66) with:

```python
    edges: list[dict[str, Any]] = []
    for i, f in enumerate(flows):
        raw_src, raw_dst = f.get("from") or "", f.get("to") or ""
        src, dst = resolve(raw_src), resolve(raw_dst)
        if not src or not dst:
            logger.warning(
                "diagram: dropping data_flow with unresolved endpoint(s): from=%r to=%r",
                raw_src, raw_dst,
            )
            continue
        if src == dst:
            continue
        edges.append({
            "id": f"e{i}",
            "source": src,
            "target": dst,
            "label": (f.get("description") or "").strip(),
        })
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apoc/backend && .venv/bin/python -m tests.test_diagrams`
Expected: PASS — all tests report `passed`.

- [ ] **Step 5: Commit**

```bash
git add apoc/backend/app/diagrams.py apoc/backend/tests/test_diagrams.py
git commit -m "fix(diagrams): log unresolved edge endpoints instead of dropping silently"
```

---

## Task 3: Backend — ask the model for a node `type`

**Files:**
- Modify: `apoc/backend/app/prompts.py`

- [ ] **Step 1: Add `type` to the component schema**

In `apoc/backend/app/prompts.py`, change the `components` line in `DESIGN_SYSTEM` (line 135) from:

```python
  "components": [{"name": string, "responsibility": string, "tech": string}],
```

to:

```python
  "components": [{"name": string, "responsibility": string, "tech": string, "type": string}],
```

- [ ] **Step 2: Add the enum instruction**

In the same `DESIGN_SYSTEM` string, immediately after the closing `}` of the JSON shape (after line 144, before the blank line preceding `The "markdown" field...`), insert:

```python

Each component's "type" MUST be exactly one of: frontend, backend, database, \
cloud, security, messagebus, external, gateway. Choose the closest category; it \
only controls the diagram node's color/icon.
```

- [ ] **Step 3: Verify the prompt now lists the enum**

Run: `cd apoc/backend && grep -n "frontend, backend, database" app/prompts.py`
Expected: prints the inserted instruction line.

- [ ] **Step 4: Commit**

```bash
git add apoc/backend/app/prompts.py
git commit -m "feat(prompts): require a semantic type per architecture component"
```

---

## Task 4: Frontend — add dependencies and a test runner

**Files:**
- Modify: `apoc/frontend/package.json`

- [ ] **Step 1: Install runtime + dev dependencies**

Run:

```bash
cd apoc/frontend
npm install @dagrejs/dagre framer-motion
npm install -D vitest
```

Expected: both commands complete; `package.json` now lists `@dagrejs/dagre` and `framer-motion` under `dependencies` and `vitest` under `devDependencies`.

- [ ] **Step 2: Add a test script**

In `apoc/frontend/package.json`, add to the `"scripts"` object:

```json
    "test": "vitest run"
```

- [ ] **Step 3: Verify the test runner is wired**

Run: `cd apoc/frontend && npm test`
Expected: vitest runs and reports `No test files found` (no tests exist yet) — this confirms vitest is installed and the script works.

- [ ] **Step 4: Commit**

```bash
git add apoc/frontend/package.json apoc/frontend/package-lock.json
git commit -m "build(frontend): add dagre, framer-motion, vitest"
```

---

## Task 5: Frontend — deterministic dagre layout function

**Files:**
- Create: `apoc/frontend/src/diagramLayout.ts`
- Test: `apoc/frontend/src/diagramLayout.test.ts`

- [ ] **Step 1: Write the failing test**

Create `apoc/frontend/src/diagramLayout.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import type { Edge, Node } from "@xyflow/react";
import { layoutDiagram } from "./diagramLayout";

const nodes: Node[] = [
  { id: "a", position: { x: 0, y: 0 }, data: { label: "Alpha", type: "frontend" } },
  { id: "b", position: { x: 0, y: 0 }, data: { label: "Beta", type: "backend" } },
  { id: "c", position: { x: 0, y: 0 }, data: { label: "Gamma", type: "database" } },
];
const edges: Edge[] = [
  { id: "e1", source: "a", target: "b" },
  { id: "e2", source: "b", target: "c" },
];

describe("layoutDiagram", () => {
  it("is deterministic for the same input", () => {
    const r1 = layoutDiagram(nodes, edges).map((n) => n.position);
    const r2 = layoutDiagram(nodes, edges).map((n) => n.position);
    expect(r1).toEqual(r2);
  });

  it("places downstream nodes to the right (LR)", () => {
    const out = layoutDiagram(nodes, edges);
    const by = Object.fromEntries(out.map((n) => [n.id, n.position]));
    expect(by.b.x).toBeGreaterThan(by.a.x);
    expect(by.c.x).toBeGreaterThan(by.b.x);
  });

  it("produces non-overlapping nodes", () => {
    const out = layoutDiagram(nodes, edges);
    for (let i = 0; i < out.length; i++) {
      for (let j = i + 1; j < out.length; j++) {
        const dx = Math.abs(out[i].position.x - out[j].position.x);
        const dy = Math.abs(out[i].position.y - out[j].position.y);
        expect(dx > 20 || dy > 20).toBe(true);
      }
    }
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apoc/frontend && npm test`
Expected: FAIL — `Cannot find module './diagramLayout'`.

- [ ] **Step 3: Implement the layout function**

Create `apoc/frontend/src/diagramLayout.ts`:

```ts
import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";

const FALLBACK_W = 180;
const FALLBACK_H = 64;

// Node box size: prefer React Flow's measured size (set after first render),
// otherwise estimate from the label so first paint is already deterministic.
function sizeOf(node: Node): { width: number; height: number } {
  const measured = (node as { measured?: { width?: number; height?: number } }).measured;
  if (measured?.width && measured?.height) {
    return { width: measured.width, height: measured.height };
  }
  const label = String((node.data as { label?: unknown })?.label ?? "");
  const width = Math.min(320, Math.max(FALLBACK_W, 24 + label.length * 8));
  return { width, height: FALLBACK_H };
}

// Pure: given unpositioned nodes + edges, return nodes with dagre LR positions.
export function layoutDiagram(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 40, ranksep: 90, marginx: 16, marginy: 16 });

  for (const n of nodes) {
    const { width, height } = sizeOf(n);
    g.setNode(n.id, { width, height });
  }
  for (const e of edges) {
    if (g.hasNode(e.source) && g.hasNode(e.target)) g.setEdge(e.source, e.target);
  }

  dagre.layout(g);

  return nodes.map((n) => {
    const { x, y, width, height } = g.node(n.id);
    // dagre returns the node center; React Flow positions are top-left.
    return { ...n, position: { x: x - width / 2, y: y - height / 2 } };
  });
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apoc/frontend && npm test`
Expected: PASS — all three `layoutDiagram` tests pass.

- [ ] **Step 5: Commit**

```bash
git add apoc/frontend/src/diagramLayout.ts apoc/frontend/src/diagramLayout.test.ts
git commit -m "feat(frontend): deterministic dagre LR layout for diagrams"
```

---

## Task 6: Frontend — typed custom node

**Files:**
- Create: `apoc/frontend/src/ArchitectureNode.tsx`

- [ ] **Step 1: Implement the typed node**

Create `apoc/frontend/src/ArchitectureNode.tsx`:

```tsx
import { Handle, Position, type NodeProps } from "@xyflow/react";

export const NODE_TYPES = [
  "frontend", "backend", "database", "cloud",
  "security", "messagebus", "external", "gateway",
] as const;
export type NodeKind = (typeof NODE_TYPES)[number];

// Per-type accent: [border, soft background, icon].
const STYLE: Record<NodeKind, { ring: string; bg: string; icon: string }> = {
  frontend:   { ring: "border-sky-400/60",     bg: "from-sky-500/15",     icon: "🖥️" },
  backend:    { ring: "border-violet-400/60",  bg: "from-violet-500/15",  icon: "⚙️" },
  database:   { ring: "border-emerald-400/60", bg: "from-emerald-500/15", icon: "🗄️" },
  cloud:      { ring: "border-cyan-400/60",    bg: "from-cyan-500/15",    icon: "☁️" },
  security:   { ring: "border-rose-400/60",    bg: "from-rose-500/15",    icon: "🛡️" },
  messagebus: { ring: "border-amber-400/60",   bg: "from-amber-500/15",   icon: "📨" },
  external:   { ring: "border-slate-400/60",   bg: "from-slate-500/15",   icon: "🌐" },
  gateway:    { ring: "border-indigo-400/60",  bg: "from-indigo-500/15",  icon: "🚪" },
};

export interface ArchitectureNodeData {
  label: string;
  type: NodeKind;
  subtitle?: string;
  editable?: boolean;
  onPatch?: (patch: { label?: string; type?: NodeKind }) => void;
  onDelete?: () => void;
  [key: string]: unknown;
}

export function ArchitectureNode({ data }: NodeProps) {
  const d = data as ArchitectureNodeData;
  const kind: NodeKind = (NODE_TYPES as readonly string[]).includes(d.type) ? d.type : "backend";
  const s = STYLE[kind];

  return (
    <div
      className={`group relative min-w-[160px] max-w-[300px] rounded-xl border ${s.ring} bg-gradient-to-br ${s.bg} to-transparent bg-[#11131b]/90 px-3 py-2 shadow-lg shadow-black/30 backdrop-blur`}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-white/40" />
      {d.editable ? (
        <button
          onClick={d.onDelete}
          className="absolute -right-2 -top-2 hidden h-4 w-4 items-center justify-center rounded-full bg-rose-500 text-[10px] text-white group-hover:flex"
          aria-label="Delete node"
        >
          ✕
        </button>
      ) : null}
      <div className="flex items-center gap-2">
        <span className="text-sm">{s.icon}</span>
        {d.editable ? (
          <input
            className="w-full bg-transparent text-sm font-medium text-white outline-none"
            value={d.label}
            onChange={(e) => d.onPatch?.({ label: e.target.value })}
          />
        ) : (
          <span className="text-sm font-medium text-white">{d.label}</span>
        )}
      </div>
      {d.subtitle ? <div className="mt-0.5 text-[11px] text-white/55">{d.subtitle}</div> : null}
      {d.editable ? (
        <select
          className="mt-1 w-full rounded bg-black/30 px-1 py-0.5 text-[11px] text-white/80 outline-none"
          value={kind}
          onChange={(e) => d.onPatch?.({ type: e.target.value as NodeKind })}
        >
          {NODE_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      ) : null}
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-white/40" />
    </div>
  );
}
```

- [ ] **Step 2: Verify it typechecks**

Run: `cd apoc/frontend && npx tsc --noEmit`
Expected: no errors referencing `ArchitectureNode.tsx`.

- [ ] **Step 3: Commit**

```bash
git add apoc/frontend/src/ArchitectureNode.tsx
git commit -m "feat(frontend): semantic typed ArchitectureNode"
```

---

## Task 7: Frontend — render DiagramCanvas from unpositioned nodes (structural editing)

**Files:**
- Modify: `apoc/frontend/src/DiagramCanvas.tsx`

This rewrites `DiagramCanvas` so positions come from `layoutDiagram`, dragging is off, and editing is structural (add/remove nodes & edges, patch label/type). The `onChange` callback emits nodes **without** positions.

- [ ] **Step 1: Replace `DiagramCanvas.tsx`**

Replace the entire contents of `apoc/frontend/src/DiagramCanvas.tsx` with:

```tsx
import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  type Edge,
  type Node,
  type Connection,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { layoutDiagram } from "./diagramLayout";
import { ArchitectureNode, type NodeKind } from "./ArchitectureNode";

export interface Diagram {
  id: string;
  title: string;
  nodes: Node[]; // stored WITHOUT positions; positions are derived here
  edges: Edge[];
}

const nodeTypes = { architecture: ArchitectureNode };
const defaultEdgeOptions = {
  type: "smoothstep" as const,
  labelBgPadding: [6, 3] as [number, number],
  labelBgBorderRadius: 4,
  labelBgStyle: { fill: "#0c0e16", fillOpacity: 0.9 },
  labelStyle: { fill: "#cbd5e1", fontSize: 11 },
  style: { stroke: "#475569" },
};

function Canvas({
  diagram,
  editable,
  onChange,
}: {
  diagram: Diagram;
  editable: boolean;
  onChange: (nodes: Node[], edges: Edge[]) => void;
}) {
  const { nodes, edges } = diagram;

  const patchNode = useCallback(
    (id: string, patch: { label?: string; type?: NodeKind }) =>
      onChange(
        nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n)),
        edges,
      ),
    [nodes, edges, onChange],
  );
  const deleteNode = useCallback(
    (id: string) =>
      onChange(
        nodes.filter((n) => n.id !== id),
        edges.filter((e) => e.source !== id && e.target !== id),
      ),
    [nodes, edges, onChange],
  );
  const deleteEdge = useCallback(
    (id: string) => onChange(nodes, edges.filter((e) => e.id !== id)),
    [nodes, edges, onChange],
  );

  // Derive positioned nodes via dagre; inject the editable affordances. We never
  // use React Flow's internal change pipeline (no dragging, no selection-based
  // delete), so nodes are re-derived deterministically on every render.
  const rfNodes = useMemo(() => {
    const withType = nodes.map((n) => ({
      ...n,
      type: "architecture",
      data: {
        ...n.data,
        editable,
        onPatch: (p: { label?: string; type?: NodeKind }) => patchNode(n.id, p),
        onDelete: () => deleteNode(n.id),
      },
    }));
    return layoutDiagram(withType, edges);
  }, [nodes, edges, editable, patchNode, deleteNode]);

  const onConnect = useCallback(
    (c: Connection) =>
      onChange(nodes, [
        ...edges,
        { id: `e${Date.now()}`, source: c.source!, target: c.target!, label: "" },
      ]),
    [nodes, edges, onChange],
  );

  const addNode = () => {
    const id = `n${Date.now()}`;
    onChange(
      [...nodes, { id, position: { x: 0, y: 0 }, data: { label: "New node", type: "backend", subtitle: "" } }],
      edges,
    );
  };

  const noop = useCallback(() => {}, []);

  return (
    <div className="relative h-full w-full overflow-hidden rounded-lg border border-white/10 bg-[#0c0e16]">
      {editable && (
        <div className="absolute left-2 top-2 z-10 flex gap-2">
          <button
            onClick={addNode}
            className="rounded-md bg-blue-500 px-2.5 py-1 text-xs font-medium text-white hover:bg-blue-400"
          >
            + node
          </button>
          <span className="rounded-md bg-black/40 px-2 py-1 text-[11px] text-white/60">
            edit label/type inline · hover a node and click ✕ to remove · drag handles to connect · click an edge to delete · layout is automatic
          </span>
        </div>
      )}
      <ReactFlow
        nodes={rfNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        defaultEdgeOptions={defaultEdgeOptions}
        onNodesChange={noop}
        onEdgesChange={noop}
        onConnect={onConnect}
        onEdgeClick={(_, edge) => editable && deleteEdge(edge.id)}
        nodesDraggable={false}
        nodesConnectable={editable}
        elementsSelectable={editable}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#2a2f3e" gap={18} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

export function DiagramCanvas(props: {
  diagram: Diagram;
  editable: boolean;
  onChange: (nodes: Node[], edges: Edge[]) => void;
}) {
  return (
    <ReactFlowProvider>
      <Canvas {...props} />
    </ReactFlowProvider>
  );
}
```

Note: the height changed from a fixed `h-[380px]` to `h-full` so the same canvas fills both the small inline preview and the large modal. The inline wrapper (Task 8) sets the small height.

- [ ] **Step 2: Verify it typechecks**

Run: `cd apoc/frontend && npx tsc --noEmit`
Expected: no errors in `DiagramCanvas.tsx`. (`PocDocument.tsx` may still error until Task 8 — that is expected and addressed next.)

- [ ] **Step 3: Commit**

```bash
git add apoc/frontend/src/DiagramCanvas.tsx
git commit -m "feat(frontend): auto-layout canvas with typed nodes, structural editing"
```

---

## Task 8: Frontend — focus modal, inline preview, coordinate-free persistence

**Files:**
- Create: `apoc/frontend/src/DiagramFocusModal.tsx`
- Modify: `apoc/frontend/src/PocDocument.tsx`

- [ ] **Step 1: Create the focus modal**

Create `apoc/frontend/src/DiagramFocusModal.tsx`:

```tsx
import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Node, Edge } from "@xyflow/react";
import { DiagramCanvas, type Diagram } from "./DiagramCanvas";

// Centered ~60% modal. Editable only when `canEdit` (architect); other roles get
// the same zoom, read-only. Shares a framer-motion layoutId with the inline
// preview so it appears to zoom out of its thumbnail.
export function DiagramFocusModal({
  diagram,
  canEdit,
  onChange,
  onClose,
}: {
  diagram: Diagram | null;
  canEdit: boolean;
  onChange: (nodes: Node[], edges: Edge[]) => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <AnimatePresence>
      {diagram && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            layoutId={`diag-${diagram.id}`}
            className="flex h-[60vh] w-[60vw] flex-col overflow-hidden rounded-2xl border border-white/15 bg-[#0c0e16] shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-2">
              <span className="text-sm font-medium text-white/80">{diagram.title}</span>
              <button onClick={onClose} className="text-white/50 hover:text-white" aria-label="Close">✕</button>
            </div>
            <div className="min-h-0 flex-1">
              <DiagramCanvas diagram={diagram} editable={canEdit} onChange={onChange} />
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
```

- [ ] **Step 2: Update `normalize` and `cleanDiagrams` in PocDocument**

In `apoc/frontend/src/PocDocument.tsx`, replace `normalize` (lines 7-14) with a version that drops positions and carries `type`/`subtitle`:

```tsx
function normalize(diagrams: any[]): Diagram[] {
  return (diagrams || []).map((d) => ({
    id: d.id,
    title: d.title || "Diagram",
    nodes: (d.nodes || []).map((n: any) => ({
      id: n.id,
      position: { x: 0, y: 0 }, // placeholder; real positions come from layoutDiagram
      data: {
        label: n.data?.label ?? "",
        type: n.data?.type ?? "backend",
        subtitle: n.data?.subtitle ?? "",
      },
    })) as Node[],
    edges: (d.edges || []) as Edge[],
  }));
}
```

Then replace the `cleanDiagrams` block (lines 52-66) so persisted nodes omit coordinates and keep `type`/`subtitle`:

```tsx
    const cleanDiagrams = diags.map((d) => ({
      id: d.id,
      title: d.title,
      nodes: d.nodes.map((n) => ({
        id: n.id,
        data: {
          label: (n.data as any)?.label ?? "",
          type: (n.data as any)?.type ?? "backend",
          subtitle: (n.data as any)?.subtitle ?? "",
        },
      })),
      edges: d.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: (e as any).label ?? "",
      })),
    }));
```

- [ ] **Step 3: Render inline preview + modal**

In `apoc/frontend/src/PocDocument.tsx`, add the import at the top (after line 5):

```tsx
import { DiagramFocusModal } from "./DiagramFocusModal";
import { motion } from "framer-motion";
```

Add focus state inside the component (after line 35, the `diags` state):

```tsx
  const [focusedId, setFocusedId] = useState<string | null>(null);
```

Replace the diagram branch of the `parts.map` (lines 111-127, the `p.type === "diagram" ? (...)` figure) with a clickable read-only preview:

```tsx
        p.type === "diagram" ? (
          <figure key={i} className="my-4">
            <figcaption className="mb-1 text-sm font-medium text-white/70">
              {diagById(p.id)?.title ?? "Diagram"}
            </figcaption>
            {diagById(p.id) ? (
              <motion.div
                layoutId={`diag-${p.id}`}
                onClick={() => setFocusedId(p.id)}
                className="h-[320px] cursor-zoom-in"
                title="Click to expand"
              >
                <DiagramCanvas diagram={diagById(p.id)!} editable={false} onChange={() => {}} />
              </motion.div>
            ) : (
              <div className="rounded-lg border border-dashed border-white/15 p-4 text-sm text-white/40">
                (diagram “{p.id}” not found)
              </div>
            )}
          </figure>
        ) : (
```

Finally, render the modal just before the closing `</div>` of the component's returned tree (after the `parts.map(...)` block, before line 141's `</div>`):

```tsx
      <DiagramFocusModal
        diagram={focusedId ? diagById(focusedId) ?? null : null}
        canEdit={canEdit}
        onChange={(n, e) => focusedId && updateDiag(focusedId, n, e)}
        onClose={() => setFocusedId(null)}
      />
```

Note: editing now happens in the modal (architect only), so the inline `editable={editing}` is gone. The old `Edit/Save/Cancel` document toolbar still governs text editing and saving; the diagram edits live in `diags` state and are written by the same `save()`.

- [ ] **Step 4: Verify the whole frontend typechecks and builds**

Run: `cd apoc/frontend && npx tsc --noEmit && npm run build`
Expected: no type errors; build succeeds.

- [ ] **Step 5: Run the app and verify the interaction**

Run the app (backend + frontend) per the project's run instructions. As the **architect**, open a POC document, click the architecture diagram, and confirm:
- it zooms into a centered ~60% modal with the review dimmed behind;
- nodes are cleanly laid out left-to-right, colored by type, no tangled edges;
- inline label/type editing, add `+ node`, connect handles, node ✕ delete, and click-edge-to-delete all work;
- Esc / backdrop click closes with a reverse zoom;
- switch identity to a non-architect role → clicking still zooms, but no editing affordances appear;
- click **Save** in the document toolbar, reload, and confirm edits persist and the layout is still clean (no stored coordinates).

- [ ] **Step 6: Commit**

```bash
git add apoc/frontend/src/DiagramFocusModal.tsx apoc/frontend/src/PocDocument.tsx
git commit -m "feat(frontend): click-to-zoom focus modal, architect-only diagram editing"
```

---

## Self-Review Notes

- **Spec coverage:** focus modal 60% + dim (Task 8) · architect-only edit via existing gate (Task 8, `canEdit`) · LLM emits type, no positions (Tasks 1, 3) · structural-only editing, coordinates never persisted (Tasks 1, 7, 8) · frontend dagre LR with measured/estimated sizes (Task 5) · 8-value enum + fallback (Tasks 1, 6) · existing `<Controls>` reused, no direction toggle (Task 7) · Tailwind without shadcn (Task 6) · framer-motion only for zoom (Tasks 4, 8) · `resolve()` silent-drop fixed (Task 2) · backend + frontend tests (Tasks 1, 2, 5).
- **Deferred (per spec):** IR→SVG export, pretext, diagram authoring skill — intentionally not in this plan.
- **Type consistency:** `data.type` / `data.subtitle` / `data.label` used identically across `diagrams.py`, `ArchitectureNode`, `DiagramCanvas`, `PocDocument`; `layoutDiagram(nodes, edges)` signature matches all call sites; `NODE_TYPES` enum identical in `config.py` and `ArchitectureNode.tsx`.
