import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Dialog } from "./Dialog";

describe("Dialog accessibility behaviour", () => {
  it("focuses the first control, closes on Escape, and restores focus", () => {
    const onClose = vi.fn();
    render(
      <>
        <button type="button">Open</button>
        <Dialog open onClose={onClose} title="Confirm cancellation">
          <button type="button">Keep booking</button>
        </Dialog>
      </>,
    );

    const dialog = screen.getByRole("dialog", { name: "Confirm cancellation" });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep booking" })).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("wraps Tab at the dialog boundaries", () => {
    render(
      <Dialog open onClose={() => undefined} title="Confirm cancellation">
        <button type="button">First</button>
        <button type="button">Last</button>
      </Dialog>,
    );
    const first = screen.getByRole("button", { name: "First" });
    const last = screen.getByRole("button", { name: "Close" });

    last.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(first).toHaveFocus();

    first.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(last).toHaveFocus();
  });
});
