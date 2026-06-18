import { describe, expect, it } from "vitest";
import { buildCitationIndex, tokenizeDigest, type CiteSource } from "./trace";

const sources: CiteSource[] = [
  { source_id: "s1", title: "EBA guidance", url: "https://a" },
  { source_id: "s2", title: "GoBD immutability", url: "https://b" },
  { source_id: "", title: "No id source", url: "https://c" },
];

describe("buildCitationIndex", () => {
  it("maps both source_id and 1-based position to the same numbered anchor", () => {
    const idx = buildCitationIndex(sources);
    expect(idx.get("s1")).toEqual({ num: 1, anchorId: "s1" });
    expect(idx.get("1")).toEqual({ num: 1, anchorId: "s1" });
    expect(idx.get("s2")).toEqual({ num: 2, anchorId: "s2" });
    // A source with no id falls back to a positional anchor.
    expect(idx.get("3")).toEqual({ num: 3, anchorId: "n3" });
  });
});

describe("tokenizeDigest", () => {
  it("resolves [s1] and [2] markers into numbered chips", () => {
    const parts = tokenizeDigest("Per [s1] and also [2], data residency holds.", sources);
    const cites = parts.filter((p) => p.type === "cite");
    expect(cites).toEqual([
      { type: "cite", num: 1, anchorId: "s1", token: "s1" },
      { type: "cite", num: 2, anchorId: "s2", token: "2" },
    ]);
    // Reassembling text + chip tokens reproduces the original digest.
    const rebuilt = parts
      .map((p) => (p.type === "text" ? p.value : `[${p.token}]`))
      .join("");
    expect(rebuilt).toBe("Per [s1] and also [2], data residency holds.");
  });

  it("leaves unknown brackets (years, acronyms) as literal text", () => {
    const parts = tokenizeDigest("By [2026] the [GoBD] rule applies, see [s2].", sources);
    expect(parts.filter((p) => p.type === "cite")).toEqual([
      { type: "cite", num: 2, anchorId: "s2", token: "s2" },
    ]);
    expect(parts.find((p) => p.type === "text" && p.value.includes("[2026]"))).toBeTruthy();
    expect(parts.find((p) => p.type === "text" && p.value.includes("[GoBD]"))).toBeTruthy();
  });

  it("is case-insensitive on the source id", () => {
    const parts = tokenizeDigest("Ref [S1].", sources);
    expect(parts.filter((p) => p.type === "cite")).toEqual([
      { type: "cite", num: 1, anchorId: "s1", token: "S1" },
    ]);
  });

  it("returns a single text part when there are no citations", () => {
    expect(tokenizeDigest("plain prose", sources)).toEqual([{ type: "text", value: "plain prose" }]);
  });
});
