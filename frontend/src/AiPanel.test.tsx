import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AiPanel } from "./AiPanel";
import { api, type PocBundle, type Stakeholder } from "./api";

const architect: Stakeholder = { id: "s1", name: "Ada", role: "architect", org: "O" };
const observer: Stakeholder = { id: "s2", name: "Obs", role: "client_sponsor", org: "O" };

function bundle(comments: any[] = []): PocBundle {
  return {
    project: { id: "p1", title: "T", client_name: "", consulting_org: "", status: "", created_at: "" },
    poc: { id: "poc1", title: "T", version: 1, markdown: "", document_md: "## Risks\nold", design: {} },
    annotations: [],
    reviews: [],
    comments,
    approvals: [],
    approval_rollup: { needed: 0, approved: 0, ready: false, approved_roles: [] },
    stakeholders: [architect],
    research: [],
  };
}

afterEach(() => vi.restoreAllMocks());

describe("AiPanel", () => {
  it("opens to the Ask tab for all roles; Apply hidden from non-architect", () => {
    render(<AiPanel bundle={bundle()} me={observer} reload={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /ask ai/i }));
    expect(screen.getByRole("button", { name: /^ask$/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^apply$/i })).toBeNull();
  });

  it("Ask: submitting calls pocChat and appends the reply", async () => {
    vi.spyOn(api, "pocChat").mockResolvedValue({ reply: "the answer" });
    render(<AiPanel bundle={bundle()} me={observer} reload={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /ask ai/i }));
    fireEvent.change(screen.getByPlaceholderText(/ask about this poc/i), {
      target: { value: "why this framework?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(api.pocChat).toHaveBeenCalled());
    expect(screen.getByText("the answer")).toBeTruthy();
  });

  it("Apply: disabled with hint when no accepted comments", () => {
    render(<AiPanel bundle={bundle()} me={architect} reload={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /ask ai/i }));
    fireEvent.click(screen.getByRole("button", { name: /^apply$/i }));
    expect(screen.getByText(/accept some comments/i)).toBeTruthy();
    expect((screen.getByRole("button", { name: /let ai apply/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("Apply: runs edit, shows diff, Accept saves + bulk-closes", async () => {
    const accepted = [{
      id: "cm1", annotation_id: null, stakeholder_id: "s1", body: "fix auth",
      anchor_line: 1, anchor_slug: "risks", status: "accepted" as const, created_at: "",
    }];
    vi.spyOn(api, "aiEdit").mockResolvedValue({ proposed_md: "## Risks\nnew", addressed_comment_ids: ["cm1"] });
    const save = vi.spyOn(api, "saveDocument").mockResolvedValue({ ok: true });
    const bulk = vi.spyOn(api, "bulkSetCommentStatus").mockResolvedValue({ ok: true });
    const reload = vi.fn();

    render(<AiPanel bundle={bundle(accepted)} me={architect} reload={reload} />);
    fireEvent.click(screen.getByRole("button", { name: /ask ai/i }));
    fireEvent.click(screen.getByRole("button", { name: /^apply$/i }));
    fireEvent.click(screen.getByRole("button", { name: /let ai apply/i }));

    await waitFor(() => expect(screen.getByText("new")).toBeTruthy()); // diff added line
    fireEvent.click(screen.getByRole("button", { name: /^accept$/i }));

    await waitFor(() => expect(save).toHaveBeenCalledWith("poc1", { document_md: "## Risks\nnew" }, "architect"));
    expect(bulk).toHaveBeenCalledWith("poc1", ["cm1"], "closed", "architect");
    expect(reload).toHaveBeenCalled();
  });
});
