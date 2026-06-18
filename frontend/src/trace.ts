// Helpers for the Trace tab's research grounding: turn the inline citation
// markers in a research digest ([s1], [S1], [1] …) into an index that points at
// the numbered source list, so the prose and its links line up one-to-one.

import type { ResearchNote } from "./api";

export type CiteSource = ResearchNote["citations"][number];

export type DigestPart =
  | { type: "text"; value: string }
  | { type: "cite"; num: number; anchorId: string; token: string };

// Map every citation token a source can be referenced by (its source_id and its
// 1-based position) to that source's display number + scroll anchor id.
export function buildCitationIndex(sources: CiteSource[]): Map<string, { num: number; anchorId: string }> {
  const index = new Map<string, { num: number; anchorId: string }>();
  sources.forEach((c, i) => {
    const num = i + 1;
    const anchorId = (c.source_id && c.source_id.trim()) || `n${num}`;
    const entry = { num, anchorId };
    if (c.source_id) index.set(c.source_id.toLowerCase(), entry);
    index.set(String(num), entry);
  });
  return index;
}

// Split a digest into plain-text runs and resolved citation chips. Tokens that
// don't resolve to a known source (e.g. "[GoBD]", "[2026]") are left as text.
export function tokenizeDigest(digest: string, sources: CiteSource[]): DigestPart[] {
  const index = buildCitationIndex(sources);
  const parts: DigestPart[] = [];
  const re = /\[([A-Za-z]?\d{1,3})\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(digest))) {
    const hit = index.get(m[1].toLowerCase());
    if (!hit) continue;
    if (m.index > last) parts.push({ type: "text", value: digest.slice(last, m.index) });
    parts.push({ type: "cite", num: hit.num, anchorId: hit.anchorId, token: m[1] });
    last = m.index + m[0].length;
  }
  if (last < digest.length) parts.push({ type: "text", value: digest.slice(last) });
  return parts;
}
