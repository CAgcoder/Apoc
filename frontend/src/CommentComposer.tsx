import { useState } from "react";
import { renderInline } from "./markdown";

export function CommentComposer({
  placeholder,
  onSubmit,
  onCancel,
  submitting,
}: {
  placeholder: string;
  onSubmit: (body: string) => void;
  onCancel?: () => void;
  submitting?: boolean;
}) {
  const [tab, setTab] = useState<"write" | "preview">("write");
  const [body, setBody] = useState("");

  const tabClass = (active: boolean) =>
    `relative -mb-px rounded-t-md border px-3 py-1.5 text-sm ${
      active
        ? "border-[#30363d] border-b-[#0d1117] bg-[#0d1117] text-[#e6edf3]"
        : "border-transparent text-[#8b949e] hover:text-[#e6edf3]"
    }`;

  return (
    <div className="overflow-hidden rounded-md border border-[#30363d] bg-[#0d1117]">
      <div className="flex items-center gap-1 border-b border-[#30363d] bg-[#161b22] px-2 pt-2">
        <button type="button" onClick={() => setTab("write")} className={tabClass(tab === "write")}>
          Write
        </button>
        <button type="button" onClick={() => setTab("preview")} className={tabClass(tab === "preview")}>
          Preview
        </button>
      </div>
      <div className="p-3">
        {tab === "write" ? (
          <textarea
            autoFocus
            value={body}
            onChange={(event) => setBody(event.target.value)}
            placeholder={placeholder}
            className="h-28 w-full resize-y rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm text-[#e6edf3] placeholder:text-[#6e7681] outline-none focus:border-[#1f6feb] focus:ring-1 focus:ring-[#1f6feb]/60"
          />
        ) : (
          <div
            className="gh-comment-body min-h-28 rounded-md border border-[#30363d] bg-[#0d1117]"
            dangerouslySetInnerHTML={{
              __html: body.trim() ? renderInline(body) : "<p style='color:#8b949e'>Nothing to preview</p>",
            }}
          />
        )}
        <div className="mt-2 flex items-center gap-2">
          <span className="text-xs text-[#6e7681]">Styling with Markdown is supported</span>
          <div className="ml-auto flex gap-2">
            {onCancel && (
              <button
                type="button"
                onClick={onCancel}
                className="rounded-md border border-[#30363d] bg-[#21262d] px-3 py-1.5 text-sm font-medium text-[#c9d1d9] hover:bg-[#30363d]"
              >
                Cancel
              </button>
            )}
            <button
              type="button"
              disabled={!body.trim() || submitting}
              onClick={() => onSubmit(body.trim())}
              className="rounded-md border border-[#238636]/40 bg-[#238636] px-3 py-1.5 text-sm font-medium text-white hover:bg-[#2ea043] disabled:cursor-not-allowed disabled:border-[#30363d] disabled:bg-[#21262d] disabled:text-[#8b949e]"
            >
              {submitting ? "Commenting…" : "Comment"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
