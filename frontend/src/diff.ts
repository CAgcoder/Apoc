import { diffLines } from "diff";

export type DiffRowType = "add" | "remove" | "context";

export interface DiffRow {
  type: DiffRowType;
  text: string;
}

// Turn jsdiff line parts into one row per line, tagged add/remove/context.
// Trailing empty line from a terminal newline is dropped so rows map 1:1 to lines.
export function computeLineDiff(before: string, after: string): DiffRow[] {
  const parts = diffLines(before || "", after || "");
  const rows: DiffRow[] = [];
  for (const part of parts) {
    const type: DiffRowType = part.added ? "add" : part.removed ? "remove" : "context";
    const lines = part.value.split("\n");
    if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
    for (const text of lines) rows.push({ type, text });
  }
  return rows;
}
