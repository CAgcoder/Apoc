import { describe, expect, it } from "vitest";
import { renderDoc, renderInline, slugify, stripToolArtifacts } from "./markdown";

describe("stripToolArtifacts", () => {
  it.each([
    ["U+FF5C (DeepSeek)", "｜｜"],
    ["U+FFFC (object-replacement)", "￼￼"],
  ])("removes a leaked DSML tool_calls block (%s) but keeps the document", (_label, fc) => {
    const src =
      `<${fc}DSML${fc}tool_calls>\n` +
      `<${fc}DSML${fc}invoke name="run_shell">\n` +
      `<${fc}DSML${fc}parameter name="cmd" string="true">echo "hi"</${fc}DSML${fc}parameter>\n` +
      `</${fc}DSML${fc}invoke>\n` +
      `</${fc}DSML${fc}tool_calls>\n\n## Context & goals\n\nReal content.`;
    const out = stripToolArtifacts(src);
    expect(out).not.toContain("tool_calls");
    expect(out).not.toContain("run_shell");
    expect(out).not.toContain("DSML");
    expect(out.startsWith("## Context & goals")).toBe(true);
  });

  it("renderDoc strips the artifact before rendering", () => {
    const fc = "￼￼";
    const { html } = renderDoc(`<${fc}DSML${fc}tool_calls>x</${fc}DSML${fc}tool_calls>\n\n## Risks\n\ntext`);
    expect(html).toContain('id="sec-risks"');
    expect(html).not.toContain("tool_calls");
  });
});

describe("slugify", () => {
  it("kebab-cases headings", () => {
    expect(slugify("Context & goals")).toBe("context-goals");
  });
});

describe("renderDoc", () => {
  it("gives h2 a sec- id and a source line", () => {
    const { html, lineMap } = renderDoc("## Risks\n\ntext");
    expect(html).toContain('id="sec-risks"');
    expect(html).toMatch(/data-line="1"/);
    expect(lineMap.some((entry) => entry.line === 1 && entry.slug === "risks")).toBe(true);
  });

  it("turns a mermaid fence into a placeholder carrying the code", () => {
    const { html } = renderDoc("```mermaid\nflowchart LR\nA-->B\n```");
    expect(html).toContain('class="mermaid-block"');
    expect(html).toContain("flowchart LR");
    expect(html).not.toContain("<svg");
  });

  it("renders GFM tables", () => {
    const { html } = renderDoc("| a | b |\n|---|---|\n| 1 | 2 |");
    expect(html).toContain("<table");
  });
});

describe("renderInline", () => {
  it("renders markdown but escapes raw html", () => {
    const html = renderInline("**bold** <script>x</script>");
    expect(html).toContain("<strong>bold</strong>");
    expect(html).not.toContain("<script>");
  });
});
