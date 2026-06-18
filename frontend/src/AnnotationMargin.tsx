import { useLayoutEffect, useMemo, useRef, useState, type RefObject } from "react";
import type { Annotation } from "./api";
import { slugify } from "./markdown";

const SEV_RANK: Record<string, number> = { block: 3, warn: 2, info: 1 };
const SEV_BORDER: Record<string, string> = {
  block: "border-red-500/50",
  warn: "border-amber-500/50",
  info: "border-blue-500/40",
};

export const DOMAIN_COLOR: Record<string, string> = {
  compliance: "#a371f7",
  legal: "#a371f7",
  security: "#f85149",
  cost: "#d29922",
  architecture: "#4493f8",
  operations: "#56d364",
  data: "#79c0ff",
};

export type AnnoGroup = {
  slug: string;
  anchor: string;
  items: Annotation[];
  domains: string[];
  worst: string;
};

export function groupByAnchor(annotations: Annotation[]): AnnoGroup[] {
  const groups = new Map<string, AnnoGroup>();
  for (const annotation of annotations) {
    const slug = slugify(annotation.anchor || "");
    if (!slug) continue;
    let group = groups.get(slug);
    if (!group) {
      group = { slug, anchor: annotation.anchor, items: [], domains: [], worst: "info" };
      groups.set(slug, group);
    }
    group.items.push(annotation);
    if (!group.domains.includes(annotation.domain)) group.domains.push(annotation.domain);
    if ((SEV_RANK[annotation.severity] ?? 1) > (SEV_RANK[group.worst] ?? 1)) {
      group.worst = annotation.severity;
    }
  }
  return [...groups.values()];
}

export function layoutTops(groups: { desiredTop: number; height: number }[], gap: number): number[] {
  const sorted = groups.map((group, index) => ({ group, index })).sort((a, b) => a.group.desiredTop - b.group.desiredTop);
  const tops = new Array<number>(groups.length);
  let previousBottom = -Infinity;
  for (const item of sorted) {
    const top = Math.max(item.group.desiredTop, previousBottom + gap);
    tops[item.index] = top;
    previousBottom = top + item.group.height;
  }
  return tops;
}

export function AnnotationMargin({
  annotations,
  scrollRef,
  activeSlug,
  onActivate,
}: {
  annotations: Annotation[];
  scrollRef: RefObject<HTMLElement | null>;
  activeSlug: string | null;
  onActivate: (slug: string) => void;
}) {
  const groups = useMemo(() => groupByAnchor(annotations), [annotations]);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);
  const [tops, setTops] = useState<number[]>([]);
  const [minHeight, setMinHeight] = useState(0);

  useLayoutEffect(() => {
    const root = scrollRef.current;
    if (!root) return;

    const recompute = () => {
      const measured = groups.map((group, index) => {
        const section = root.querySelector<HTMLElement>(`#sec-${group.slug}`);
        return {
          desiredTop: section?.offsetTop ?? 0,
          height: cardRefs.current[index]?.offsetHeight ?? 96,
        };
      });
      const next = layoutTops(measured, 12);
      setTops(next);
      setMinHeight(next.reduce((max, top, index) => Math.max(max, top + measured[index].height), 0) + 32);
    };

    recompute();
    const observer = new ResizeObserver(recompute);
    observer.observe(root);
    window.addEventListener("resize", recompute);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", recompute);
    };
  }, [groups, scrollRef]);

  if (groups.length === 0) {
    return <div className="px-3 py-4 text-sm text-white/35">No AI findings.</div>;
  }

  return (
    <div className="relative" style={{ minHeight }}>
      {groups.map((group, index) => (
        <div
          key={group.slug}
          ref={(element) => {
            cardRefs.current[index] = element;
          }}
          id={`anno-${group.slug}`}
          onClick={() => onActivate(group.slug)}
          style={{ position: "absolute", top: tops[index] ?? 0, left: 0, right: 0 }}
          className={`mx-2 cursor-pointer rounded-lg border bg-[#0d1117] px-3 py-2 transition ${
            SEV_BORDER[group.worst] ?? SEV_BORDER.info
          } ${activeSlug === group.slug ? "ring-2 ring-white/35" : ""}`}
        >
          <div className="flex items-center gap-2 text-xs text-white/55">
            <span>
              {group.items.length} finding{group.items.length > 1 ? "s" : ""}
            </span>
            <span className="ml-auto flex gap-1">
              {group.domains.map((domain) => (
                <span
                  key={domain}
                  title={domain}
                  className="size-2 rounded-full"
                  style={{ background: DOMAIN_COLOR[domain] ?? "#8b949e" }}
                />
              ))}
            </span>
          </div>
          <div className="mt-1 truncate text-xs text-white/40">{group.anchor}</div>
          <div className="mt-2 grid gap-2">
            {group.items.map((annotation) => (
              <div key={annotation.id} className="rounded-md border border-white/8 bg-white/[0.02] p-2">
                <div className="flex items-center gap-2 text-xs text-white/45">
                  <span
                    className="size-2 rounded-full"
                    style={{ background: DOMAIN_COLOR[annotation.domain] ?? "#8b949e" }}
                  />
                  <span>{annotation.domain}</span>
                  <span>{annotation.severity}</span>
                </div>
                <div className="mt-1 text-sm font-medium text-white">{annotation.title}</div>
                {annotation.body && <div className="mt-1 text-xs text-white/70">{annotation.body}</div>}
                {annotation.suggestion && (
                  <div className="mt-1 text-xs text-white/55">
                    <span className="font-medium text-white/65">Suggestion:</span> {annotation.suggestion}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
