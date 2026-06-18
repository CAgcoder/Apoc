import { useEffect, useMemo, useRef, useState } from "react";
import { api, PocBundle, ResearchNote, Stakeholder } from "./api";
import { AiPanel } from "./AiPanel";
import { MarkdownDoc } from "./MarkdownDoc";
import { stripToolArtifacts } from "./markdown";
import { tokenizeDigest } from "./trace";

type Tab = "deck" | "review" | "approvals" | "trace";

const VERDICT: Record<string, string> = {
  approve: "text-emerald-300",
  revise: "text-amber-300",
  block: "text-red-300",
  comment: "text-blue-300",
};

// Each reviewer role owns an annotation domain; their Review view leads with it.
const ROLE_DOMAIN: Record<string, string> = {
  compliance: "compliance",
  legal: "compliance",
  security: "security",
  finops: "cost",
  cto: "architecture",
};
const REVIEW_ROLES = ["compliance", "security", "finops", "cto", "legal"];

const ROLE_INTRO: Record<string, string> = {
  architect: "You own this POC. Present and edit the deck; resolve review findings.",
  compliance: "Review the POC for regulatory, data-residency and policy exposure.",
  legal: "Review the POC for contractual, data and regulatory risk.",
  security: "Review the POC's security controls, identity and data protection.",
  finops: "Review the POC's cost assumptions and cost risk.",
  cto: "Decide whether this POC is viable to proceed. Weigh the key trade-offs.",
  client_sponsor: "Follow the POC and the alignment progress.",
  consultant: "Follow the client POC and its review.",
};

// Which tabs each role sees, in order (first = default landing).
function tabsForRole(role: string): Tab[] {
  if (role === "architect") return ["deck", "review", "approvals", "trace"];
  if (REVIEW_ROLES.includes(role)) return ["review", "approvals", "deck", "trace"];
  return ["deck", "approvals", "trace"]; // sponsor / consultant: observe, no review lens
}

export function ProjectView({
  projectId,
  me,
  onBack,
}: {
  projectId: string;
  me: Stakeholder;
  onBack: () => void;
}) {
  const [bundle, setBundle] = useState<PocBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tabs = tabsForRole(me.role);
  const [tab, setTab] = useState<Tab>(tabs[0]);

  const load = () =>
    api
      .pocBundle(projectId)
      .then((b) => {
        setBundle(b);
        setError(null);
      })
      .catch((e: any) => setError(e?.message || "Could not load this project."));
  useEffect(() => {
    load();
  }, [projectId]);
  // When the viewer switches identity, land them on their role's default view.
  useEffect(() => {
    setTab(tabsForRole(me.role)[0]);
  }, [me.role]);

  if (error)
    return (
      <div className="p-6 text-sm text-red-300">
        <button onClick={onBack} className="mb-3 block text-white/50 hover:text-white">
          ← projects
        </button>
        {error}
        <button
          onClick={load}
          className="ml-3 rounded bg-white/10 px-2 py-1 text-xs text-white/70 hover:text-white"
        >
          Retry
        </button>
      </div>
    );
  if (!bundle) return <div className="p-6 text-white/40">Loading…</div>;
  const { project, poc, approval_rollup } = bundle;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-white/10 px-5 py-3">
        <button onClick={onBack} className="text-sm text-white/50 hover:text-white">
          ← projects
        </button>
        <h2 className="font-semibold text-white">{project.title}</h2>
        {approval_rollup?.ready && (
          <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs text-emerald-300">
            ✓ All approved — ready to align
          </span>
        )}
        <div className="ml-auto flex gap-1 text-sm">
          {tabs.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-lg px-3 py-1.5 capitalize ${
                tab === t ? "bg-white/10 text-white" : "text-white/50 hover:text-white"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      <div className="border-b border-white/5 bg-white/[0.02] px-5 py-1.5 text-xs text-white/45">
        As <span className="text-white/70">{me.name}</span> · {ROLE_INTRO[me.role] ?? ""}
      </div>

      {!poc ? (
        <div className="p-6 text-white/40">
          No POC generated yet (status: {project.status}).
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-hidden">
          {tab === "deck" && <DeckPane pocId={poc.id} me={me} />}
          {tab === "review" && (
            <>
              <ReviewPane bundle={bundle} me={me} reload={load} />
              <AiPanel bundle={bundle} me={me} reload={load} />
            </>
          )}
          {tab === "approvals" && <ApprovalsPane bundle={bundle} me={me} reload={load} />}
          {tab === "trace" && <TracePane projectId={projectId} bundle={bundle} />}
        </div>
      )}
    </div>
  );
}

function DeckPane({ pocId, me }: { pocId: string; me: Stakeholder }) {
  const editable = me.role === "architect";
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-5 py-2 text-sm text-white/50">
        {editable ? (
          <span className="text-blue-300">
            You are the architect — use <b>Edit</b> in the deck toolbar to change slides and Save.
          </span>
        ) : (
          <span>View only. Only the architect can edit the POC.</span>
        )}
      </div>
      <iframe
        key={me.role}
        title="POC deck"
        src={api.deckUrl(pocId, me.role)}
        className="min-h-0 flex-1 border-0 bg-black"
      />
    </div>
  );
}

function ReviewPane({
  bundle,
  me,
  reload,
}: {
  bundle: PocBundle;
  me: Stakeholder;
  reload: () => void;
}) {
  const { poc, annotations, comments, stakeholders, reviews } = bundle;
  const scrollRef = useRef<HTMLDivElement>(null);
  const [activeSlug, setActiveSlug] = useState<string | null>(null);

  const myDomain = ROLE_DOMAIN[me.role];
  const myReport = reviews.find((r) => r.role === me.role);
  const [showAll, setShowAll] = useState(!myDomain);
  const shown = useMemo(
    () => (showAll || !myDomain ? annotations : annotations.filter((a) => a.domain === myDomain)),
    [annotations, myDomain, showAll],
  );

  const activate = (slug: string) => {
    setActiveSlug(slug);
    window.requestAnimationFrame(() => {
      scrollRef.current?.querySelector(`#sec-${slug}`)?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  };

  return (
    <div ref={scrollRef} className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[80rem] px-5 py-4 pb-28">
        {myReport && (
          <div className="my-3 rounded-lg border border-blue-500/30 bg-blue-500/[0.07] p-3">
            <div className="text-xs text-blue-300/80">
              Your AI review draft: verdict{" "}
              <span className={VERDICT[myReport.verdict] ?? ""}>{myReport.verdict}</span>
            </div>
            <div className="mt-1 text-sm text-white/80">{myReport.summary}</div>
          </div>
        )}
        <div className="mb-3 flex items-center gap-2 text-sm text-white/45">
          <span>
            {shown.length} AI finding{shown.length === 1 ? "" : "s"} inline · hover a line and click
            <span className="mx-1 inline-flex size-4 items-center justify-center rounded bg-[#4493f8] text-[11px] font-semibold text-white">
              +
            </span>
            to comment
          </span>
          {myDomain && (
            <button
              type="button"
              onClick={() => setShowAll((value) => !value)}
              className="ml-auto rounded-md border border-white/12 px-2 py-0.5 text-xs text-white/60 hover:text-white"
            >
              {showAll ? "all domains" : `my domain: ${myDomain}`}
            </button>
          )}
        </div>
        <MarkdownDoc
          pocId={poc!.id}
          documentMd={poc!.document_md || ""}
          canEdit={me.role === "architect"}
          reload={reload}
          annotations={shown}
          comments={comments}
          stakeholders={stakeholders}
          me={me}
          activeSlug={activeSlug}
          onSlugActivate={activate}
        />
      </div>
    </div>
  );
}

function ApprovalsPane({
  bundle,
  me,
  reload,
}: {
  bundle: PocBundle;
  me: Stakeholder;
  reload: () => void;
}) {
  const { poc, reviews, approvals, approval_rollup, stakeholders } = bundle;
  const approverRoles = ["architect", "compliance", "security", "finops", "cto"];
  const approvers = stakeholders.filter((s) => approverRoles.includes(s.role));
  const statusOf = (id: string) => approvals.find((a) => a.stakeholder_id === id)?.status ?? "pending";
  const reviewOf = (role: string) => reviews.find((r) => r.role === role);

  const setStatus = async (status: string) => {
    await api.setApproval(poc!.id, { stakeholder_id: me.id, status }, me.role);
    reload();
  };

  return (
    <div className="mx-auto max-w-4xl space-y-4 overflow-y-auto p-6 h-full">
      <div className="rounded-xl border border-white/10 bg-[#141722] p-4">
        <div className="flex items-center justify-between">
          <div className="font-medium text-white">
            Approval progress: {approval_rollup.approved} / {approval_rollup.needed}
          </div>
          {approval_rollup.ready ? (
            <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-sm text-emerald-300">
              Ready to align — hold one short meeting
            </span>
          ) : (
            <span className="text-sm text-white/45">Waiting on remaining stakeholders</span>
          )}
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
          <div
            className="h-full bg-emerald-400"
            style={{ width: `${(approval_rollup.approved / Math.max(1, approval_rollup.needed)) * 100}%` }}
          />
        </div>
      </div>

      {approvers.map((s) => {
        const r = reviewOf(s.role);
        const st = statusOf(s.id);
        const isMe = s.id === me.id;
        return (
          <div key={s.id} className="rounded-xl border border-white/10 bg-[#141722] p-4">
            <div className="flex items-center gap-3">
              <span className="font-medium text-white">{s.name}</span>
              <span className="text-xs text-white/40 uppercase">{s.role}</span>
              {r && <span className={`text-xs ${VERDICT[r.verdict] ?? ""}`}>AI verdict: {r.verdict}</span>}
              <span
                className={`ml-auto rounded-full px-2.5 py-0.5 text-xs ${
                  st === "approved"
                    ? "bg-emerald-500/15 text-emerald-300"
                    : st === "changes_requested"
                    ? "bg-amber-500/15 text-amber-300"
                    : "bg-white/10 text-white/50"
                }`}
              >
                {st.replace(/_/g, " ")}
              </span>
            </div>
            {r && (
              <div className="mt-2 text-sm text-white/65">
                {r.summary}
              </div>
            )}
            {isMe && (
              <div className="mt-3 flex gap-2">
                <button
                  onClick={() => setStatus("approved")}
                  className="rounded-lg bg-emerald-500/90 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-400"
                >
                  Approve
                </button>
                <button
                  onClick={() => setStatus("changes_requested")}
                  className="rounded-lg bg-amber-500/90 px-3 py-1.5 text-sm font-medium text-black hover:bg-amber-400"
                >
                  Request changes
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// Human-readable label for each audit action (the raw event keys are terse).
const AUDIT_LABEL: Record<string, string> = {
  "project.created": "Project created",
  "intake.pdf_extracted": "Requirements extracted from PDF",
  "generation.started": "Generation started",
  "research.completed": "Web research grounded",
  "candidates.judged": "Candidate designs compared & fused",
  "document.completed": "POC document written",
  "reviews.completed": "Review board ran",
  "deck.completed": "Slide deck built",
  "fusion.completed": "Generation complete",
  "document.completed_legacy": "POC document written",
  "document.edited": "Document edited",
  "deck.edited": "Deck edited",
  "comment.added": "Comment added",
  "approval.set": "Approval updated",
  "generation.failed": "Generation failed",
};

// One-line summary of an event's detail payload.
function summarizeDetail(action: string, d: Record<string, any>): string {
  if (!d || typeof d !== "object") return "";
  const bits: string[] = [];
  if (typeof d.sources === "number") bits.push(`${d.sources} sources`);
  if (Array.isArray(d.candidates)) bits.push(`${d.candidates.length} candidates`);
  if (typeof d.picked_title === "string" && d.picked_title) bits.push(`→ ${d.picked_title}`);
  if (typeof d.sections === "number") bits.push(`${d.sections} sections`);
  if (typeof d.chars === "number") bits.push(`${d.chars.toLocaleString()} chars`);
  if (typeof d.reviews === "number") bits.push(`${d.reviews} reviews`);
  if (typeof d.annotations === "number") bits.push(`${d.annotations} findings`);
  if (typeof d.slides === "number") bits.push(`${d.slides} slides`);
  if (typeof d.fields === "number") bits.push(`${d.fields} fields`);
  return bits.join(" · ");
}

function ResearchGrounding({ research }: { research: ResearchNote }) {
  // Number each source and let the inline [s1] / [1] markers in the digest jump
  // to it — the index that ties the prose to its links.
  const sources = research.citations;

  const flashSource = (anchorId: string) => {
    const el = document.getElementById(`cite-${anchorId}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("cite-flash");
    setTimeout(() => el.classList.remove("cite-flash"), 1400);
  };

  // Split the digest into text + clickable citation chips. Strip any leaked
  // tool-call syntax (DeepSeek can emit it into the research digest too).
  const rendered = useMemo(
    () => tokenizeDigest(stripToolArtifacts(research.digest), sources),
    [research.digest, sources],
  );

  return (
    <div className="rounded-xl border border-white/10 bg-[#141722] p-4">
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-white/75">
        {rendered.map((part, i) =>
          part.type === "text" ? (
            part.value
          ) : (
            <button
              key={`cite-${i}`}
              onClick={() => flashSource(part.anchorId)}
              title={`Jump to source ${part.num}`}
              className="mx-0.5 rounded bg-blue-500/15 px-1 align-baseline text-[11px] font-medium text-blue-300 hover:bg-blue-500/30"
            >
              [{part.num}]
            </button>
          ),
        )}
      </p>
      <h4 className="mt-4 text-xs font-semibold uppercase tracking-wide text-white/40">
        Sources ({sources.length})
      </h4>
      <ol className="mt-1.5 space-y-1.5 text-sm">
        {sources.map((c, i) => {
          const num = i + 1;
          const anchorId = (c.source_id && c.source_id.trim()) || `n${num}`;
          const meta = [c.sitename, c.date].filter(Boolean).join(" · ");
          return (
            <li
              key={c.source_id ?? c.url ?? i}
              id={`cite-${anchorId}`}
              className="flex gap-2 rounded-md px-1 py-0.5 transition-colors"
            >
              <span className="shrink-0 font-mono text-xs text-white/35">[{num}]</span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <a href={c.url} target="_blank" rel="noreferrer" className="text-blue-300 hover:underline">
                    {c.title}
                  </a>
                  {meta && <span className="text-xs text-white/40">{meta}</span>}
                </div>
                {c.author && <div className="text-xs text-white/35">By {c.author}</div>}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function TracePane({ projectId, bundle }: { projectId: string; bundle: PocBundle }) {
  const [audit, setAudit] = useState<any[]>([]);
  useEffect(() => {
    api.audit(projectId).then(setAudit);
  }, [projectId]);
  const research = bundle.research?.[0];
  // The API returns events newest-first; read the pipeline oldest-first as a
  // numbered trace so step N's outputs feed step N+1.
  const steps = useMemo(() => [...audit].reverse(), [audit]);

  return (
    <div className="mx-auto grid max-w-5xl gap-6 overflow-y-auto p-6 h-full md:grid-cols-2">
      <section>
        <h3 className="mb-2 font-semibold text-white">Research grounding</h3>
        {research ? (
          <ResearchGrounding research={research} />
        ) : (
          <p className="text-white/40">
            No research recorded for this POC (it predates research persistence, or used the
            legacy path). New generations capture the web-research digest and its sources here.
          </p>
        )}
      </section>
      <section>
        <h3 className="mb-2 font-semibold text-white">Audit trail</h3>
        <ol className="relative space-y-3 border-l border-white/10 pl-5 text-sm">
          {steps.map((e, i) => {
            const detail = summarizeDetail(e.action, e.detail || {});
            const label = AUDIT_LABEL[e.action] ?? e.action;
            const failed = e.action.endsWith(".failed");
            return (
              <li key={e.id} id={`ev-${i + 1}`} className="relative">
                <span
                  className={`absolute -left-[1.45rem] top-1 h-2.5 w-2.5 rounded-full ring-2 ring-[#0c0e16] ${
                    failed ? "bg-red-400" : "bg-blue-400"
                  }`}
                />
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-[11px] text-white/35">{i + 1}</span>
                  <span className={`font-medium ${failed ? "text-red-300" : "text-white/90"}`}>
                    {label}
                  </span>
                  {e.actor !== "system" && (
                    <span className="text-xs text-white/45">· {e.actor}</span>
                  )}
                </div>
                {detail && <div className="mt-0.5 text-xs text-white/55">{detail}</div>}
                <div className="mt-0.5 font-mono text-[11px] text-white/30">
                  {new Date(e.created_at).toLocaleString()} · {e.action}
                </div>
              </li>
            );
          })}
          {steps.length === 0 && <li className="text-white/40">No events recorded.</li>}
        </ol>
      </section>
    </div>
  );
}
