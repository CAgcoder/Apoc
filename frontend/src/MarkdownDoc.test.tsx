import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MarkdownDoc } from "./MarkdownDoc";
import type { Comment, Stakeholder } from "./api";

const architect: Stakeholder = {
  id: "s1",
  name: "Ada",
  role: "architect",
  org: "O",
};

const openComment: Comment = {
  id: "c1",
  annotation_id: null,
  stakeholder_id: "s1",
  body: "please fix",
  anchor_line: 1,
  anchor_slug: "risks",
  status: "open",
  created_at: "",
};

describe("MarkdownDoc", () => {
  it("renders markdown document sections and architect edit control", () => {
    const html = renderToStaticMarkup(
      <MarkdownDoc
        pocId="poc1"
        documentMd={"## Risks\n\nText"}
        canEdit
        reload={() => {}}
        annotations={[]}
        comments={[]}
        stakeholders={[architect]}
        me={architect}
        activeSlug={null}
        onSlugActivate={() => {}}
      />,
    );

    expect(html).toContain("Edit document");
    expect(html).toContain("sec-risks");
  });
});

describe("MarkdownDoc comment status", () => {
  it("renders the status badge on a human comment", () => {
    const html = renderToStaticMarkup(
      <MarkdownDoc
        pocId="poc1"
        documentMd={"## Risks\n\nText"}
        canEdit
        reload={() => {}}
        annotations={[]}
        comments={[openComment]}
        stakeholders={[architect]}
        me={architect}
        activeSlug={null}
        onSlugActivate={() => {}}
      />,
    );
    expect(html).toContain("please fix");
    expect(html).toContain("open"); // badge text
    expect(html).toContain("Accept"); // architect control
  });

  it("hides curate controls from non-architects", () => {
    const observer: Stakeholder = { id: "s9", name: "Obs", role: "client_sponsor", org: "O" };
    const html = renderToStaticMarkup(
      <MarkdownDoc
        pocId="poc1"
        documentMd={"## Risks\n\nText"}
        canEdit={false}
        reload={() => {}}
        annotations={[]}
        comments={[openComment]}
        stakeholders={[observer]}
        me={observer}
        activeSlug={null}
        onSlugActivate={() => {}}
      />,
    );
    expect(html).toContain("please fix");
    expect(html).not.toContain(">Accept<");
  });
});
