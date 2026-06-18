import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CommentStatus } from "./CommentStatus";

afterEach(() => vi.restoreAllMocks());

describe("CommentStatus", () => {
  it("shows the badge to everyone", () => {
    render(<CommentStatus status="accepted" canCurate={false} onChange={() => {}} />);
    expect(screen.getByText("accepted")).toBeTruthy();
  });

  it("hides controls from non-architects", () => {
    render(<CommentStatus status="open" canCurate={false} onChange={() => {}} />);
    expect(screen.queryByRole("button", { name: /accept/i })).toBeNull();
  });

  it("architect on an open comment can Accept and Close", () => {
    const onChange = vi.fn();
    render(<CommentStatus status="open" canCurate onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /^accept$/i }));
    expect(onChange).toHaveBeenCalledWith("accepted");
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onChange).toHaveBeenCalledWith("closed");
  });

  it("architect on a closed comment can Reopen", () => {
    const onChange = vi.fn();
    render(<CommentStatus status="closed" canCurate onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /reopen/i }));
    expect(onChange).toHaveBeenCalledWith("open");
  });

  it("architect on an accepted comment can Unaccept", () => {
    const onChange = vi.fn();
    render(<CommentStatus status="accepted" canCurate onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /unaccept/i }));
    expect(onChange).toHaveBeenCalledWith("open");
  });
});
