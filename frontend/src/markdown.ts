import MarkdownIt from "markdown-it";

export interface LineMapEntry {
  line: number;
  endLine: number;
  slug?: string;
  tag?: string;
}

export function slugify(s: string): string {
  return s.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

// The model occasionally leaks its own tool-call syntax into the generated prose:
// DSML tags whose name is wrapped in special-token delimiters. DeepSeek uses the
// fullwidth vertical bar (U+FF5C, ｜); other tokenizers use the object-replacement
// char (U+FFFC, ￼). A whole `<｜｜DSML｜｜tool_calls> … </｜｜DSML｜｜tool_calls>` block
// can land at the top of the document. Strip the block and any stray DSML tags so
// the document renders as written.
const DELIM = "[\\uFF5C\\uFFFC]";
const DSML_BLOCK = new RegExp(
  `<${DELIM}*\\s*DSML${DELIM}*\\s*tool_calls>[\\s\\S]*?<\\/${DELIM}*\\s*DSML${DELIM}*\\s*tool_calls>`,
  "g",
);
const DSML_TAG = new RegExp(`<\\/?${DELIM}*\\s*DSML[\\s\\S]*?>`, "g");

export function stripToolArtifacts(src: string): string {
  return (src || "")
    .replace(DSML_BLOCK, "")
    .replace(DSML_TAG, "")
    .replace(/￼/g, "")
    .replace(/^\s+/, "");
}

function escapeAttr(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function makeDocMd(): MarkdownIt {
  const md = new MarkdownIt({ html: false, linkify: true, breaks: false });

  md.core.ruler.push("source_lines", (state) => {
    const env = state.env as { lineMap?: LineMapEntry[] };
    env.lineMap = [];
    for (let i = 0; i < state.tokens.length; i += 1) {
      const token = state.tokens[i];
      if (!token.map || token.level !== 0) continue;

      if (/_open$/.test(token.type)) {
        const line = token.map[0] + 1;
        const endLine = token.map[1];
        token.attrSet("data-line", String(line));
        if (token.type === "heading_open" && token.tag === "h2") {
          const inline = state.tokens[i + 1];
          const slug = slugify(inline?.type === "inline" ? inline.content : "");
          if (slug) token.attrSet("id", `sec-${slug}`);
          env.lineMap.push({ line, endLine, slug, tag: token.tag });
        } else {
          env.lineMap.push({ line, endLine, tag: token.tag });
        }
      }

      if (token.type === "fence" || token.type === "code_block") {
        const line = token.map[0] + 1;
        token.attrSet("data-line", String(line));
        env.lineMap.push({ line, endLine: token.map[1], tag: token.tag });
      }
    }
    return true;
  });

  const defaultFence =
    md.renderer.rules.fence ||
    ((tokens, idx, opts, _env, self) => self.renderToken(tokens, idx, opts));

  md.renderer.rules.fence = (tokens, idx, opts, env, self) => {
    const token = tokens[idx];
    if ((token.info || "").trim().toLowerCase() === "mermaid") {
      const line = token.map ? token.map[0] + 1 : 0;
      return `<div class="mermaid-block" data-line="${line}" data-code="${escapeAttr(token.content)}"></div>\n`;
    }
    return defaultFence(tokens, idx, opts, env, self);
  };

  return md;
}

const docMd = makeDocMd();
const inlineMd = new MarkdownIt({ html: false, linkify: true, breaks: true });

export function renderDoc(src: string): { html: string; lineMap: LineMapEntry[] } {
  const env: { lineMap?: LineMapEntry[] } = {};
  const html = docMd.render(stripToolArtifacts(src), env);
  return { html, lineMap: env.lineMap || [] };
}

export interface DocBlock {
  // 1-based source line where this block starts (the comment anchor).
  line: number;
  // Section slug, only for `## ` headings — what AI findings anchor to.
  slug?: string;
  tag: string;
  // Pre-rendered HTML for the block, or `mermaid` set instead for diagrams.
  html: string;
  mermaid?: string;
}

// Split the document into top-level blocks (heading, paragraph, list, table,
// diagram …) so each can be rendered as its own React element and carry its own
// comment anchor — the GitHub-diff "one row per block" model.
export function renderBlocks(src: string): DocBlock[] {
  const env: { lineMap?: LineMapEntry[] } = {};
  const tokens = docMd.parse(stripToolArtifacts(src), env);
  const blocks: DocBlock[] = [];
  let i = 0;
  while (i < tokens.length) {
    if (tokens[i].level !== 0) {
      i += 1;
      continue;
    }
    const start = i;
    let depth = 0;
    do {
      depth += tokens[i].nesting;
      i += 1;
    } while (i < tokens.length && depth > 0);

    const slice = tokens.slice(start, i);
    const head = slice[0];
    const line = head.map ? head.map[0] + 1 : 0;

    if (head.type === "fence" && (head.info || "").trim().toLowerCase() === "mermaid") {
      blocks.push({ line, tag: "mermaid", html: "", mermaid: head.content });
      continue;
    }

    let slug: string | undefined;
    if (head.type === "heading_open" && head.tag === "h2") {
      const inline = slice[1];
      slug = slugify(inline?.type === "inline" ? inline.content : "") || undefined;
    }
    blocks.push({ line, slug, tag: head.tag || head.type, html: docMd.renderer.render(slice, docMd.options, env) });
  }
  return blocks;
}

export function renderInline(src: string): string {
  return inlineMd.render(src || "");
}

export function renderMarkdown(md: string): { html: string; headings: string[] } {
  const rendered = renderDoc(md);
  return {
    html: rendered.html,
    headings: rendered.lineMap.filter((entry) => entry.slug).map((entry) => entry.slug || ""),
  };
}
