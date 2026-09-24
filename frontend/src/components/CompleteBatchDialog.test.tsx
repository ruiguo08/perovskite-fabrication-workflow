import { fireEvent, render, screen } from "@testing-library/react";
import { CompleteBatchDialog } from "./CompleteBatchDialog";
import type { FrozenBatchCondition } from "../types/api";
import { describe, expect, it, vi } from "vitest";

const conditions: FrozenBatchCondition[] = [
  {
    id: 11,
    fabrication_batch_id: 1,
    source_condition_id: 1,
    condition_code: "exp-C",
    condition_name: "Control",
    role: "control",
    source_condition_hash: "a".repeat(64),
    recipe_snapshot: {},
    recipe_schema_version: 3,
    device_layout_code: "15x15_dual_005",
    device_layout_snapshot: {},
    planned_substrate_count: 3,
    expected_device_count: 6,
    actual_substrate_count: null,
  },
  {
    id: 12,
    fabrication_batch_id: 1,
    source_condition_id: 2,
    condition_code: "exp-T1",
    condition_name: "Target 1",
    role: "target",
    source_condition_hash: "b".repeat(64),
    recipe_snapshot: {},
    recipe_schema_version: 3,
    device_layout_code: "15x15_dual_005",
    device_layout_snapshot: {},
    planned_substrate_count: 3,
    expected_device_count: 6,
    actual_substrate_count: null,
  },
];

function renderDialog(onConfirm: (inputs: Record<number, { actualCount: number | ""; deviationDescription: string }>) => void = vi.fn()) {
  render(
    <CompleteBatchDialog
      open
      conditions={conditions}
      submitting={false}
      error={null}
      onConfirm={onConfirm}
      onCancel={vi.fn()}
    />,
  );
  return onConfirm;
}

describe("CompleteBatchDialog", () => {
  it("defaults each count to the planned count and enables submission", () => {
    const onConfirm = renderDialog();
    const confirm = screen.getByRole("button", { name: "Complete batch" });
    expect(confirm).not.toBeDisabled();
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledWith({
      11: { actualCount: 3, deviationDescription: "" },
      12: { actualCount: 3, deviationDescription: "" },
    });
  });

  it("keeps a cleared count empty (not zero), shows a field error, and disables submission", () => {
    renderDialog();
    const controlInput = document.querySelector(
      "[data-completion-count='11']",
    ) as HTMLInputElement;

    fireEvent.change(controlInput, { target: { value: "" } });
    expect(controlInput.value).toBe("");

    expect(
      screen.getByText(/enter how many substrates were actually made/i),
    ).toBeInTheDocument();
    const confirm = screen.getByRole("button", { name: "Complete batch" });
    expect(confirm).toBeDisabled();

    fireEvent.change(controlInput, { target: { value: "2" } });
    expect(screen.queryByText(/enter how many substrates were actually made/i)).not.toBeInTheDocument();
    // 2 is below the planned 3, so a reason is required before submitting.
    expect(confirm).toBeDisabled();
    fireEvent.change(
      document.querySelector("[data-completion-deviation='11']") as HTMLTextAreaElement,
      { target: { value: "Two usable substrates." } },
    );
    expect(confirm).not.toBeDisabled();
  });

  it("requires a deviation reason only for conditions below the planned count", () => {
    renderDialog();
    const controlInput = document.querySelector(
      "[data-completion-count='11']",
    ) as HTMLInputElement;
    const targetInput = document.querySelector(
      "[data-completion-count='12']",
    ) as HTMLInputElement;

    fireEvent.change(controlInput, { target: { value: "2" } });
    expect(document.querySelector("[data-completion-deviation='11']")).not.toBeNull();
    // The target is still at its planned count: no reason is requested.
    expect(document.querySelector("[data-completion-deviation='12']")).toBeNull();

    const confirm = screen.getByRole("button", { name: "Complete batch" });
    expect(confirm).toBeDisabled();

    fireEvent.change(
      document.querySelector("[data-completion-deviation='11']") as HTMLTextAreaElement,
      { target: { value: "One substrate broke." } },
    );
    expect(confirm).not.toBeDisabled();

    // A count of zero means the whole group is abandoned and still needs a reason.
    fireEvent.change(targetInput, { target: { value: "0" } });
    expect(document.querySelector("[data-completion-deviation='12']")).not.toBeNull();
  });
});
