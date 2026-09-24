import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../components/Toast";
import { BaselinesPage } from "./BaselinesPage";

const apiFetchMock = vi.hoisted(() => vi.fn());
const sessionState = vi.hoisted(() => ({
  id: 2,
  role: "student" as "student" | "instructor" | "administrator",
}));

vi.mock("../lib/api", () => ({ apiFetch: apiFetchMock }));
vi.mock("../auth/session", () => ({
  useSession: () => ({
    user: { id: sessionState.id, username: "baseline-user", display_name: "Baseline User", role: sessionState.role, csrf_available: true },
  }),
}));

const depositionProcess = {
  method: "spin_coating_vcd",
  spin_steps: [{ rpm: 3000, seconds: 30, acceleration_rpm_per_s: 1000 }],
  vcd_stages: [{ valve: "VV02", pressure_pa: 1000, seconds: 5 }],
  gas_backfill_stages: [],
  vcd_step_sequence: ["vcd_stage1"],
  anneal_steps: [{ temperature_c: 100, seconds: 1800 }],
};

const perovskiteLayer = {
  layer_type: "perovskite",
  role: "perovskite",
  name: "Perovskite",
  preset_id: null,
  solution: {
    formulation_type: "stock_solution",
    stock_solution: "Perovskite stock solution",
    solids: [{ chemical: "FAI", weight_mg: 200 }],
    solvents: [{ solvent: "DMF", volume_ml: 1 }],
  },
  process: null,
};

const deviceRecipe = {
  schema_version: 2,
  junction_type: "single_junction",
  perovskite_bandgap: "normal_bandgap",
  setup_mode: "baseline",
  experimental_groups: [],
  substrate: { material: "ITO", vendor: "Ossila", type_number: "S111", width_mm: 15, length_mm: 15 },
  layers: [perovskiteLayer],
};

function baseline(id: number, name: string, extra: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    id,
    name,
    status: "active",
    scope: "shared",
    owner_user_id: null,
    owner_display_name: null,
    promoted_by_user_id: null,
    promoted_by_display_name: null,
    promoted_at: null,
    promotion_note: null,
    promoted_version_id: null,
    device_recipe: deviceRecipe,
    deposition_process: depositionProcess,
    current_revision_number: 1,
    current_version_id: id + 10,
    canonical_hash: "c".repeat(64),
    created_at: "2026-08-01T08:00:00Z",
    updated_at: "2026-08-01T08:00:00Z",
    ...extra,
  };
}

const perovskitePreset = {
  id: 41,
  preset_key: "perovskite-stock-v1",
  name: "Perovskite stock",
  status: "active",
  scope: "shared",
  layer: perovskiteLayer,
  deposition_process: depositionProcess,
  current_revision_number: 1,
  current_version_id: 51,
  canonical_hash: "c".repeat(64),
  created_at: "2026-08-01T08:00:00Z",
  updated_at: "2026-08-01T08:00:00Z",
};

const substrateMaterial = {
  id: 1,
  category: "substrate",
  name: "ITO",
  formula: "",
  cas_number: "",
  specification: {},
  status: "active",
  products: [{ id: 11, vendor: "Ossila", catalog_number: "S111", specification: {}, status: "active", created_at: "2026-08-01T08:00:00Z", updated_at: "2026-08-01T08:00:00Z" }],
  created_at: "2026-08-01T08:00:00Z",
  updated_at: "2026-08-01T08:00:00Z",
};

const layout = { code: "15x15-6", version: 1, substrate_width_mm: "15", substrate_length_mm: "15", devices_per_substrate: 6, device_active_area_cm2: "0.09", total_active_area_cm2: "0.54", description: "15 mm square · six devices" };

function renderPage() {
  return render(<ToastProvider><BaselinesPage /></ToastProvider>);
}

async function fillAuthoringWorkspace() {
  fireEvent.change(screen.getByLabelText(/^New baseline name/), { target: { value: "First reference" } });
  fireEvent.change(screen.getByLabelText(/^Substrate material/), { target: { value: "ITO" } });
  fireEvent.change(screen.getByLabelText(/^Supplier product/), { target: { value: "11" } });
  fireEvent.change(screen.getByLabelText(/^Device layout/), { target: { value: "15x15-6" } });
  fireEvent.change(screen.getByLabelText("Layer preset"), { target: { value: "41" } });
  fireEvent.click(screen.getByRole("button", { name: "Add copied preset" }));
}

function mockCatalogPaths() {
  apiFetchMock.mockImplementation((path: string) => {
    if (path === "/api/layer-presets") {
      return Promise.resolve([perovskitePreset]);
    }
    if (path === "/api/materials") {
      return Promise.resolve([substrateMaterial]);
    }
    if (path === "/api/device-layouts") {
      return Promise.resolve([layout]);
    }
    return Promise.resolve([]);
  });
}

describe("BaselinesPage", () => {
  beforeEach(() => {
    sessionState.role = "student";
    sessionState.id = 2;
    apiFetchMock.mockReset();
    mockCatalogPaths();
  });

  it("lets a student create the first Personal baseline from an empty directory", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Create baseline" })).toBeInTheDocument();
    expect(await screen.findByLabelText(/^Baseline scope/)).toHaveValue("Personal (visible only to you)");
    expect(screen.getByRole("button", { name: "Save personal baseline" })).toBeDisabled();

    await fillAuthoringWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Save personal baseline" }));

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/api/baselines", {
      method: "POST",
      body: {
        name: "First reference",
        device_recipe: expect.objectContaining({ schema_version: 2, setup_mode: "baseline", layers: [{ ...perovskiteLayer, preset_id: "perovskite-stock-v1" }] }),
        deposition_process: depositionProcess,
      },
    }));
    expect(apiFetchMock).not.toHaveBeenCalledWith("/api/baselines", expect.objectContaining({ "method": "POST", "body": expect.objectContaining({ "scope": expect.anything() }) }));
  });

  it("shows the new Personal baseline in the Personal group with its owner", async () => {
    sessionState.id = 7;
    apiFetchMock.mockImplementation((path: string) => {
      if (path === "/api/baselines") {
        return Promise.resolve([
          baseline(61, "Shared reference"),
          baseline(62, "My reference", { scope: "personal", owner_user_id: 7, owner_display_name: "Baseline User" }),
        ]);
      }
      return Promise.resolve([]);
    });
    renderPage();

    const personalGroupHeading = await screen.findByRole("heading", { name: "Personal baselines" });
    const card = await screen.findByRole("article", { name: "My reference" });

    expect(personalGroupHeading).toBeInTheDocument();
    expect(within(card).getByText("personal")).toBeInTheDocument();
    expect(within(card).getByText(/Owned by You/)).toBeInTheDocument();
    expect(within(card).queryByText("Promote to shared")).not.toBeInTheDocument();
  });

  it("lets an instructor create a Shared baseline and promote a Personal baseline", async () => {
    sessionState.role = "instructor";
    const personal = baseline(80, "Student work", { scope: "personal", owner_user_id: 7, owner_display_name: "Student A" });
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/layer-presets") {
        return Promise.resolve([perovskitePreset]);
      }
      if (path === "/api/materials") {
        return Promise.resolve([substrateMaterial]);
      }
      if (path === "/api/device-layouts") {
        return Promise.resolve([layout]);
      }
      if (path === "/api/baselines" && options?.method === "POST") {
        return Promise.resolve(baseline(81, "Staff shared"));
      }
      if (path === "/api/baselines/80/promote" && options?.method === "POST") {
        return Promise.resolve(baseline(80, "Student work", {
          scope: "shared",
          owner_user_id: 7,
          owner_display_name: "Student A",
          promoted_by_user_id: 2,
          promoted_by_display_name: "Baseline User",
          promoted_at: "2026-08-02T08:00:00Z",
          promotion_note: "Promoted reference",
        }));
      }
      if (path === "/api/baselines/80/versions") {
        return Promise.resolve([]);
      }
      return Promise.resolve([personal]);
    });
    renderPage();

    expect(await screen.findByLabelText(/^Baseline scope/)).toHaveValue("Shared (lab-wide starting point)");
    expect(screen.getByRole("button", { name: "Save shared baseline" })).toBeDisabled();
    await fillAuthoringWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Save shared baseline" }));
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/api/baselines", {
      method: "POST",
      body: expect.objectContaining({ name: "First reference" }),
    }));

    const personalCard = await screen.findByRole("article", { name: "Student work" });
    expect(within(personalCard).getByText(/Owned by Student A/)).toBeInTheDocument();
    fireEvent.click(within(personalCard).getByText("Promote to shared"));
    fireEvent.change(within(personalCard).getByLabelText(/Promotion note for Student work/), { target: { value: "Promoted reference" } });
    fireEvent.click(within(personalCard).getByRole("button", { name: "Promote Student work to shared" }));

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/api/baselines/80/promote", {
      method: "POST",
      body: { note: "Promoted reference" },
    }));
    const promotedCard = await screen.findByRole("article", { name: "Student work" });
    expect(await within(promotedCard).findByText(/Promoted by Baseline User/)).toBeInTheDocument();
  });

  it("keeps version history available on shared baselines", async () => {
    sessionState.role = "student";
    apiFetchMock.mockImplementation((path: string) => {
      if (path === "/api/baselines/61/versions") {
        return Promise.resolve([{
          id: 71,
          baseline_id: 61,
          revision_number: 1,
          recipe_schema_version: 2,
          device_recipe: deviceRecipe,
          deposition_process: depositionProcess,
          canonical_hash: "c".repeat(64),
          change_note: "Initial revision",
          created_by_id: 1,
          created_at: "2026-08-01T08:00:00Z",
        }]);
      }
      if (path === "/api/baselines") {
        return Promise.resolve([baseline(61, "Shared reference")]);
      }
      return Promise.resolve([]);
    });
    renderPage();

    const card = await screen.findByRole("article", { name: "Shared reference" });
    expect(within(card).getByText("shared")).toBeInTheDocument();
    expect(within(card).getByText(/Shared · created directly by staff/)).toBeInTheDocument();
    fireEvent.click(within(card).getByText("Version history"));
    expect(await within(card).findByText("Revision 1")).toBeInTheDocument();
  });
});