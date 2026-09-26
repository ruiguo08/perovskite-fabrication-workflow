import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../components/Toast";
import { ExperimentBuilderPage } from "./ExperimentBuilderPage";

const apiFetchMock = vi.hoisted(() => vi.fn());
const sessionState = vi.hoisted(() => ({
  role: "student" as "student" | "instructor" | "administrator",
}));

vi.mock("../lib/api", () => ({ apiFetch: apiFetchMock }));
vi.mock("../auth/session", () => ({
  useSession: () => ({
    user: {
      id: 7,
      username: "planner",
      display_name: "Planner",
      role: sessionState.role,
      csrf_available: true,
    },
  }),
}));

const process = {
  method: "spin_coating_vcd" as const,
  spin_steps: [{ rpm: 3000, seconds: 30, acceleration_rpm_per_s: 1000 }],
  vcd_stages: [{ valve: "VV02", pressure_pa: 1000, seconds: 5 }],
  gas_backfill_stages: [],
  vcd_step_sequence: ["vcd_stage1"],
  anneal_steps: [{ temperature_c: 100, seconds: 1800 }],
};

const layers = [
  { layer_type: "niox", role: "htl", name: "NiOx", preset_id: "niox-spin", solution: { formulation_type: "weighed_solids" as const, stock_dispersion: "", stock_volume_ml: null, solids: [{ chemical: "NiOx", weight_mg: 10 }], solvents: [{ solvent: "IPA", volume_ml: 1 }] }, process: { method: "spin_coating", spin_steps: [{ rpm: 4000, seconds: 30, acceleration_rpm_per_s: 2000 }], anneal_steps: [] } },
  { layer_type: "perovskite", role: "perovskite", name: "Perovskite", preset_id: "pvk", solution: { formulation_type: "weighed_solids" as const, stock_dispersion: "", stock_volume_ml: null, solids: [{ chemical: "PbI2", weight_mg: 461 }], solvents: [{ solvent: "DMF", volume_ml: 1 }] }, process: null },
  { layer_type: "c60", role: "etl", name: "C60", preset_id: "c60", solution: null, process: { method: "thermal_evaporation", thickness_nm: 20, rate_angstrom_per_s: 0.2 } },
  { layer_type: "sno2", role: "etl", name: "SnO2", preset_id: "sno2", solution: null, process: { method: "ald", thickness_nm: 20, substrate_temperature_c: 80, cycles: 100 } },
  { layer_type: "ag", role: "top_electrode", name: "Ag", preset_id: "ag", solution: null, process: { method: "thermal_evaporation", thickness_nm: 100, rate_angstrom_per_s: 1 } },
];

const baseline = {
  id: 1,
  name: "Reference baseline",
  status: "active",
  scope: "shared",
  owner_user_id: null,
  owner_display_name: null,
  promoted_by_user_id: null,
  promoted_by_display_name: null,
  promoted_at: null,
  promotion_note: null,
  promoted_version_id: null,
  device_recipe: {
    schema_version: 2,
    setup_mode: "baseline",
    junction_type: "single_junction",
    perovskite_bandgap: "normal_bandgap",
    experimental_groups: [
      { group_id: "control", kind: "control", name: "Control", change_from_control: "Baseline fabrication procedure", inherits_control: false, adjustments: [], substrate_count: 3 },
      { group_id: "target-1", kind: "target", name: "Target 1", change_from_control: "", inherits_control: true, adjustments: [], substrate_count: 3 },
    ],
    substrate: { material: "ITO glass", vendor: "Ossila", type_number: "S111", width_mm: 15, length_mm: 15 },
    layers,
  },
  deposition_process: process,
  current_revision_number: 2,
  current_version_id: 12,
  canonical_hash: "a".repeat(64),
  created_at: "2026-08-01T08:00:00Z",
  updated_at: "2026-08-01T08:00:00Z",
};

const campaign = { id: 2, code: "interface-2026", display_name: "Interface study", description: "", status: "active", created_at: "2026-08-01T08:00:00Z", updated_at: "2026-08-01T08:00:00Z", closed_at: null };
const layout = { code: "15x15-6", version: 1, substrate_width_mm: "15", substrate_length_mm: "15", devices_per_substrate: 6, device_active_area_cm2: "0.09", total_active_area_cm2: "0.54", description: "15 mm square · six devices" };
const materials = [{
  id: 1,
  category: "substrate",
  name: "ITO glass",
  formula: "",
  cas_number: "",
  specification: {},
  status: "active",
  products: [{ id: 2, vendor: "Ossila", catalog_number: "S111", specification: {}, status: "active", created_at: "2026-08-01T08:00:00Z", updated_at: "2026-08-01T08:00:00Z" }],
  created_at: "2026-08-01T08:00:00Z",
  updated_at: "2026-08-01T08:00:00Z",
}];

function responseFor(path: string, options?: { method?: string }) {
  if (path === "/api/campaigns") return Promise.resolve([campaign]);
  if (path === "/api/baselines") return Promise.resolve([baseline]);
  if (path === "/api/layer-presets") return Promise.resolve([]);
  if (path === "/api/materials") return Promise.resolve(materials);
  if (path === "/api/device-layouts") return Promise.resolve([layout]);
  if (path === "/api/editor-config") {
    return Promise.resolve({ vcd_valves: ["VV02", "VV03", "VV06", "Pudi"], max_solid_chemicals: 20, max_solvents: 10 });
  }
  if (path === "/api/experiments" && options?.method === "POST") {
    return Promise.resolve({ id: 42 });
  }
  return Promise.reject(new Error(`Unexpected API request: ${path}`));
}

function renderPage() {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={["/experiments/new"]}>
        <Routes>
          <Route path="/experiments/new" element={<ExperimentBuilderPage />} />
          <Route path="/experiments/:experimentId" element={<p>Saved experiment</p>} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>,
  );
}

describe("ExperimentBuilderPage", () => {
  beforeEach(() => {
    sessionState.role = "student";
    apiFetchMock.mockReset();
    apiFetchMock.mockImplementation(responseFor);
  });

  it("loads every reusable directory and lets students plan from scratch", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Plan experiment" })).toBeInTheDocument();
    expect(screen.getByText(/baseline reference \(optional shortcut\)/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /plan from scratch/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save experiment" })).toBeDisabled();
    expect(screen.getByText("Complete each step, then review the plan before saving.")).toBeInTheDocument();
    expect(screen.queryByText(/review items remain/)).not.toBeInTheDocument();
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(6));
    for (const path of ["/api/campaigns", "/api/baselines", "/api/layer-presets", "/api/materials", "/api/device-layouts", "/api/editor-config"]) {
      expect(apiFetchMock).toHaveBeenCalledWith(path);
    }
  });

  it("deep-expands the baseline, reviews the complete plan, and saves explicit condition layouts", async () => {
    renderPage();
    await screen.findByRole("option", { name: /Reference baseline/ });

    fireEvent.change(screen.getByLabelText(/^Campaign/), { target: { value: "interface-2026" } });
    fireEvent.change(screen.getByLabelText(/^Baseline reference/), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Review" }));

    expect(screen.getByText("Reference baseline · revision 2")).toBeInTheDocument();
    expect(screen.getByText(/ITO glass · Ossila · S111/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save experiment" }));

    expect(await screen.findByText("Saved experiment")).toBeInTheDocument();
    const post = apiFetchMock.mock.calls.find(([path, options]) => path === "/api/experiments" && options?.method === "POST");
    expect(post).toBeDefined();
    const payload = post![1].body;
    expect(payload.source_baseline_version_id).toBe(12);
    expect(payload.recipe.device_recipe.layers).toEqual(layers);
    expect(payload.recipe.device_recipe.experimental_groups[1].layers).toEqual(layers);
    expect(payload.recipe.device_recipe.experimental_groups[1]).not.toHaveProperty("device_layout_code");
    expect(payload.condition_plans).toEqual([
      { group_id: "control", role: "control", device_layout_code: "15x15-6", planned_substrate_count: 3 },
      { group_id: "target-1", role: "target", device_layout_code: "15x15-6", planned_substrate_count: 3 },
    ]);
  });

  it("lets instructors start from a blank editable plan", async () => {
    sessionState.role = "instructor";
    renderPage();

    expect(await screen.findByRole("button", { name: "Start blank" })).toBeInTheDocument();
  });
});

describe("ExperimentBuilderPage draft persistence", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/campaigns") return [{ code: "interface-2026", display_name: "Interface 2026", status: "active" }];
      if (path === "/api/baselines") return [];
      if (path === "/api/layer-presets") return [];
      if (path === "/api/materials") return [];
      if (path === "/api/device-layouts") return [{
        code: "15x15-6", description: "15x15 mm", substrate_width_mm: 15, substrate_length_mm: 15,
        devices_per_substrate: 2, device_active_area_cm2: 0.05, status: "active",
      }];
      return undefined;
    });
    window.localStorage.clear();
  });

  it("restores the campaign selection when the page is left and reopened", async () => {
    const { unmount } = renderPage();
    fireEvent.change(await screen.findByLabelText(/^Campaign/), { target: { value: "interface-2026" } });

    expect(window.localStorage.getItem("perovskite-bo:experiment-draft:7")).toContain("interface-2026");
    unmount();

    renderPage();
    expect(await screen.findByLabelText(/^Campaign/)).toHaveValue("interface-2026");
    expect(screen.getByRole("button", { name: /discard draft/i })).toBeInTheDocument();
  });

  it("hides the restoration banner once the student starts over from a baseline", async () => {
    window.localStorage.setItem(
      "perovskite-bo:experiment-draft:7",
      JSON.stringify({
        version: 1,
        draft: {
          campaign_id: "interface-2026",
          source_baseline_version_id: null,
          source_baseline_name: null,
          setup_mode: "blank",
          junction_type: "single_junction",
          perovskite_bandgap: "normal_bandgap",
          architecture: "pin",
          substrate: { material: "ITO", vendor: "", type_number: "", width_mm: 15, length_mm: 15 },
          layers: [],
          deposition_process: {
            method: "spin_coating_vcd",
            spin_steps: [], vcd_stages: [], gas_backfill_stages: [],
            vcd_step_sequence: [], anneal_steps: [],
          },
          plan_type: "standalone",
          conditions: [],
        },
      }),
    );

    renderPage();
    expect(await screen.findByRole("button", { name: /discard draft/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /start blank/i }));
    // Replacing a draft that holds content requires an explicit confirmation.
    fireEvent.click(await screen.findByRole("button", { name: /discard edits and replace/i }));

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /discard draft/i })).not.toBeInTheDocument();
    });
  });

  it("discards the restored draft and starts from a blank plan", async () => {
    window.localStorage.setItem(
      "perovskite-bo:experiment-draft:7",
      JSON.stringify({
        version: 1,
        draft: {
          campaign_id: "interface-2026",
          source_baseline_version_id: null,
          source_baseline_name: null,
          setup_mode: "blank",
          junction_type: "single_junction",
          perovskite_bandgap: "normal_bandgap",
          architecture: "pin",
          substrate: { material: "ITO", vendor: "", type_number: "", width_mm: 15, length_mm: 15 },
          layers: [],
          deposition_process: {
            method: "spin_coating_vcd",
            spin_steps: [], vcd_stages: [], gas_backfill_stages: [],
            vcd_step_sequence: [], anneal_steps: [],
          },
          plan_type: "standalone",
          conditions: [],
        },
      }),
    );

    renderPage();
    expect(await screen.findByLabelText(/^Campaign/)).toHaveValue("interface-2026");
    fireEvent.click(screen.getByRole("button", { name: /discard draft/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/^Campaign/)).toHaveValue("");
    });
    expect(window.localStorage.getItem("perovskite-bo:experiment-draft:7")).toBeNull();
  });
});
