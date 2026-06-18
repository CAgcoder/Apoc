import { describe, expect, it } from "vitest";
import { computeLineDiff } from "./diff";

describe("computeLineDiff", () => {
  it("marks added, removed, and context lines", () => {
    const before = "line a\nline b\nline c";
    const after = "line a\nline B\nline c";
    const rows = computeLineDiff(before, after);
    const removed = rows.filter((r) => r.type === "remove").map((r) => r.text);
    const added = rows.filter((r) => r.type === "add").map((r) => r.text);
    const context = rows.filter((r) => r.type === "context").map((r) => r.text);
    expect(removed).toContain("line b");
    expect(added).toContain("line B");
    expect(context).toContain("line a");
    expect(context).toContain("line c");
  });

  it("returns all-context when identical", () => {
    const rows = computeLineDiff("x\ny", "x\ny");
    expect(rows.every((r) => r.type === "context")).toBe(true);
  });
});
