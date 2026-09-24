import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { ConfirmDialog } from "./ConfirmDialog";
import { describe, expect, it, vi } from "vitest";

function DialogHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open dialog
      </button>
      <ConfirmDialog
        open={open}
        title="Deactivate preset"
        message="This preset will no longer appear in new experiments."
        onConfirm={() => setOpen(false)}
        onCancel={() => setOpen(false)}
      />
    </>
  );
}

describe("ConfirmDialog", () => {
  it("traps focus, closes on Escape, and restores the opener", () => {
    render(<DialogHarness />);
    const opener = screen.getByRole("button", { name: "Open dialog" });
    opener.focus();
    fireEvent.click(opener);

    const cancel = screen.getByRole("button", { name: "Cancel" });
    const confirm = screen.getByRole("button", { name: "Confirm" });
    expect(cancel).toHaveFocus();

    confirm.focus();
    fireEvent.keyDown(confirm, { key: "Tab" });
    expect(cancel).toHaveFocus();

    fireEvent.keyDown(cancel, { key: "Tab", shiftKey: true });
    expect(confirm).toHaveFocus();

    fireEvent.keyDown(confirm, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("uses distinct accessible labels for simultaneous dialogs", () => {
    render(
      <>
        <ConfirmDialog
          open
          title="First action"
          message="First message"
          onConfirm={vi.fn()}
          onCancel={vi.fn()}
        />
        <ConfirmDialog
          open
          title="Second action"
          message="Second message"
          onConfirm={vi.fn()}
          onCancel={vi.fn()}
        />
      </>,
    );

    const dialogs = screen.getAllByRole("dialog");
    expect(dialogs).toHaveLength(2);
    expect(dialogs[0].getAttribute("aria-labelledby")).not.toBe(
      dialogs[1].getAttribute("aria-labelledby"),
    );
    expect(dialogs[0].getAttribute("aria-describedby")).not.toBe(
      dialogs[1].getAttribute("aria-describedby"),
    );
  });
});
