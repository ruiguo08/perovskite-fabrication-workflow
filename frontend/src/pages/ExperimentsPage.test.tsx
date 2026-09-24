import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ExperimentsPage } from "./ExperimentsPage";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", () => ({ apiFetch: apiFetchMock }));

const deviceRecipe = {
  schema_version: 2,
  junction_type: "single_junction",
  perovskite_bandgap: "normal_bandgap",
  setup_mode: "baseline",
  experimental_groups: [],
  substrate: { material: "ITO", vendor: "Ossila", type_number: "S111", width_mm: 15, length_mm: 15 },
  layers: [{ layer_type: "perovskite", role: "perovskite", name: "Perovskite", preset_id: null, solution: null, process: null }],
};

const experiments = [
  {
    id: 1,
    recipe: { device_recipe: deviceRecipe },
    status: "completed",
    metrics: { pce: 22.1 },
    failure_reason: null,
    created_at: "2026-08-01T08:00:00Z",
    updated_at: "2026-08-03T08:00:00Z",
    campaign_id: "interface-2026",
    experiment_code: "interface-2026-v1",
    series_version: 1,
    plan_type: "comparative",
    plan_status: "completed",
  },
  {
    id: 2,
    recipe: { device_recipe: deviceRecipe },
    status: "planned",
    metrics: {},
    failure_reason: null,
    created_at: "2026-08-02T08:00:00Z",
    updated_at: "2026-08-04T08:00:00Z",
    campaign_id: "stability-2026",
    experiment_code: "stability-2026-v2",
    series_version: 2,
    plan_type: "standalone",
    plan_status: "draft",
  },
];

describe("ExperimentsPage", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue(experiments);
  });

  it("renders authorized API rows as React detail links", async () => {
    render(<MemoryRouter><ExperimentsPage /></MemoryRouter>);

    const recent = await screen.findByRole("link", { name: "stability-2026-v2" });
    expect(recent).toHaveAttribute("href", "/experiments/2");
    expect(screen.getByRole("link", { name: "interface-2026-v1" })).toHaveAttribute("href", "/experiments/1");
    expect(screen.getByRole("link", { name: "Plan new experiment" })).toHaveAttribute("href", "/experiments/new");
  });

  it("filters only the already authorized rows by Campaign, status, and text", async () => {
    render(<MemoryRouter><ExperimentsPage /></MemoryRouter>);
    await screen.findByText("stability-2026-v2");

    fireEvent.change(screen.getByLabelText("Campaign"), { target: { value: "interface-2026" } });
    expect(screen.getByText("interface-2026-v1")).toBeInTheDocument();
    expect(screen.queryByText("stability-2026-v2")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Campaign"), { target: { value: "all" } });
    fireEvent.change(screen.getByLabelText("Plan status"), { target: { value: "draft" } });
    expect(screen.getByText("stability-2026-v2")).toBeInTheDocument();
    expect(screen.queryByText("interface-2026-v1")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Plan status"), { target: { value: "all" } });
    fireEvent.change(screen.getByLabelText("Search experiments"), { target: { value: "interface" } });
    const table = screen.getByRole("table", { name: "Experiment records" });
    expect(within(table).getByText("interface-2026-v1")).toBeInTheDocument();
    expect(within(table).queryByText("stability-2026-v2")).not.toBeInTheDocument();
  });
});
