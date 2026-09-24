import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HelpHint } from "./HelpHint";

describe("HelpHint", () => {
  it("exposes the guidance to assistive technology and pins it on click", () => {
    render(
      <HelpHint label="VCD program">
        <p>Rows run in order.</p>
      </HelpHint>,
    );

    const trigger = screen.getByRole("button", { name: /vcd program help/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveAttribute("aria-describedby");
    expect(screen.getByText("Rows run in order.")).toBeInTheDocument();

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    fireEvent.keyDown(trigger, { key: "Escape" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });
});
