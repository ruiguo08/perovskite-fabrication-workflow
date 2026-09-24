import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../components/Toast";
import { LayerPresetsPage } from "./LayerPresetsPage";

const apiFetchMock = vi.hoisted(() => vi.fn());
const sessionState = vi.hoisted(() => ({
  role: "student" as "student" | "instructor" | "administrator",
}));

vi.mock("../lib/api", () => ({ apiFetch: apiFetchMock }));
vi.mock("../auth/session", () => ({
  useSession: () => ({
    user: { id: 2, username: "preset-user", display_name: "Preset User", role: sessionState.role, csrf_available: true },
  }),
}));

const layer = {
  layer_type: "sam",
  role: "htl",
  name: "2PACz",
  preset_id: "sam_spin_v1",
  solution: {
    formulation_type: "weighed_solids",
    stock_dispersion: "",
    stock_volume_ml: null,
    solids: [{ chemical: "2PACz", weight_mg: 1 }],
    solvents: [{ solvent: "ethanol", volume_ml: 1 }],
  },
  process: {
    method: "spin_coating",
    spin_steps: [{ rpm: 3000, seconds: 30, acceleration_rpm_per_s: 1000 }],
    anneal_steps: [{ temperature_c: 100, seconds: 600 }],
  },
};

const sharedPreset = {
  id: 31,
  preset_key: "sam_spin_v1",
  name: "Shared SAM",
  status: "active",
  scope: "shared",
  layer,
  deposition_process: null,
  current_revision_number: 1,
  current_version_id: 41,
  canonical_hash: "a".repeat(64),
  created_at: "2026-08-01T08:00:00Z",
  updated_at: "2026-08-01T08:00:00Z",
};

const personalPreset = {
  ...sharedPreset,
  id: 32,
  preset_key: "personal-preset-version:42",
  name: "My SAM",
  scope: "personal",
  current_version_id: 42,
  canonical_hash: "b".repeat(64),
};

function renderPage() {
  return render(<ToastProvider><LayerPresetsPage /></ToastProvider>);
}

describe("LayerPresetsPage", () => {
  beforeEach(() => {
    sessionState.role = "student";
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue([sharedPreset, personalPreset]);
  });

  it("lets a student clone a complete snapshot into a personal preset", async () => {
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/layer-presets" && options?.method === "POST") {
        return Promise.resolve({ ...personalPreset, id: 33, name: "My optimized SAM" });
      }
      return Promise.resolve([sharedPreset, personalPreset]);
    });
    renderPage();

    await screen.findByText("Shared SAM");
    const sharedCard = screen.getByRole("article", { name: "Shared SAM" });
    const personalCard = screen.getByRole("article", { name: "My SAM" });
    expect(within(sharedCard).queryByText("Edit preset")).not.toBeInTheDocument();
    expect(within(sharedCard).queryByRole("button", { name: /deactivate/i })).not.toBeInTheDocument();
    expect(within(personalCard).getByText("Edit preset")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/^New preset name/), { target: { value: "My optimized SAM" } });
    fireEvent.change(screen.getByLabelText(/^Source preset/), { target: { value: "31" } });
    const cloneSection = screen.getByRole("region", { name: "Create from saved snapshot" });
    fireEvent.click(within(cloneSection).getByRole("button", { name: "Create personal preset" }));

    expect(await screen.findByText("My optimized SAM")).toBeInTheDocument();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/layer-presets", {
      method: "POST",
      body: { name: "My optimized SAM", layer, deposition_process: null, scope: "personal" },
    });
  });

  it("lets a student create a personal preset from scratch without any saved snapshot", async () => {
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/layer-presets" && options?.method === "POST") {
        return Promise.resolve({ ...personalPreset, id: 34, name: "My first NiOx" });
      }
      return Promise.resolve([]);
    });
    renderPage();

    // The from-scratch form works even with an empty catalog.
    await screen.findByText("No shared presets are available.");
    const blankSection = screen.getByRole("region", { name: "Create from scratch" });
    fireEvent.change(within(blankSection).getByLabelText(/^Layer type/), { target: { value: "niox" } });
    fireEvent.change(within(blankSection).getByLabelText(/^Preset name/), { target: { value: "My first NiOx" } });
    // Layer name auto-fills from the chosen layer type definition.
    expect(within(blankSection).getByLabelText(/^Layer name/)).toHaveValue("NiOx");

    // Solution and process may stay empty on a non-perovskite preset.
    fireEvent.click(within(blankSection).getByRole("button", { name: "Create personal preset" }));

    await waitFor(() => {
      const call = apiFetchMock.mock.calls.find(
        (c) => c[0] === "/api/layer-presets" && (c[1] as { method?: string })?.method === "POST",
      );
      const body = (call?.[1] as { body?: { layer?: unknown; deposition_process?: unknown; scope?: string } })?.body;
      expect(body).toEqual({
        name: "My first NiOx",
        layer: {
          layer_type: "niox",
          role: "htl",
          name: "NiOx",
          preset_id: null,
          solution: null,
          process: null,
        },
        deposition_process: null,
        scope: "personal",
      });
    });
    expect(await screen.findByText("Layer preset created from scratch.")).toBeInTheDocument();
  });

  it("blocks a perovskite preset from scratch until the deposition process is complete", async () => {
    apiFetchMock.mockResolvedValue([]);
    renderPage();

    await screen.findByText("No shared presets are available.");
    fireEvent.change(screen.getByLabelText(/^Layer type/), { target: { value: "perovskite" } });
    fireEvent.change(screen.getByLabelText(/^Preset name/), { target: { value: "PV preset" } });
    expect(screen.getByLabelText(/^Layer name/)).toHaveValue("Perovskite");

    // The perovskite editor demands complete spin/VCD/anneal stages; the
    // submit button stays locked until the issues are resolved.
    const blankSection = screen.getByRole("region", { name: "Create from scratch" });
    const submit = within(blankSection).getByRole("button", { name: "Create personal preset" });
    expect(submit).toBeDisabled();
    expect(await screen.findByText("Complete these values before saving")).toBeInTheDocument();

    expect(apiFetchMock).not.toHaveBeenCalledWith("/api/layer-presets", {
      method: "POST",
      body: expect.anything(),
    });
  });

  it("creates a perovskite preset from scratch once every deposition stage is complete", async () => {
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/layer-presets" && options?.method === "POST") {
        return Promise.resolve({ ...personalPreset, id: 35, name: "PV from scratch" });
      }
      return Promise.resolve([]);
    });
    renderPage();

    await screen.findByText("No shared presets are available.");
    const blankSection = screen.getByRole("region", { name: "Create from scratch" });
    fireEvent.change(within(blankSection).getByLabelText(/^Layer type/), { target: { value: "perovskite" } });
    fireEvent.change(within(blankSection).getByLabelText(/^Preset name/), { target: { value: "PV from scratch" } });

    // The perovskite editor starts fully blank: add one spin stage and one
    // evacuation row, then fill each field by its label.
    fireEvent.click(within(blankSection).getByRole("button", { name: "Add spin stage" }));
    fireEvent.click(within(blankSection).getByRole("button", { name: "Add stage" }));
    fireEvent.change(within(blankSection).getByLabelText("Stage 1 speed (rpm)"), { target: { value: "1000" } });
    fireEvent.change(within(blankSection).getAllByLabelText("Duration (s)")[0], { target: { value: "10" } });
    fireEvent.change(within(blankSection).getByLabelText("Acceleration (rpm/s)"), { target: { value: "100" } });

    // One complete evacuation row: valve, pressure (Pa), and the row's own
    // Duration (s) — the last Duration field in the section.
    fireEvent.change(within(blankSection).getByLabelText("Valve"), { target: { value: "VV02" } });
    fireEvent.change(within(blankSection).getByLabelText("Pressure (Pa)"), { target: { value: "900" } });
    const durationFields = within(blankSection).getAllByLabelText("Duration (s)");
    fireEvent.change(durationFields[durationFields.length - 1], { target: { value: "10" } });

    fireEvent.click(within(blankSection).getByRole("button", { name: "Add annealing stage" }));
    fireEvent.change(within(blankSection).getByLabelText("Stage 1 temperature (°C)"), { target: { value: "100" } });
    const annealDurations = within(blankSection).getAllByLabelText("Duration (s)");
    fireEvent.change(annealDurations[annealDurations.length - 1], { target: { value: "60" } });

    const submit = within(blankSection).getByRole("button", { name: "Create personal preset" });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);

    await waitFor(() => {
      const call = apiFetchMock.mock.calls.find(
        (c) => c[0] === "/api/layer-presets" && (c[1] as { method?: string })?.method === "POST",
      );
      const body = (call?.[1] as { body?: { name?: string; layer?: { layer_type?: string }; deposition_process?: { spin_steps?: unknown[]; vcd_stages?: { valve: string; pressure_pa: number; seconds: number }[]; vcd_step_sequence?: string[]; anneal_steps?: unknown[] } } })?.body;
      expect(body?.name).toBe("PV from scratch");
      expect(body?.layer?.layer_type).toBe("perovskite");
      expect(body?.deposition_process?.spin_steps).toHaveLength(1);
      expect(body?.deposition_process?.vcd_stages).toEqual([
        { valve: "VV02", pressure_pa: 900, seconds: 10 },
      ]);
      expect(body?.deposition_process?.vcd_step_sequence).toEqual(["vcd_stage1"]);
      expect(body?.deposition_process?.anneal_steps).toHaveLength(1);
    });
    expect(await screen.findByText("Layer preset created from scratch.")).toBeInTheDocument();
  });

  it("shows the student's own pending chemicals in the solution editor options", async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === "/api/materials") {
        return Promise.resolve([
          { id: 1, category: "chemical", name: "Active FAI", formula: "", cas_number: "", specification: {}, status: "active", products: [], created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z" },
          { id: 2, category: "chemical", name: "My pending EDADI", formula: "", cas_number: "", specification: {}, status: "pending", products: [], created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z" },
        ]);
      }
      return Promise.resolve([personalPreset]);
    });
    renderPage();

    const card = await screen.findByRole("article", { name: "My SAM" });
    fireEvent.click(within(card).getByText("Edit preset"));

    // The datalist renders once the editor opens; both the active catalog
    // chemical and the student's own pending proposal are offered.
    await within(card).findByLabelText("Chemical 1");
    const chemicalDatalist = document.getElementById("preset-32-chemical-options");
    expect(chemicalDatalist).not.toBeNull();
    const offered = Array.from(chemicalDatalist!.querySelectorAll("option")).map((option) => option.getAttribute("value"));
    expect(offered).toContain("Active FAI");
    expect(offered).toContain("My pending EDADI");
  });

  it("loads immutable version history with provenance", async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === "/api/layer-presets/32/versions") {
        return Promise.resolve([{
          id: 51,
          layer_preset_id: 32,
          revision_number: 1,
          preset_schema_version: 1,
          layer,
          deposition_process: null,
          canonical_hash: "b".repeat(64),
          created_by_id: 2,
          created_at: "2026-08-01T08:00:00Z",
        }]);
      }
      return Promise.resolve([sharedPreset, personalPreset]);
    });
    renderPage();

    const card = await screen.findByRole("article", { name: "My SAM" });
    fireEvent.click(within(card).getByText("Version history"));

    expect(await within(card).findByText("Revision 1")).toBeInTheDocument();
    expect(within(card).getByText(/schema 1/i)).toBeInTheDocument();
    expect(within(card).getByText(/actor 2/i)).toBeInTheDocument();
    expect(within(card).getByText(/^bbbbbbbbbbbb/, { selector: ".version-list__hash" })).toBeInTheDocument();
  });

  it("shows promotion failures on promote-only student cards", async () => {
    sessionState.role = "instructor";
    const studentPreset = {
      id: 77,
      preset_key: "student-sam",
      name: "Student SAM",
      status: "active",
      scope: "personal",
      layer,
      deposition_process: null,
      current_revision_number: 1,
      current_version_id: 771,
      canonical_hash: "c".repeat(64),
      created_at: "2026-09-01T08:00:00Z",
      updated_at: "2026-09-01T08:00:00Z",
    };
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/layer-presets?promotable=true") {
        return Promise.resolve([studentPreset]);
      }
      if (path === "/api/layer-presets/77/promote" && options?.method === "POST") {
        return Promise.reject(
          new Error("a shared layer preset named 'Shared SAM' already exists"),
        );
      }
      return Promise.resolve([sharedPreset]);
    });
    renderPage();

    const card = await screen.findByRole("article", { name: "Student SAM" });
    fireEvent.click(within(card).getByRole("button", { name: /promote student sam to shared/i }));
    fireEvent.click(screen.getByRole("button", { name: "Promote to shared" }));

    expect(
      await screen.findByText(/a shared layer preset named 'Shared SAM' already exists/i),
    ).toBeInTheDocument();
  });

  it("lets staff manage shared presets", async () => {
    sessionState.role = "instructor";
    apiFetchMock.mockImplementation((path: string) => {
      if (path === "/api/layer-presets?promotable=true") return Promise.resolve([]);
      return Promise.resolve([sharedPreset]);
    });
    renderPage();

    const card = await screen.findByRole("article", { name: "Shared SAM" });
    expect(within(card).getByText("Edit preset")).toBeInTheDocument();
    fireEvent.click(within(card).getByRole("button", { name: "Deactivate Shared SAM" }));
    fireEvent.click(screen.getByRole("button", { name: "Deactivate preset" }));

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/api/layer-presets/31", { method: "DELETE" }));
  });

  it("lets a student add a second solid ingredient via the structured editor and save a revision", async () => {
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/layer-presets/32" && options?.method === "PUT") {
        return Promise.resolve({ ...personalPreset, current_revision_number: 2 });
      }
      return Promise.resolve([sharedPreset, personalPreset]);
    });
    renderPage();

    const card = await screen.findByRole("article", { name: "My SAM" });
    fireEvent.click(within(card).getByText("Edit preset"));

    await waitFor(() => expect(within(card).getByLabelText("Chemical 1")).toHaveValue("2PACz"));
    fireEvent.click(within(card).getByRole("button", { name: "Add solid" }));

    fireEvent.change(await within(card).findByLabelText("Chemical 2"), { target: { value: "EDADI" } });
    fireEvent.change(within(card).getAllByLabelText(/Weight \(mg\)/)[1], { target: { value: "2.5" } });

    fireEvent.click(within(card).getByRole("button", { name: "Save new revision" }));

    await waitFor(() => {
      const call = apiFetchMock.mock.calls.find(
        (c) => c[0] === "/api/layer-presets/32" && (c[1] as { method?: string })?.method === "PUT",
      );
      const layer = (call?.[1] as { body?: { layer?: { solution?: { solids?: unknown[] } } } })?.body?.layer;
      expect(layer?.solution?.solids).toEqual([
        { chemical: "2PACz", weight_mg: 1 },
        { chemical: "EDADI", weight_mg: 2.5 },
      ]);
    });
    expect(await screen.findByText("A new immutable preset revision was saved.")).toBeInTheDocument();
  });
});
