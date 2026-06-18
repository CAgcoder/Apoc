import { useEffect, useLayoutEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import { createRoot, type Root } from "react-dom/client";
import { api, type Annotation, type Comment, type Stakeholder } from "./api";
import { DOMAIN_COLOR, groupByAnchor, layoutTops } from "./AnnotationMargin";
import { CommentComposer } from "./CommentComposer";
import { CommentStatus } from "./CommentStatus";
import { Mermaid } from "./Mermaid";
import { renderBlocks, renderDoc, renderInline } from "./markdown";

const SEV_LABEL: Record<string, string> = { block: "gh-label-block", warn: "gh-label-warn", info: "gh-label-info" };

function initials(name: string): string {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() ?? "")
      .join("") || "?"
  );
}

function AiComment({ annotation }: { annotation: Annotation }) {
  return (
    <div className="gh-comment">
      <div className="gh-comment-head">
        <span className="gh-avatar gh-avatar-bot">AI</span>
        <b>AI review</b>
        <span className="gh-dot" style={{ background: DOMAIN_COLOR[annotation.domain] ?? "#8b949e" }} />
        <span>{annotation.domain}</span>
        <span className="gh-spacer" />
        <span className={`gh-label ${SEV_LABEL[annotation.severity] ?? SEV_LABEL.info}`}>{annotation.severity}</span>
      </div>
      <div className="gh-comment-body">
        <div className="gh-comment-title">{annotation.title}</div>
        {annotation.body && <div>{annotation.body}</div>}
        {annotation.suggestion && (
          <div className="gh-suggestion">
            <div className="gh-suggestion-label">Suggested change</div>
            <div className="gh-suggestion-body">{annotation.suggestion}</div>
          </div>
        )}
      </div>
    </div>
  );
}

function HumanComment({
  name,
  comment,
  canCurate,
  onStatus,
}: {
  name: string;
  comment: Comment;
  canCurate: boolean;
  onStatus: (status: string) => void;
}) {
  return (
    <div className={`gh-comment${comment.status === "closed" ? " gh-comment-closed" : ""}`}>
      <div className="gh-comment-head">
        <span className="gh-avatar">{initials(name)}</span>
        <b>{name}</b>
        <span>commented</span>
        <span className="gh-spacer" />
        <CommentStatus status={comment.status} canCurate={canCurate} onChange={(s) => onStatus(s)} />
      </div>
      <div className="gh-comment-body" dangerouslySetInnerHTML={{ __html: renderInline(comment.body) }} />
    </div>
  );
}

export function MarkdownDoc({
  pocId,
  documentMd,
  canEdit,
  reload,
  annotations,
  comments,
  stakeholders,
  me,
  activeSlug,
  onSlugActivate,
}: {
  pocId: string;
  documentMd: string;
  canEdit: boolean;
  reload: () => void;
  annotations: Annotation[];
  comments: Comment[];
  stakeholders: Stakeholder[];
  me: Stakeholder;
  activeSlug: string | null;
  onSlugActivate: (slug: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(documentMd);
  const [saving, setSaving] = useState(false);
  const [posting, setPosting] = useState(false);
  const [composer, setComposer] = useState<{ line: number; slug: string } | null>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const previewMermaidRoots = useRef<Root[]>([]);
  const docColRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);
  const [tops, setTops] = useState<number[]>([]);
  const [annoMinHeight, setAnnoMinHeight] = useState(0);

  useEffect(() => setDraft(documentMd), [documentMd]);

  const blocks = useMemo(() => renderBlocks(documentMd), [documentMd]);
  const preview = useMemo(() => renderDoc(draft), [draft]);

  // AI findings grouped by the section they anchor to.
  const annoGroups = useMemo(() => groupByAnchor(annotations), [annotations]);

  // Float each AI group at the vertical offset of its section in the left
  // column, nudging groups down to avoid overlap (the doc stays continuous).
  useLayoutEffect(() => {
    if (editing) return;
    const col = docColRef.current;
    if (!col) return;
    const recompute = () => {
      const colTop = col.getBoundingClientRect().top;
      const measured = annoGroups.map((group, index) => {
        const section = col.querySelector<HTMLElement>(`#sec-${group.slug}`);
        const desiredTop = section ? section.getBoundingClientRect().top - colTop : 0;
        return { desiredTop: Math.max(0, desiredTop), height: cardRefs.current[index]?.offsetHeight ?? 120 };
      });
      const next = layoutTops(measured, 14);
      setTops(next);
      setAnnoMinHeight(next.reduce((max, top, index) => Math.max(max, top + measured[index].height), 0) + 24);
    };
    recompute();
    const observer = new ResizeObserver(recompute);
    observer.observe(col);
    window.addEventListener("resize", recompute);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", recompute);
    };
  }, [annoGroups, blocks, editing]);

  const commentsByLine = useMemo(() => {
    const map = new Map<number, Comment[]>();
    for (const comment of comments) {
      if (comment.anchor_line == null) continue;
      map.set(comment.anchor_line, [...(map.get(comment.anchor_line) || []), comment]);
    }
    return map;
  }, [comments]);

  const stakeholderName = (id: string) => stakeholders.find((stakeholder) => stakeholder.id === id)?.name ?? "Someone";

  // Editing preview still renders Markdown to one blob; mount its mermaid fences.
  const mountMermaids = (root: HTMLElement | null, rootsRef: MutableRefObject<Root[]>) => {
    if (!root) return;
    rootsRef.current.forEach((mounted) => mounted.unmount());
    rootsRef.current = [];
    root.querySelectorAll<HTMLElement>(".mermaid-block").forEach((element) => {
      const mounted = createRoot(element);
      mounted.render(<Mermaid code={element.getAttribute("data-code") || ""} />);
      rootsRef.current.push(mounted);
    });
  };

  useEffect(() => {
    if (!editing) return;
    mountMermaids(previewRef.current, previewMermaidRoots);
    return () => {
      previewMermaidRoots.current.forEach((mounted) => mounted.unmount());
      previewMermaidRoots.current = [];
    };
  }, [editing, preview.html]);

  useEffect(() => {
    if (editing) setComposer(null);
  }, [editing]);

  const submitComment = async (body: string) => {
    if (!composer) return;
    setPosting(true);
    try {
      await api.addComment(
        pocId,
        { stakeholder_id: me.id, body, anchor_line: composer.line, anchor_slug: composer.slug || null },
        me.role,
      );
      setComposer(null);
      reload();
    } finally {
      setPosting(false);
    }
  };

  const changeStatus = async (commentId: string, status: string) => {
    await api.setCommentStatus(pocId, commentId, status, me.role);
    reload();
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.saveDocument(pocId, { document_md: draft }, "architect");
      setEditing(false);
      reload();
    } finally {
      setSaving(false);
    }
  };

  if (!documentMd.trim() && !editing) {
    return (
      <div className="rounded-lg border border-white/10 bg-white/[0.02] p-5 text-sm text-white/45">
        This POC was created before Markdown review. Regenerate it to view the new review screen.
      </div>
    );
  }

  return (
    <div className="relative">
      {canEdit && (
        <div className="sticky top-0 z-30 mb-3 flex items-center gap-2 border-b border-white/10 bg-[#0c0e16] py-2">
          {!editing ? (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="rounded-lg border border-white/15 px-3 py-1.5 text-sm text-white/80 hover:bg-white/5"
            >
              Edit document
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={save}
                disabled={saving}
                className="rounded-lg bg-blue-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {saving ? "Saving" : "Save"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setEditing(false);
                  setDraft(documentMd);
                }}
                className="rounded-lg border border-white/15 px-3 py-1.5 text-sm text-white/60 hover:bg-white/5 hover:text-white"
              >
                Cancel
              </button>
            </>
          )}
        </div>
      )}

      {editing ? (
        <div className="grid grid-cols-2 gap-3">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="h-[70dvh] w-full resize-none rounded-lg border border-white/12 bg-[#0d1117] p-3 font-mono text-xs text-white outline-none focus:border-blue-500/50"
          />
          <div
            ref={previewRef}
            className="md doc-html h-[70dvh] overflow-y-auto rounded-lg border border-white/10 p-3"
            dangerouslySetInnerHTML={{ __html: preview.html }}
          />
        </div>
      ) : (
        <div className="gh-split">
          <div className="gh-doc-col" ref={docColRef}>
            {blocks.map((block, index) => {
              const lineComments = commentsByLine.get(block.line);
              const isActive = !!block.slug && block.slug === activeSlug;
              return (
                <div className={`gh-left${isActive ? " gh-left-active" : ""}`} key={`${block.line}-${index}`}>
                  <div className="gh-num">
                    <span>{block.line}</span>
                    <button
                      type="button"
                      className="gh-plus"
                      title="Comment on this section"
                      onClick={() => setComposer({ line: block.line, slug: block.slug || "" })}
                    >
                      +
                    </button>
                  </div>
                  <div className="gh-content">
                    {block.mermaid ? (
                      <Mermaid code={block.mermaid} />
                    ) : (
                      <div className="md" dangerouslySetInnerHTML={{ __html: block.html }} />
                    )}
                    {(lineComments?.length || composer?.line === block.line) && (
                      <div className="gh-thread gh-human">
                        {lineComments?.map((comment) => (
                          <HumanComment
                            key={comment.id}
                            name={stakeholderName(comment.stakeholder_id)}
                            comment={comment}
                            canCurate={canEdit}
                            onStatus={(status) => changeStatus(comment.id, status)}
                          />
                        ))}
                        {composer?.line === block.line && (
                          <CommentComposer
                            placeholder={`Leave a comment as ${me.name}`}
                            submitting={posting}
                            onCancel={() => setComposer(null)}
                            onSubmit={submitComment}
                          />
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="gh-anno-col" style={{ minHeight: annoMinHeight }}>
            {annoGroups.map((group, index) => (
              <div
                key={group.slug}
                ref={(element) => {
                  cardRefs.current[index] = element;
                }}
                className={`gh-thread gh-ai${group.slug === activeSlug ? " gh-ai-active" : ""}`}
                style={{ position: "absolute", top: tops[index] ?? 0, left: 0, right: 0 }}
                onClick={() => onSlugActivate(group.slug)}
              >
                {group.items.map((annotation) => (
                  <AiComment key={annotation.id} annotation={annotation} />
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
