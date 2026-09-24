import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../components/Toast";
import { ExperimentDetailPage } from "./ExperimentDetailPage";

const apiFetchMock = vi.hoisted(() => vi.fn());
const sessionState = vi.hoisted(() => ({
  role: "student" as "student" | "instructor" | "administrator",
}));
vi.mock("../lib/api", () => ({ apiFetch: apiFetchMock }));
vi.mock("../auth/session", () => ({
  useSession: () => ({ user: { id: 2, username: "plan-user", display_name: "Plan User", role: sessionState.role, csrf_available: true } }),
}));

const layer = { layer_type: "perovskite", role: "perovskite", name: "Perovskite", preset_id: null, solution: null, process: null };
const substrate = { material: "ITO", vendor: "Ossila", type_number: "S111", width_mm: 15, length_mm: 15 };
const depositionProcess = {
  method: "spin_coating_vcd",
  spin_steps: [{ rpm: 3000, seconds: 30, acceleration_rpm_per_s: 1000 }],
  vcd_stages: [{ valve: "VV02", pressure_pa: 1000, seconds: 5 }],
  gas_backfill_stages: [],
  vcd_step_sequence: ["vcd_stage1"],
  anneal_steps: [{ temperature_c: 100, seconds: 1800 }],
};
const conditionSnapshot = {
  schema_version: 3,
  device: {
    schema_version: 2,
    setup_mode: "baseline",
    junction_type: "single_junction",
    perovskite_bandgap: "normal_bandgap",
    tandem_type: null,
    substrate,
    layers: [layer],
  },
  deposition_process: depositionProcess,
};
const experiment = {
  id: 7,
  recipe: {
    device_recipe: {
      schema_version: 2,
      junction_type: "single_junction",
      perovskite_bandgap: "normal_bandgap",
      setup_mode: "baseline",
      experimental_groups: [],
      substrate,
      layers: [layer],
    },
  },
  status: "planned",
  metrics: {},
  failure_reason: null,
  created_at: "2026-08-01T08:00:00Z",
  updated_at: "2026-08-02T08:00:00Z",
  campaign_id: "interface-2026",
  experiment_code: "interface-2026-v7",
  series_version: 7,
  plan_type: "comparative",
  plan_status: "draft",
};
const condition = {
  id: 81,
  experiment_id: 7,
  role: "control",
  condition_code: "interface-2026-v7-C",
  condition_name: "Control",
  recipe_snapshot: conditionSnapshot,
  recipe_schema_version: 3,
  canonical_hash: "d".repeat(64),
  source_baseline_version_id: 71,
  device_layout_code: "15x15-6",
  device_layout_snapshot: { code: "15x15-6", devices_per_substrate: 6 },
  planned_substrate_count: 2,
  expected_device_count: 12,
  requires_manual_review: false,
  created_at: "2026-08-01T08:00:00Z",
};
const pendingException = {
  id: 91,
  condition_id: 81,
  requested_count: 2,
  reason: "Limited conductive-glass inventory",
  requested_by_id: 2,
  requested_at: "2026-08-01T08:00:00Z",
  decision: "pending",
  decided_by_id: null,
  decided_at: null,
  decision_note: "",
  approved_condition_hash: null,
};

function detail(overrides: Record<string, unknown> = {}) {
  return {
    experiment: { ...experiment, ...overrides },
    conditions: [condition],
    substrate_exceptions: [],
    fabrication_batches: [],
    results: [],
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/experiments/7"]}>
      <ToastProvider>
        <Routes><Route path="/experiments/:experimentId" element={<ExperimentDetailPage />} /></Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
}

function NavigateButton({ to }: { to: string }) {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate(to)}>
      navigate-to
    </button>
  );
}

function renderNavigablePage() {
  return render(
    <MemoryRouter initialEntries={["/experiments/7"]}>
      <ToastProvider>
        <NavigateButton to="/experiments/8" />
        <Routes><Route path="/experiments/:experimentId" element={<ExperimentDetailPage />} /></Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe("ExperimentDetailPage", () => {
  beforeEach(() => {
    sessionState.role = "student";
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue(detail());
  });

  it("renders complete condition provenance and direct audit exports", async () => {
    renderPage();

    const card = await screen.findByRole("article", { name: "Control" });
    expect(within(card).getByText("interface-2026-v7-C")).toBeInTheDocument();
    expect(within(card).getByText("15x15-6")).toBeInTheDocument();
    expect(within(card).getByText("12 expected devices")).toBeInTheDocument();
    expect(within(card).getByText("Baseline version 71")).toBeInTheDocument();
    expect(within(card).getByText(/^dddddddddddd/)).toBeInTheDocument();
    expect(within(card).getByText(/"deposition_process"/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Export JSON" })).toHaveAttribute("href", "/experiments/7/export.json");
    expect(screen.getByRole("link", { name: "Export PDF" })).toHaveAttribute("href", "/experiments/7/export.pdf");
  });

  it("offers submit-for-approval, never direct release, for a normal-count draft", async () => {
    // A structurally complete draft (no low-count exception) must still go
    // through the strict approval workflow, not release directly.
    apiFetchMock.mockResolvedValue({
      ...detail(),
      conditions: [{ ...condition, planned_substrate_count: 3, expected_device_count: 18 }],
    });
    renderPage();

    const submit = await screen.findByRole("button", { name: "Submit for approval" });
    expect(submit).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Release plan" })).not.toBeInTheDocument();
  });

  it("lets a student request a required substrate exception", async () => {
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/conditions/81/substrate-exceptions" && options?.method === "POST") {
        return Promise.resolve(pendingException);
      }
      return Promise.resolve(detail());
    });
    renderPage();

    const card = await screen.findByRole("article", { name: "Control" });
    fireEvent.change(within(card).getByLabelText(/^Exception reason for Control/), { target: { value: "Limited conductive-glass inventory" } });
    fireEvent.click(within(card).getByRole("button", { name: "Request exception" }));

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/api/conditions/81/substrate-exceptions", {
      method: "POST",
      body: { requested_count: 2, reason: "Limited conductive-glass inventory" },
    }));
    expect(await within(card).findByText("Limited conductive-glass inventory")).toBeInTheDocument();
  });

  it("lets staff approve pending exceptions and then approve the plan", async () => {
    sessionState.role = "instructor";
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/substrate-exceptions/91/decision" && options?.method === "POST") {
        return Promise.resolve({ ...pendingException, decision: "approved", decided_by_id: 3, approved_condition_hash: condition.canonical_hash });
      }
      if (path === "/api/experiments/7/plan-status" && options?.method === "PATCH") {
        return Promise.resolve(undefined);
      }
      return Promise.resolve({ ...detail({ plan_status: "pending_approval" }), substrate_exceptions: [pendingException] });
    });
    renderPage();

    const card = await screen.findByRole("article", { name: "Control" });
    fireEvent.click(within(card).getByRole("button", { name: "Approve exception" }));
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/api/substrate-exceptions/91/decision", {
      method: "POST",
      body: { decision: "approved", decision_note: "" },
    }));
    fireEvent.click(screen.getByRole("button", { name: "Approve plan" }));
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/api/experiments/7/plan-status", {
      method: "PATCH",
      body: { status: "approved" },
    }));
  });

  it("creates a frozen batch only from a released plan", async () => {
    const released = detail({ plan_status: "released" });
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/experiments/7/fabrication-batches" && options?.method === "POST") {
        return Promise.resolve({
          id: 101,
          experiment_id: 7,
          batch_number: 1,
          batch_code: "interface-2026-v7-B01",
          status: "draft",
          condition_set_hash: "e".repeat(64),
          notes: "First fabrication run",
          created_by_id: 2,
          created_at: "2026-08-02T08:00:00Z",
          updated_at: "2026-08-02T08:00:00Z",
          started_at: null,
          completed_at: null,
          cancelled_at: null,
        });
      }
      return Promise.resolve(released);
    });
    renderPage();

    await screen.findByText("interface-2026-v7-C");
    fireEvent.change(screen.getByLabelText("Batch notes"), { target: { value: "First fabrication run" } });
    fireEvent.click(screen.getByRole("button", { name: "Freeze fabrication batch" }));

    expect(await screen.findByText("interface-2026-v7-B01")).toBeInTheDocument();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/experiments/7/fabrication-batches", {
      method: "POST",
      body: { notes: "First fabrication run" },
    });
  });

  it("never shows or mutates experiment A under route B when navigating without remount", async () => {
    let resolvePatch: ((value: unknown) => void) | null = null;
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/experiments/7/plan-status" && options?.method === "PATCH") {
        return new Promise((resolve) => {
          resolvePatch = resolve;
        });
      }
      if (path === "/api/experiments/7") {
        return Promise.resolve(detail());
      }
      if (path === "/api/experiments/8") {
        return Promise.resolve(
          detail({ id: 8, experiment_code: "interface-2026-v8" }),
        );
      }
      return Promise.resolve(undefined);
    });
    renderNavigablePage();

    await screen.findByText("interface-2026-v7");
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));

    // Navigate away while the plan-status PATCH is still in flight.
    fireEvent.click(screen.getByRole("button", { name: "navigate-to" }));
    await screen.findByText("interface-2026-v8");
    expect(screen.queryByText("interface-2026-v7")).not.toBeInTheDocument();

    // The stale mutation resolves late: it must neither write A's status
    // into B's page nor surface a success toast for the abandoned route.
    await act(async () => {
      resolvePatch?.(undefined);
    });
    expect(screen.getByText("interface-2026-v8")).toBeInTheDocument();
    expect(screen.queryByText(/plan status changed/i)).not.toBeInTheDocument();
  });
});
