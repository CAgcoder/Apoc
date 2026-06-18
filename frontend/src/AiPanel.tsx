import { useState } from "react";
import { api, type ChatMessage, type PocBundle, type Stakeholder } from "./api";
import { DiffView } from "./DiffView";

type Tab = "ask" | "apply";

interface Proposal {
  proposed_md: string;
  addressed: string[];
  closeIds: Set<string>;
}

export function AiPanel({
  bundle,
  me,
  reload,
}: {
  bundle: PocBundle;
  me: Stakeholder;
  reload: () => void;
}) {
  const [open, setOpen] = useState(false);
  const isArchitect = me.role === "architect";
  const [tab, setTab] = useState<Tab>("ask");

  // Ask state
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [asking, setAsking] = useState(false);

  // Apply state
  const [note, setNote] = useState("");
  const [applying, setApplying] = useState(false);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pocId = bundle.poc!.id;
  const accepted = bundle.comments.filter((c) => c.status === "accepted");
  const stakeholderName = (id: string) =>
    bundle.stakeholders.find((s) => s.id === id)?.name ?? "Someone";

  const send = async () => {
    const text = input.trim();
    if (!text || asking) return;
    const next = [...chat, { role: "user" as const, content: text }];
    setChat(next);
    setInput("");
    setAsking(true);
    try {
      const { reply } = await api.pocChat(pocId, next);
      setChat([...next, { role: "assistant", content: reply }]);
    } catch (e: any) {
      setChat([...next, { role: "assistant", content: `Error: ${e?.message || "chat failed"}` }]);
    } finally {
      setAsking(false);
    }
  };

  const runEdit = async () => {
    setApplying(true);
    setError(null);
    try {
      const res = await api.aiEdit(pocId, { instruction: note.trim() }, me.role);
      setProposal({
        proposed_md: res.proposed_md,
        addressed: res.addressed_comment_ids,
        closeIds: new Set(res.addressed_comment_ids),
      });
    } catch (e: any) {
      setError(e?.message || "AI edit failed");
    } finally {
      setApplying(false);
    }
  };

  const acceptProposal = async () => {
    if (!proposal) return;
    setApplying(true);
    setError(null);
    try {
      await api.saveDocument(pocId, { document_md: proposal.proposed_md }, me.role);
      const ids = [...proposal.closeIds];
      if (ids.length) await api.bulkSetCommentStatus(pocId, ids, "closed", me.role);
      setProposal(null);
      setNote("");
      reload();
      setOpen(false);
    } catch (e: any) {
      setError(e?.message || "Save failed");
    } finally {
      setApplying(false);
    }
  };

  const toggleClose = (id: string) => {
    if (!proposal) return;
    const closeIds = new Set(proposal.closeIds);
    closeIds.has(id) ? closeIds.delete(id) : closeIds.add(id);
    setProposal({ ...proposal, closeIds });
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-40 rounded-full bg-blue-500 px-4 py-3 text-sm font-medium text-white shadow-lg hover:bg-blue-400"
      >
        Ask AI
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-40 flex h-[34rem] w-[26rem] flex-col rounded-xl border border-white/15 bg-[#0d1117] shadow-2xl">
      <div className="flex items-center gap-1 border-b border-white/10 px-3 py-2">
        <button
          type="button"
          onClick={() => setTab("ask")}
          className={`rounded px-2 py-1 text-sm ${tab === "ask" ? "bg-white/10 text-white" : "text-white/50"}`}
        >
          Ask
        </button>
        {isArchitect && (
          <button
            type="button"
            onClick={() => setTab("apply")}
            className={`rounded px-2 py-1 text-sm ${tab === "apply" ? "bg-white/10 text-white" : "text-white/50"}`}
          >
            Apply
          </button>
        )}
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="ml-auto text-white/40 hover:text-white"
          aria-label="Close panel"
        >
          ✕
        </button>
      </div>

      {tab === "ask" && (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3 text-sm">
            {chat.length === 0 && (
              <p className="text-white/40">Ask anything about this POC, its review, or its research.</p>
            )}
            {chat.map((m, i) => (
              <div
                key={i}
                className={`rounded-lg px-3 py-2 ${m.role === "user" ? "bg-blue-500/15 text-white" : "bg-white/5 text-white/85"}`}
              >
                {m.content}
              </div>
            ))}
            {asking && <div className="text-white/40">…</div>}
          </div>
          <div className="flex gap-2 border-t border-white/10 p-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="Ask about this POC…"
              className="flex-1 rounded-lg border border-white/12 bg-[#0c0e16] px-3 py-2 text-sm text-white outline-none focus:border-blue-500/50"
            />
            <button
              type="button"
              onClick={send}
              disabled={asking}
              className="rounded-lg bg-blue-500 px-3 py-2 text-sm font-medium text-white hover:bg-blue-400 disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      )}

      {tab === "apply" && isArchitect && (
        <div className="min-h-0 flex-1 overflow-y-auto p-3 text-sm">
          {!proposal ? (
            <>
              <div className="mb-2 text-white/70">
                {accepted.length} accepted comment{accepted.length === 1 ? "" : "s"} will be applied.
              </div>
              {accepted.length === 0 ? (
                <p className="mb-3 text-white/40">Accept some comments first (in the review thread).</p>
              ) : (
                <ul className="mb-3 space-y-1 text-white/70">
                  {accepted.map((c) => (
                    <li key={c.id} className="rounded border border-white/10 px-2 py-1">
                      <span className="text-white/40">{c.anchor_slug || "general"}</span> — {stakeholderName(c.stakeholder_id)}: {c.body.slice(0, 80)}
                    </li>
                  ))}
                </ul>
              )}
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Additional guidance (optional)"
                className="mb-2 h-20 w-full resize-none rounded-lg border border-white/12 bg-[#0c0e16] p-2 text-sm text-white outline-none focus:border-blue-500/50"
              />
              {error && <div className="mb-2 text-red-300">{error}</div>}
              <button
                type="button"
                onClick={runEdit}
                disabled={applying || (accepted.length === 0 && !note.trim())}
                className="w-full rounded-lg bg-blue-500 px-3 py-2 font-medium text-white hover:bg-blue-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {applying ? "Applying…" : "Let AI apply"}
              </button>
            </>
          ) : (
            <>
              <DiffView before={bundle.poc!.document_md} after={proposal.proposed_md} />
              {proposal.addressed.length > 0 && (
                <div className="mt-3">
                  <div className="mb-1 text-white/60">AI will close these comments:</div>
                  {proposal.addressed.map((id) => (
                    <label key={id} className="flex items-center gap-2 text-white/70">
                      <input
                        type="checkbox"
                        checked={proposal.closeIds.has(id)}
                        onChange={() => toggleClose(id)}
                      />
                      {stakeholderName(
                        bundle.comments.find((c) => c.id === id)?.stakeholder_id || "",
                      )}: {bundle.comments.find((c) => c.id === id)?.body.slice(0, 60)}
                    </label>
                  ))}
                </div>
              )}
              {error && <div className="mt-2 text-red-300">{error}</div>}
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={acceptProposal}
                  disabled={applying}
                  className="rounded-lg bg-emerald-500 px-3 py-2 font-medium text-white hover:bg-emerald-400 disabled:opacity-50"
                >
                  Accept
                </button>
                <button
                  type="button"
                  onClick={() => setProposal(null)}
                  className="rounded-lg border border-white/15 px-3 py-2 text-white/70 hover:bg-white/5"
                >
                  Discard
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
