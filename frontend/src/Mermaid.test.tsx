import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("beautiful-mermaid", () => ({
  renderMermaidSVG: () => {
    throw new Error("bad diagram");
  },
}));

import { Mermaid } from "./Mermaid";

describe("Mermaid", () => {
  it("falls back to raw code when rendering fails", () => {
    const html = renderToStaticMarkup(<Mermaid code="flowchart LR\nA-->B" />);

    expect(html).toContain("diagram failed to render");
    expect(html).toContain("flowchart LR");
  });
});
