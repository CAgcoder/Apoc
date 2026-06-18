import { describe, expect, it } from "vitest";
import { groupByAnchor, layoutTops, type AnnoGroup } from "./AnnotationMargin";
import type { Annotation } from "./api";

const anno = (id: string, anchor: string, domain: string, severity: string): Annotation => ({
  id,
  poc_id: "p",
  anchor,
  domain,
  severity,
  title: id,
  body: "",
  suggestion: "",
  created_at: "",
});

describe("groupByAnchor", () => {
  it("merges multiple findings at one section and computes worst severity", () => {
    const groups = groupByAnchor([
      anno("a", "Cost outlook", "cost", "warn"),
      anno("b", "Cost outlook", "compliance", "block"),
      anno("c", "Risks", "security", "info"),
    ]);
    const cost = groups.find((group) => group.slug === "cost-outlook")!;
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
      { slug: "b", desiredTop: 40, height: 80 },
      { slug: "c", desiredTop: 400, height: 80 },
    ] as unknown as (AnnoGroup & { desiredTop: number; height: number })[];
    const tops = layoutTops(groups, 12);
    expect(tops[0]).toBe(0);
    expect(tops[1]).toBe(92);
    expect(tops[2]).toBe(400);
  });
});
