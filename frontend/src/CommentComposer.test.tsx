import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CommentComposer } from "./CommentComposer";

describe("CommentComposer", () => {
  it("renders write and preview tabs around the textarea", () => {
    const html = renderToStaticMarkup(
      <CommentComposer placeholder="Comment as Ada..." onSubmit={() => {}} />,
    );

    expect(html).toContain("Write");
    expect(html).toContain("Preview");
    expect(html).toContain("Comment as Ada...");
  });
});
