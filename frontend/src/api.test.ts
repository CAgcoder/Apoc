import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

function mockFetch(json: any = { ok: true }) {
  const spy = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => json,
    text: async () => "",
  });
  (globalThis as any).fetch = spy;
  return spy;
}

afterEach(() => vi.restoreAllMocks());

describe("api ai methods", () => {
  it("setCommentStatus posts status with role header", async () => {
    const spy = mockFetch();
    await api.setCommentStatus("poc1", "cm1", "accepted", "architect");
    const [url, opts] = spy.mock.calls[0];
    expect(url).toContain("/api/pocs/poc1/comments/cm1/status");
    expect(opts.method).toBe("POST");
    expect(JSON.parse(opts.body)).toEqual({ status: "accepted" });
    expect(opts.headers["X-Apoc-Role"]).toBe("architect");
  });

  it("bulkSetCommentStatus posts ids + status", async () => {
    const spy = mockFetch();
    await api.bulkSetCommentStatus("poc1", ["a", "b"], "closed", "architect");
    const [url, opts] = spy.mock.calls[0];
    expect(url).toContain("/api/pocs/poc1/comments/status");
    expect(JSON.parse(opts.body)).toEqual({ ids: ["a", "b"], status: "closed" });
  });

  it("aiEdit posts instruction with role header", async () => {
    const spy = mockFetch({ proposed_md: "x", addressed_comment_ids: [] });
    await api.aiEdit("poc1", { instruction: "be terse" }, "architect");
    const [url, opts] = spy.mock.calls[0];
    expect(url).toContain("/api/pocs/poc1/ai-edit");
    expect(JSON.parse(opts.body)).toEqual({ instruction: "be terse" });
    expect(opts.headers["X-Apoc-Role"]).toBe("architect");
  });

  it("pocChat posts messages without role header", async () => {
    const spy = mockFetch({ reply: "hi" });
    const msgs = [{ role: "user" as const, content: "q" }];
    await api.pocChat("poc1", msgs);
    const [url, opts] = spy.mock.calls[0];
    expect(url).toContain("/api/pocs/poc1/chat");
    expect(JSON.parse(opts.body)).toEqual({ messages: msgs });
    expect(opts.headers["X-Apoc-Role"]).toBeUndefined();
  });
});
