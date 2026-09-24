import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConditionPlanner } from "./ConditionPlanner";
import { createBlankDraft, setPlanType } from "./state";
import type { ExperimentDraft } from "./types";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api", () => ({ apiFetch: apiFetchMock }));

function comparativeDraftWithTargets(): ExperimentDraft {
  const draft = setPlanType(createBlankDraft(), "standalone");
  draft.substrate.width_mm = 15;
  draft.substrate.length_mm = 15;
  draft.layers = [
    {
      layer_type: "etl",
      role: "etl",
      name: "ETL",
      preset_id: null,
      solution: null,
      process: null,
    },
  ];
  return setPlanType(draft, "comparative");
}

function renderPlanner(draft: ExperimentDraft) {
  const onChange = vi.fn();
  render(
    <ConditionPlanner
      draft={draft}
      layouts={[]}
      onChange={onChange}
      onError={vi.fn()}
    />,
  );
  return onChange;
}

describe("ConditionPlanner plan-type switch", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue([]);
  });

  it("applies a non-destructive switch immediately without a dialog", () => {
    const onChange = renderPlanner(comparativeDraftWithTargets());

    fireEvent.click(screen.getByLabelText("Standalone"));

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0].plan_type).toBe("standalone");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("confirms before discarding condition-specific edits; Cancel keeps the draft", () => {
    const draft = comparativeDraftWithTargets();
    // Give the target its own edited layer stack (differs from the shared one).
    const target = draft.conditions.find((item) => item.kind === "target");
    expect(target).toBeDefined();
    if (!target) return;
    target.layers = [
      {
        layer_type: "htl",
        role: "htl",
        name: "Edited HTL",
        preset_id: null,
        solution: null,
        process: null,
      },
    ];
    const onChange = renderPlanner(draft);

    fireEvent.click(screen.getByLabelText("Standalone"));

    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).toMatch(/layer stack/i);
    // Cancel is the safe initial action and keeps the current plan type.
    const cancel = screen.getByRole("button", { name: "Cancel" });
    expect(cancel).toHaveFocus();
    fireEvent.click(cancel);
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(draft.plan_type).toBe("comparative");

    // Confirm applies the destructive switch and closes the dialog.
    fireEvent.click(screen.getByLabelText("Standalone"));
    fireEvent.click(screen.getByRole("button", { name: "Discard edits and switch" }));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0].plan_type).toBe("standalone");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
