import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DiffView } from "./DiffView";

describe("DiffView", () => {
  it("renders added and removed lines with gutters", () => {
    const html = renderToStaticMarkup(
      <DiffView before={"line a\nline b\nline c"} after={"line a\nline B\nline c"} />,
    );
    expect(html).toContain("diff-add");
    expect(html).toContain("diff-remove");
    expect(html).toContain("line B");
    expect(html).toContain("line b");
    expect(html).toContain("line a"); // context
  });
});
