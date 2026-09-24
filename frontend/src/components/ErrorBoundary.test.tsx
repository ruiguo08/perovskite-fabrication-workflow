import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary";

function Bomb(): never {
  throw new Error("unhandled render failure");
}

describe("ErrorBoundary", () => {
  it("renders children when nothing throws", () => {
    render(
      <ErrorBoundary>
        <p>Stable content</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("Stable content")).toBeInTheDocument();
  });

  it("shows an alert with a reload action when a child throws", () => {
    const consoleSpy = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    try {
      render(
        <ErrorBoundary>
          <Bomb />
        </ErrorBoundary>,
      );
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Reload" }),
      ).toBeInTheDocument();
    } finally {
      consoleSpy.mockRestore();
    }
  });
});
