import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LayerStackEditor } from "./LayerStackEditor";
import { addLayer, createBlankDraft } from "./state";
import type { ExperimentDraft } from "./types";
import type { LayerPreset, PerovskiteDepositionProcess } from "../../types/api";

const perovskiteProcess: PerovskiteDepositionProcess = {
  method: "spin_coating_vcd",
  spin_steps: [{ rpm: 3000, seconds: 30, acceleration_rpm_per_s: 1000 }],
  vcd_stages: [{ valve: "VV02", pressure_pa: 1000, seconds: 5 }],
  gas_backfill_stages: [],
  vcd_step_sequence: ["vcd_stage1"],
  anneal_steps: [{ temperature_c: 100, seconds: 1800 }],
};

function preset(id: number, layer: LayerPreset["layer"], depositionProcess: LayerPreset["deposition_process"]): LayerPreset {
  return {
    id,
    preset_key: `preset-${id}`,
    name: layer.name,
    status: "active",
    scope: "shared",
    layer,
    deposition_process: depositionProcess,
    current_revision_number: 1,
    current_version_id: id + 10,
    canonical_hash: "c".repeat(64),
    created_at: "2026-08-01T08:00:00Z",
    updated_at: "2026-08-01T08:00:00Z",
  };
}

const PEROVSKITE_PRESET = preset(1, {
  layer_type: "perovskite",
  role: "perovskite",
  name: "Perovskite stock",
  preset_id: null,
  solution: null,
  process: null,
}, perovskiteProcess);

const NIOX_PRESET = preset(2, {
  layer_type: "niox",
  role: "htl",
  name: "NiOx HTL",
  preset_id: null,
  solution: null,
  process: null,
}, null);

function Harness() {
  const [draft, setDraft] = useState<ExperimentDraft>(() => createBlankDraft());
  return (
    <LayerStackEditor
      draft={draft}
      presets={[PEROVSKITE_PRESET, NIOX_PRESET]}
      materials={[]}
      onChange={setDraft}
      onError={vi.fn()}
    />
  );
}

describe("LayerStackEditor Perovskite process editor visibility", () => {
  it("renders no process editor when the layer stack is empty", () => {
    render(<Harness />);

    expect(screen.queryByRole("heading", { name: "Perovskite deposition process" })).not.toBeInTheDocument();
    expect(screen.queryByText(/spin_steps|Add VCD stage/i)).not.toBeInTheDocument();
  });

  it("renders the process editor after a Perovskite preset is added", () => {
    render(<Harness />);

    fireEvent.change(screen.getByLabelText("Layer preset"), { target: { value: String(PEROVSKITE_PRESET.id) } });
    fireEvent.click(screen.getByRole("button", { name: "Add copied preset" }));

    expect(screen.getByRole("heading", { name: "Perovskite deposition process" })).toBeInTheDocument();
  });

  it("keeps the process editor hidden for a non-perovskite layer stack", () => {
    render(<Harness />);

    fireEvent.change(screen.getByLabelText("Layer preset"), { target: { value: String(NIOX_PRESET.id) } });
    fireEvent.click(screen.getByRole("button", { name: "Add copied preset" }));

    expect(screen.queryByRole("heading", { name: "Perovskite deposition process" })).not.toBeInTheDocument();
  });
});

describe("LayerStackEditor blank layers", () => {
  it("adds a blank layer from scratch without any preset", () => {
    render(<Harness />);
    const picker = screen.getByLabelText(/New blank layer/i);
    // An empty stack offers every layer type from scratch.
    expect(within(picker).getByRole("option", { name: /Ag · top electrode/i })).toBeInTheDocument();
    fireEvent.change(picker, { target: { value: "ag" } });
    fireEvent.click(screen.getByRole("button", { name: "Add blank layer" }));
    expect(screen.getByRole("heading", { name: "Ag" })).toBeInTheDocument();
    // The picker resets and no longer offers the unique type that is present.
    expect(picker).toHaveValue("");
    expect(within(picker).queryByRole("option", { name: /Ag · top electrode/i })).not.toBeInTheDocument();
  });
});

describe("LayerStackEditor drag-and-drop reordering", () => {
  function TwoNioxHarness() {
    const [draft, setDraft] = useState<ExperimentDraft>(() => {
      let initial = createBlankDraft();
      initial = addLayer(initial, NIOX_PRESET);
      return addLayer(initial, { ...NIOX_PRESET, id: 3, layer: { ...NIOX_PRESET.layer, name: "Second NiOx" } });
    });
    return (
      <LayerStackEditor
        draft={draft}
        presets={[NIOX_PRESET]}
        materials={[]}
        onChange={setDraft}
        onError={vi.fn()}
      />
    );
  }

  it("reorders two same-type layers when the second is dragged onto the first", () => {
    render(<TwoNioxHarness />);
    const cards = screen.getAllByRole("article");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).getByText("NiOx HTL")).toBeInTheDocument();
    expect(within(cards[1]).getByText("Second NiOx")).toBeInTheDocument();

    // Drag the second NiOx (index 1) onto the first (index 0).
    fireEvent.dragStart(within(cards[1]).getByText("⠿"));
    fireEvent.dragOver(cards[0]);
    fireEvent.drop(cards[0]);

    const reordered = screen.getAllByRole("article");
    expect(within(reordered[0]).getByText("Second NiOx")).toBeInTheDocument();
    expect(within(reordered[1]).getByText("NiOx HTL")).toBeInTheDocument();
  });

  function SingleNioxHarness() {
    const [draft, setDraft] = useState<ExperimentDraft>(() => addLayer(createBlankDraft(), NIOX_PRESET));
    return (
      <LayerStackEditor
        draft={draft}
        presets={[NIOX_PRESET]}
        materials={[]}
        onChange={setDraft}
        onError={vi.fn()}
      />
    );
  }

  function NioxPairThenPerovskiteHarness() {
    const [draft, setDraft] = useState<ExperimentDraft>(() => {
      let initial = createBlankDraft();
      initial = addLayer(initial, NIOX_PRESET);
      initial = addLayer(initial, { ...NIOX_PRESET, id: 3, layer: { ...NIOX_PRESET.layer, name: "Second NiOx" } });
      return addLayer(initial, PEROVSKITE_PRESET);
    });
    return (
      <LayerStackEditor
        draft={draft}
        presets={[PEROVSKITE_PRESET, NIOX_PRESET]}
        materials={[]}
        onChange={setDraft}
        onError={vi.fn()}
      />
    );
  }

  it("renders the drag handle only on layers with an adjacent same-type neighbor", () => {
    render(<SingleNioxHarness />);
    const cards = screen.getAllByRole("article");
    expect(within(cards[0]).queryByTitle("Drag to reorder")).not.toBeInTheDocument();
  });

  it("renders the handle on every layer of a same-type run", () => {
    render(<TwoNioxHarness />);
    const cards = screen.getAllByRole("article");
    expect(within(cards[0]).getByTitle("Drag to reorder")).toBeInTheDocument();
    expect(within(cards[1]).getByTitle("Drag to reorder")).toBeInTheDocument();
  });

  it("marks a legal target during drag-over and clears the marker after the drop", () => {
    render(<TwoNioxHarness />);
    const cards = screen.getAllByRole("article");

    fireEvent.dragStart(within(cards[0]).getByTitle("Drag to reorder"));
    fireEvent.dragOver(cards[1]);
    expect(cards[1].className).toContain("builder-layer-card--drop-after");

    fireEvent.drop(cards[1]);
    const reordered = screen.getAllByRole("article");
    expect(within(reordered[0]).getByText("Second NiOx")).toBeInTheDocument();
    expect(reordered[0].className).not.toContain("builder-layer-card--drop");
  });

  it("does not mark or reorder when the drop crosses a material boundary", () => {
    render(<NioxPairThenPerovskiteHarness />);
    const cards = screen.getAllByRole("article");
    expect(within(cards[0]).getByText("NiOx HTL")).toBeInTheDocument();

    // Drag the first NiOx onto the perovskite card: not a legal reorder.
    fireEvent.dragStart(within(cards[0]).getByTitle("Drag to reorder"));
    fireEvent.dragOver(cards[2]);
    expect(cards[2].className).not.toContain("builder-layer-card--drop");
    fireEvent.drop(cards[2]);

    const unchanged = screen.getAllByRole("article");
    expect(within(unchanged[0]).getByText("NiOx HTL")).toBeInTheDocument();
    expect(within(unchanged[2]).getByText("Perovskite stock")).toBeInTheDocument();
  });

  it("advertises the dragged layer via the data transfer for cross-browser drags", () => {
    render(<TwoNioxHarness />);
    const cards = screen.getAllByRole("article");
    const setData = vi.fn();
    fireEvent.dragStart(within(cards[0]).getByTitle("Drag to reorder"), {
      dataTransfer: { effectAllowed: "", setData, setDragImage: vi.fn() } as unknown as DataTransfer,
    });
    expect(setData).toHaveBeenCalledWith("text/plain", "0");
  });
});