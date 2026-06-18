import { useMemo } from "react";
import { computeLineDiff, type DiffRowType } from "./diff";

const GUTTER: Record<DiffRowType, string> = { add: "+", remove: "-", context: " " };
const ROW_CLASS: Record<DiffRowType, string> = {
  add: "diff-add",
  remove: "diff-remove",
  context: "diff-context",
};

export function DiffView({ before, after }: { before: string; after: string }) {
  const rows = useMemo(() => computeLineDiff(before, after), [before, after]);
  return (
    <div className="diff-view">
      {rows.map((row, i) => (
        <div key={i} className={`diff-row ${ROW_CLASS[row.type]}`}>
          <span className="diff-gutter">{GUTTER[row.type]}</span>
          <span className="diff-text">{row.text || " "}</span>
        </div>
      ))}
    </div>
  );
}
