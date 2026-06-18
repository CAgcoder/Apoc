import { describe, expect, it } from "vitest";
import { formatPdfExtractionMeta, GENERATION_STALL_MS } from "./Dashboard";

describe("generation watchdog", () => {
  it("waits ten minutes before treating a quiet stream as stalled", () => {
    expect(GENERATION_STALL_MS).toBe(10 * 60 * 1000);
  });
});

describe("PDF extraction metadata", () => {
  it("summarizes page count, used characters, and truncation state", () => {
    expect(formatPdfExtractionMeta({
      source_type: "uploaded_pdf",
      page_count: 7,
      chars_used: 4636,
      truncated: false,
    })).toBe("PDF: 7 pages | 4,636 chars used | complete");

    expect(formatPdfExtractionMeta({
      source_type: "uploaded_pdf",
      page_count: 12,
      chars_used: 60000,
      truncated: true,
    })).toBe("PDF: 12 pages | 60,000 chars used | truncated");
  });

  it("returns an empty label for non-PDF provenance", () => {
    expect(formatPdfExtractionMeta({ source_type: "guided_chat" })).toBe("");
  });
});
