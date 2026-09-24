import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../components/Toast";
import { BatchDetailPage } from "./BatchDetailPage";
import type { BatchRunSheet, Deviation, SolutionPreparation } from "../types/api";

const apiFetchMock = vi.hoisted(() => vi.fn());
const sessionState = vi.hoisted(() => ({
  role: "student" as "student" | "instructor" | "administrator",
}));
vi.mock("../lib/api", () => ({ apiFetch: apiFetchMock }));
vi.mock("../auth/session", () => ({
  useSession: () => ({ user: { id: 2, username: "run-sheet-user", display_name: "Run Sheet User", role: sessionState.role, csrf_available: true } }),
}));

const preparedSnapshot = {
  formulation_type: "weighed_solids",
  stock_dispersion: "",
  stock_volume_ml: null,
  solids: [{ chemical: "Me-4PACz", weight_mg: 2 }],
  solvents: [{ solvent: "Ethanol", volume_ml: 1 }],
};

function preparation(id: number, code: string, hash: string): SolutionPreparation {
  return {
    id,
    fabrication_batch_id: 5,
    preparation_code: code,
    status: "planned",
    planned_solution_snapshot: preparedSnapshot,
    planned_snapshot_schema_version: 1,
    planned_canonical_hash: hash,
    actual_solution_snapshot: null,
    actual_snapshot_schema_version: null,
    actual_canonical_hash: null,
    actual_recording_mode: null,
    prepared_by_id: null,
    prepared_at: null,
    completed_at: null,
    notes: "",
    created_at: "2026-08-01T08:00:00Z",
    updated_at: "2026-08-01T08:00:00Z",
  };
}

function makeRunSheet(): BatchRunSheet {
  return {
    batch: {
      id: 5,
      experiment_id: 7,
      batch_number: 1,
      batch_code: "interface-2026-v7-B01",
      status: "draft",
      condition_set_hash: "c".repeat(64),
      notes: "Frozen test batch",
      created_by_id: 2,
      created_at: "2026-08-01T08:00:00Z",
      updated_at: "2026-08-01T08:00:00Z",
      started_at: null,
      completed_at: null,
      cancelled_at: null,
    },
    conditions: [
      {
        id: 21,
        fabrication_batch_id: 5,
        source_condition_id: 11,
        condition_code: "interface-2026-v7-C",
        condition_name: "Control",
        role: "control",
        source_condition_hash: "d".repeat(64),
        recipe_snapshot: {},
        recipe_schema_version: 3,
        device_layout_code: "15x15_dual_005",
        device_layout_snapshot: {},
        planned_substrate_count: 3,
        expected_device_count: 6,
        actual_substrate_count: null,
      },
    ],
    substrates: [
      {
        id: 31,
        batch_condition_id: 21,
        substrate_ordinal: 1,
        substrate_code: "interface-2026-v7-B01-C-S01",
        substrate_mark: "C01",
        status: "planned",
        notes: "",
        created_at: "2026-08-01T08:00:00Z",
        updated_at: "2026-08-01T08:00:00Z",
      },
    ],
    devices: [
      {
        id: 41,
        substrate_id: 31,
        device_ordinal: 1,
        device_code: "interface-2026-v7-B01-C-S01-D01",
        device_mark: "C011",
        device_active_area_cm2: "0.045",
        status: "planned",
        notes: "",
        created_at: "2026-08-01T08:00:00Z",
        updated_at: "2026-08-01T08:00:00Z",
      },
    ],
    preparations: [
      {
        preparation: preparation(51, "interface-2026-v7-B01-P01", "e".repeat(64)),
        uses: [
          { id: 61, solution_preparation_id: 51, batch_condition_id: 21, layer_ordinal: 1, layer_role: "etl", layer_type: "sno2", layer_snapshot_hash: "f".repeat(64) },
          { id: 62, solution_preparation_id: 51, batch_condition_id: 21, layer_ordinal: 2, layer_role: "htl", layer_type: "sam", layer_snapshot_hash: "f".repeat(64) },
        ],
      },
    ],
    executions: [
      {
        execution: {
          id: 71,
          fabrication_batch_id: 5,
          execution_code: "interface-2026-v7-B01-E01",
          method: "thermal_evaporation",
          layer_role: "etl",
          layer_type: "c60",
          layer_name: "C60",
          status: "planned",
          is_shared: false,
          planned_process_snapshot: { method: "thermal_evaporation", thickness_nm: 20, rate_angstrom_per_s: 0.5 },
          planned_snapshot_schema_version: 1,
          planned_canonical_hash: "g".repeat(64),
          actual_process_snapshot: null,
          actual_snapshot_schema_version: null,
          actual_canonical_hash: null,
          actual_recording_mode: null,
          equipment_identifier: null,
          executed_by_id: null,
          started_at: null,
          completed_at: null,
          notes: "",
          created_at: "2026-08-01T08:00:00Z",
          updated_at: "2026-08-01T08:00:00Z",
        },
        members: [
          { id: 81, process_execution_id: 71, substrate_id: 31, batch_condition_id: 21, layer_ordinal: 1, layer_snapshot_hash: "h".repeat(64) },
        ],
      },
    ],
    deviations: [],
    editor_config: { vcd_valves: ["VV02"], max_solid_chemicals: 20, max_solvents: 10 },
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/experiments/7/batches/5"]}>
      <ToastProvider>
        <Routes>
          <Route path="/experiments/:experimentId/batches/:batchId" element={<BatchDetailPage />} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
}

async function renderReadySheet() {
  renderPage();
  await screen.findByText("Frozen conditions");
}

function preparationCard(): HTMLElement {
  const strong = screen.getAllByText("interface-2026-v7-B01-P01")[0];
  return strong.closest("article") as HTMLElement;
}

function recordingSelect(card: HTMLElement): HTMLSelectElement {
  const label = within(card).getByText("Actual recording").closest("label") as HTMLLabelElement;
  return label.querySelector("select") as HTMLSelectElement;
}

const runSheetMethod = (path: string, options?: { method?: string }): boolean | undefined => (options?.method ?? "GET") === "GET" && path === "/api/fabrication-batches/5/run-sheet";

function deferredRunSheet() {
  let resolve!: (value: BatchRunSheet) => void;
  const promise = new Promise<BatchRunSheet>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
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
    <MemoryRouter initialEntries={["/experiments/7/batches/5"]}>
      <ToastProvider>
        <NavigateButton to="/experiments/7/batches/99" />
        <Routes>
          <Route path="/experiments/:experimentId/batches/:batchId" element={<BatchDetailPage />} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe("BatchDetailPage", () => {
  beforeEach(() => {
    sessionState.role = "student";
    apiFetchMock.mockReset();
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        return makeRunSheet();
      }
      return undefined;
    });
  });

  it("renders the run sheet with frozen snapshots and role-gated actions", async () => {
    await renderReadySheet();

    expect(screen.getByRole("button", { name: "Mark ready" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel batch" })).not.toBeInTheDocument();
    expect(screen.getByText("interface-2026-v7-B01-P01")).toBeInTheDocument();
    expect(screen.getByText("interface-2026-v7-B01-E01")).toBeInTheDocument();
    expect(document.querySelectorAll(".data-table").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("link", { name: "Export JSON" })).toHaveAttribute(
      "href",
      "/experiments/7/batches/5/export.json",
    );
  });

  it("shows the cancel action only to instructors and administrators", async () => {
    sessionState.role = "instructor";
    await renderReadySheet();

    const cancel = screen.getByRole("button", { name: "Cancel batch" });
    expect(cancel).toHaveAttribute("data-status-action", "cancelled");
  });

  it("updates the preparation row locally from the PATCH response without refetching", async () => {
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        return makeRunSheet();
      }
      if (path.endsWith("/solution-preparations/51")) {
        return { ...makeRunSheet().preparations[0].preparation, status: "preparing" };
      }
      return undefined;
    });
    await renderReadySheet();

    const card = preparationCard();
    fireEvent.change(within(card).getByLabelText("Status"), { target: { value: "preparing" } });
    fireEvent.click(within(card).getByRole("button", { name: "Save preparation" }));

    const heading = card.querySelector(".run-sheet-card__heading") as HTMLElement;
    await waitFor(() => expect(within(heading).getByText("preparing")).toBeInTheDocument());

    const patchCall = apiFetchMock.mock.calls.find((call) => call[1]?.method === "PATCH");
    expect(patchCall?.[1]?.body).toMatchObject({ status: "preparing", notes: "" });
    const runSheetFetches = apiFetchMock.mock.calls.filter((call) => runSheetMethod(call[0], call[1]));
    expect(runSheetFetches).toHaveLength(1);
  });

  it("sends actual_matches_planned when the recording is marked as planned", async () => {
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        return makeRunSheet();
      }
      if (path.endsWith("/solution-preparations/51")) {
        return makeRunSheet().preparations[0].preparation;
      }
      return undefined;
    });
    await renderReadySheet();

    const card = preparationCard();
    fireEvent.change(recordingSelect(card), { target: { value: "copied_from_plan" } });
    fireEvent.click(within(card).getByRole("button", { name: "Save preparation" }));

    await waitFor(() => {
      const patchCall = apiFetchMock.mock.calls.find((call) => call[1]?.method === "PATCH");
      expect(patchCall?.[1]?.body).toMatchObject({ actual_matches_planned: true });
      expect(patchCall?.[1]?.body).not.toHaveProperty("actual_solution_snapshot");
    });
  });

  it("emits the edited snapshot when recording adjusted parameters", async () => {
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        return makeRunSheet();
      }
      if (path.endsWith("/solution-preparations/51")) {
        return makeRunSheet().preparations[0].preparation;
      }
      return undefined;
    });
    await renderReadySheet();

    const card = preparationCard();
    fireEvent.change(recordingSelect(card), { target: { value: "entered" } });
    const editor = within(card).getByText("Formulation type").closest(".snapshot-editor") as HTMLElement;
    const weight = editor.querySelector('input[type="number"]') as HTMLInputElement;
    fireEvent.change(weight, { target: { value: "4" } });
    fireEvent.click(within(card).getByRole("button", { name: "Save preparation" }));

    await waitFor(() => {
      const patchCall = apiFetchMock.mock.calls.find((call) => call[1]?.method === "PATCH");
      const body = patchCall?.[1]?.body as { actual_solution_snapshot: { solids: { weight_mg: number }[] } };
      expect(body.actual_solution_snapshot).toBeDefined();
      expect(body.actual_solution_snapshot.solids[0].weight_mg).toBe(4);
    });
  });

  it("refetches the run sheet after a batch status transition", async () => {
    await renderReadySheet();

    fireEvent.click(screen.getByRole("button", { name: "Mark ready" }));

    await waitFor(() => {
      const statusCall = apiFetchMock.mock.calls.find((call) => call[0]?.endsWith("/status"));
      expect(statusCall?.[1]?.method).toBe("PATCH");
      expect(statusCall?.[1]?.body).toEqual({ status: "ready" });
    });
    await waitFor(() => {
      const fetches = apiFetchMock.mock.calls.filter((call) => runSheetMethod(call[0], call[1]));
      expect(fetches.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("renders the refetched run sheet after a split, not a stale local override", async () => {
    const sheet = makeRunSheet();
    let fetches = 0;
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        fetches += 1;
        if (fetches >= 2) {
          const refetched = makeRunSheet();
          refetched.preparations.push({
            preparation: preparation(52, "interface-2026-v7-B01-P02", "e".repeat(64)),
            uses: [{ id: 63, solution_preparation_id: 52, batch_condition_id: 21, layer_ordinal: 1, layer_role: "etl", layer_type: "sno2", layer_snapshot_hash: "f".repeat(64) }],
          });
          return refetched;
        }
        return sheet;
      }
      if (path.endsWith("/solution-preparations/51")) {
        // A prior preparation PATCH that sets a local override.
        return { ...sheet.preparations[0].preparation, status: "preparing" };
      }
      if (path.endsWith("/split")) {
        return sheet.preparations[0].preparation;
      }
      return undefined;
    });
    await renderReadySheet();

    // Record a preparation actual to establish a localSheet override.
    const card = preparationCard();
    fireEvent.change(within(card).getByLabelText("Status"), { target: { value: "preparing" } });
    fireEvent.click(within(card).getByRole("button", { name: "Save preparation" }));
    await waitFor(() => {
      const heading = card.querySelector(".run-sheet-card__heading") as HTMLElement;
      expect(within(heading).getByText("preparing")).toBeInTheDocument();
    });

    // Split, which refetches the run sheet with a new preparation.
    fireEvent.click(within(card).getByRole("button", { name: /Split preparation/ }));
    const member = card.querySelector('[data-split-member]') as HTMLInputElement;
    fireEvent.click(member);
    fireEvent.click(within(card).getByRole("button", { name: "Split" }));

    await waitFor(() => {
      expect(fetches).toBeGreaterThanOrEqual(2);
    });
    await waitFor(() => {
      expect(document.body.textContent).toContain("interface-2026-v7-B01-P02");
    });
  });

  it("posts the selected member ids when splitting a preparation", async () => {
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        return makeRunSheet();
      }
      if (path.endsWith("/split")) {
        return makeRunSheet().preparations[0].preparation;
      }
      return undefined;
    });
    await renderReadySheet();

    const card = preparationCard();
    fireEvent.click(within(card).getByRole("button", { name: /Split preparation/ }));
    const member = card.querySelector('[data-split-member]') as HTMLInputElement;
    fireEvent.click(member);
    fireEvent.click(within(card).getByRole("button", { name: "Split" }));

    await waitFor(() => {
      const splitCall = apiFetchMock.mock.calls.find((call) => call[0]?.endsWith("/split"));
      expect(splitCall?.[1]?.body).toEqual({ member_ids: [61], notes: "" });
    });
  });

  it("stays silent when a split refresh is superseded by a newer reload", async () => {
    const secondReload = deferredRunSheet();
    const thirdReload = deferredRunSheet();
    let runSheetCalls = 0;
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        runSheetCalls += 1;
        if (runSheetCalls === 1) {
          return makeRunSheet();
        }
        return runSheetCalls === 2 ? secondReload.promise : thirdReload.promise;
      }
      if (path.endsWith("/split") || path.endsWith("/status")) {
        return undefined;
      }
      return undefined;
    });
    await renderReadySheet();

    // First action: split. Its refresh (run-sheet fetch 2) stays pending.
    const card = preparationCard();
    fireEvent.click(within(card).getByRole("button", { name: /Split preparation/ }));
    fireEvent.click(card.querySelector('[data-split-member]') as HTMLInputElement);
    fireEvent.click(within(card).getByRole("button", { name: "Split" }));
    await waitFor(() => expect(runSheetCalls).toBe(2));

    // Second action: mark the batch ready. Its refresh (fetch 3) supersedes
    // the still-pending split refresh.
    fireEvent.click(screen.getByRole("button", { name: "Mark ready" }));
    await waitFor(() => expect(runSheetCalls).toBe(3));

    // The newest refresh lands with the split topology and the new status.
    const readySheet = makeRunSheet();
    readySheet.batch = { ...readySheet.batch, status: "ready" };
    readySheet.preparations = readySheet.preparations.map((item, index) =>
      index === 0
        ? {
            ...item,
            preparation: preparation(51, "interface-2026-v7-B01-P01X", item.preparation.planned_canonical_hash),
          }
        : item,
    );
    await act(async () => {
      thirdReload.resolve(readySheet);
      await thirdReload.promise;
    });
    await waitFor(() =>
      expect(screen.getAllByText("interface-2026-v7-B01-P01X").length).toBeGreaterThan(0),
    );
    expect(screen.getAllByText("Batch status changed to ready.")).toHaveLength(1);

    // The superseded split refresh resolves late with the pre-split sheet: it
    // must not toast, must not raise the refresh-failure banner, and must not
    // replace the fresh topology.
    await act(async () => {
      secondReload.resolve(makeRunSheet());
      await secondReload.promise;
    });

    expect(screen.queryByText("Split saved.")).not.toBeInTheDocument();
    expect(screen.queryByText(/Unable to refresh the run sheet/)).not.toBeInTheDocument();
    expect(screen.getAllByText("interface-2026-v7-B01-P01X").length).toBeGreaterThan(0);
  });

  it("records a deviation with a JSON planned value and the encoded target", async () => {
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        return makeRunSheet();
      }
      if (path.endsWith("/deviations")) {
        return {
          id: 91,
          fabrication_batch_id: 5,
          category: "process",
          deviation_type: "general",
          severity: "warning",
          description: "Weight drifted by 0.3 mg",
          planned_value: { weight_mg: 2 },
          actual_value: null,
          recorded_by_id: 2,
          recorded_at: "2026-08-04T08:00:00Z",
          supersedes_deviation_id: null,
          solution_preparation_id: 51,
          process_execution_id: null,
          substrate_id: null,
          device_id: null,
          created_at: "2026-08-04T08:00:00Z",
        } satisfies Deviation;
      }
      return undefined;
    });
    await renderReadySheet();

    fireEvent.change(screen.getByLabelText("Target"), { target: { value: "solution_preparation_id:51" } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Weight drifted by 0.3 mg" } });
    fireEvent.change(screen.getByLabelText("Planned value (JSON)"), { target: { value: '{"weight_mg": 2}' } });
    fireEvent.click(screen.getByRole("button", { name: "Record deviation" }));

    await waitFor(() => {
      const deviationCall = apiFetchMock.mock.calls.find(
        (call) => call[0]?.endsWith("/deviations") && call[1]?.method === "POST",
      );
      expect(deviationCall?.[1]?.body).toMatchObject({
        category: "process",
        deviation_type: "general",
        severity: "warning",
        description: "Weight drifted by 0.3 mg",
        solution_preparation_id: 51,
        planned_value: { weight_mg: 2 },
      });
    });
    expect(await screen.findByText("Weight drifted by 0.3 mg")).toBeInTheDocument();
  });

  it("completes the batch with one PATCH and embedded shortfall deviations", async () => {
    const sheet = makeRunSheet();
    sheet.batch.status = "in_progress";
    sheet.preparations[0].preparation.status = "discarded";
    sheet.executions[0].execution.status = "cancelled";
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        return sheet;
      }
      return undefined;
    });
    renderPage();
    await screen.findByText("Frozen conditions");

    fireEvent.click(screen.getByRole("button", { name: "Complete batch" }));
    const countInput = document.querySelector(
      "[data-completion-count='21']",
    ) as HTMLInputElement;
    fireEvent.change(countInput, { target: { value: "2" } });
    fireEvent.change(
      document.querySelector("[data-completion-deviation='21']") as HTMLTextAreaElement,
      { target: { value: "One substrate cracked during annealing." } },
    );
    const dialogConfirm = screen
      .getAllByRole("button", { name: "Complete batch" })
      .at(-1) as HTMLButtonElement;
    fireEvent.click(dialogConfirm);

    await waitFor(() => {
      const patchCalls = apiFetchMock.mock.calls.filter(
        (call) => call[0]?.endsWith("/status") && call[1]?.method === "PATCH",
      );
      expect(patchCalls).toHaveLength(1);
      expect(patchCalls[0][1]?.body).toMatchObject({
        status: "completed",
        actual_substrate_counts: { "21": 2 },
        shortfall_deviations: [
          { condition_id: 21, description: "One substrate cracked during annealing." },
        ],
      });
    });
    expect(
      apiFetchMock.mock.calls.some(
        (call) => call[0]?.endsWith("/deviations") && call[1]?.method === "POST",
      ),
    ).toBe(false);
  });

  it("a failed completion PATCH assumes nothing saved; retry issues exactly one more request", async () => {
    const sheet = makeRunSheet();
    sheet.batch.status = "in_progress";
    sheet.preparations[0].preparation.status = "discarded";
    sheet.executions[0].execution.status = "cancelled";
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        return sheet;
      }
      if (path.endsWith("/status") && options?.method === "PATCH") {
        throw new Error("server rejected the completion");
      }
      return undefined;
    });
    renderPage();
    await screen.findByText("Frozen conditions");

    const fillAndConfirm = () => {
      fireEvent.click(screen.getByRole("button", { name: "Complete batch" }));
      const countInput = document.querySelector(
        "[data-completion-count='21']",
      ) as HTMLInputElement;
      fireEvent.change(countInput, { target: { value: "2" } });
      fireEvent.change(
        document.querySelector("[data-completion-deviation='21']") as HTMLTextAreaElement,
        { target: { value: "One substrate cracked during annealing." } },
      );
      fireEvent.click(
        screen.getAllByRole("button", { name: "Complete batch" }).at(-1) as HTMLButtonElement,
      );
    };

    fillAndConfirm();
    expect(await screen.findByText(/server rejected the completion/i)).toBeInTheDocument();
    // The dialog stays open with the operator's input; no deviation POST
    // happened and nothing is assumed saved.
    expect(
      apiFetchMock.mock.calls.some(
        (call) => call[0]?.endsWith("/deviations") && call[1]?.method === "POST",
      ),
    ).toBe(false);

    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        return sheet;
      }
      return undefined;
    });
    fireEvent.click(
      screen.getAllByRole("button", { name: "Complete batch" }).at(-1) as HTMLButtonElement,
    );

    await waitFor(() => {
      const patchCalls = apiFetchMock.mock.calls.filter(
        (call) => call[0]?.endsWith("/status") && call[1]?.method === "PATCH",
      );
      expect(patchCalls).toHaveLength(2);
      expect(patchCalls[1][1]?.body).toMatchObject({
        status: "completed",
        shortfall_deviations: [
          { condition_id: 21, description: "One substrate cracked during annealing." },
        ],
      });
    });
    expect(
      apiFetchMock.mock.calls.some(
        (call) => call[0]?.endsWith("/deviations") && call[1]?.method === "POST",
      ),
    ).toBe(false);
  });

  it("rejects invalid JSON deviation values client-side without posting", async () => {
    await renderReadySheet();

    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "invalid planned value" } });
    fireEvent.change(screen.getByLabelText("Planned value (JSON)"), { target: { value: "{broken" } });
    fireEvent.click(screen.getByRole("button", { name: "Record deviation" }));

    expect(await screen.findByText("Planned value must be valid JSON")).toBeInTheDocument();
    const posted = apiFetchMock.mock.calls.filter((call) => call[0]?.endsWith("/deviations"));
    expect(posted).toHaveLength(0);
  });

it("ignores an old-route preparation save that resolves after navigation", async () => {
    const sheetB = makeRunSheet();
    sheetB.batch = { ...sheetB.batch, id: 99, batch_code: "other-sheet-B99", status: "ready" };
    sheetB.preparations = sheetB.preparations.map((item, index) => ({
      ...item,
      preparation: {
        ...item.preparation,
        preparation_code: `other-sheet-B99-P0${index + 1}`,
      },
    }));
    let resolveSaved!: (value: SolutionPreparation) => void;
    const saved = new Promise<SolutionPreparation>((resolve) => {
      resolveSaved = resolve;
    });
    const runSheetFetches: string[] = [];
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if ((options?.method ?? "GET") === "GET" && path.endsWith("/run-sheet")) {
        runSheetFetches.push(path);
        return path.includes("/99/") ? sheetB : makeRunSheet();
      }
      if (path.endsWith("/solution-preparations/51")) {
        return saved;
      }
      return undefined;
    });
    renderNavigablePage();
    await screen.findByText("interface-2026-v7-B01-P01");

    // Begin a preparation save on batch A (deferred).
    const card = preparationCard();
    fireEvent.change(within(card).getByLabelText("Status"), { target: { value: "preparing" } });
    fireEvent.click(within(card).getByRole("button", { name: "Save preparation" }));
    await waitFor(() => {
      expect(apiFetchMock.mock.calls.some((call) => call[0]?.includes("/solution-preparations/51"))).toBe(true);
    });

    // Navigate to batch B while the save is still pending.
    fireEvent.click(screen.getByRole("button", { name: "navigate-to" }));
    await screen.findByText("other-sheet-B99");

    // Resolve the old-route mutation after B has loaded.
    await act(async () => {
      resolveSaved({ ...makeRunSheet().preparations[0].preparation, status: "preparing" });
      await saved;
    });

    // No success toast from the old route, no prep injected into B's sheet,
    // and no run-sheet refetch for the old route after navigation.
    expect(screen.queryByText("Solution preparation saved.")).not.toBeInTheDocument();
    expect(screen.queryByText("interface-2026-v7-B01-P01")).not.toBeInTheDocument();
    const fetchesAfterNavigation = runSheetFetches.filter((path) => path.includes("/5/run-sheet"));
    expect(fetchesAfterNavigation.length).toBeLessThanOrEqual(1);
  });

  it("ignores an old-route batch status refetch that resolves after navigation", async () => {
    const sheetB = makeRunSheet();
    sheetB.batch = { ...sheetB.batch, id: 99, batch_code: "other-sheet-B99", status: "ready" };
    sheetB.preparations = sheetB.preparations.map((item, index) => ({
      ...item,
      preparation: { ...item.preparation, preparation_code: `other-sheet-B99-P0${index + 1}` },
    }));
    let resolveStatus!: () => void;
    const statusPatch = new Promise<void>((resolve) => {
      resolveStatus = resolve;
    });
    const runSheetFetches: string[] = [];
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if ((options?.method ?? "GET") === "GET" && path.endsWith("/run-sheet")) {
        runSheetFetches.push(path);
        return path.includes("/99/") ? sheetB : makeRunSheet();
      }
      if (path.endsWith("/status") && options?.method === "PATCH") {
        await statusPatch;
        return undefined;
      }
      return undefined;
    });
    renderNavigablePage();
    await screen.findByText("interface-2026-v7-B01-P01");

    // Begin A's status mutation (PATCH deferred) and navigate before it resolves.
    fireEvent.click(screen.getByRole("button", { name: "Mark ready" }));
    await waitFor(() => {
      expect(apiFetchMock.mock.calls.some((call) => call[0]?.endsWith("/status"))).toBe(true);
    });
    fireEvent.click(screen.getByRole("button", { name: "navigate-to" }));
    await screen.findByText("other-sheet-B99");

    const fetchesBeforeResolve = runSheetFetches.length;
    await act(async () => {
      resolveStatus();
      await statusPatch;
    });

    // No A run-sheet refetch fired after navigation, no A toast, B stays usable.
    expect(runSheetFetches.length).toBe(fetchesBeforeResolve);
    expect(screen.queryByText("Batch status changed to ready.")).not.toBeInTheDocument();
    expect(screen.getByText("other-sheet-B99")).toBeInTheDocument();
    const startExecution = screen.getByRole("button", { name: "Start execution" });
    expect(startExecution).toBeEnabled();
  });

  it("keeps stale data hidden while a refresh retry is pending", async () => {
    let runSheetCalls = 0;
    let rejectRetry!: (error: unknown) => void;
    const retryDeferred = new Promise<void>((_resolve, reject) => {
      rejectRetry = reject;
    });
    const retried = makeRunSheet();
    retried.batch = { ...retried.batch, status: "ready" };
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        runSheetCalls += 1;
        if (runSheetCalls === 3) {
          await retryDeferred;
          return retried;
        }
        if (runSheetCalls === 2) {
          throw new Error("refresh unavailable");
        }
        return makeRunSheet();
      }
      return undefined;
    });
    await renderReadySheet();

    fireEvent.click(screen.getByRole("button", { name: "Mark ready" }));
    expect(await screen.findByText("Unable to refresh run sheet", { exact: true })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark ready" })).not.toBeInTheDocument();
    expect(screen.queryByText("interface-2026-v7-B01")).not.toBeInTheDocument();

    // Begin the retry; the deferred request stays pending.
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(screen.getByText("Unable to refresh run sheet", { exact: true })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark ready" })).not.toBeInTheDocument();
    expect(screen.queryByText("interface-2026-v7-B01")).not.toBeInTheDocument();

    // A second failure keeps the error state.
    await act(async () => {
      rejectRetry(new Error("still unavailable"));
      await retryDeferred.catch(() => undefined);
    });
    expect(screen.getByText("Unable to refresh run sheet", { exact: true })).toBeInTheDocument();
    expect(screen.queryByText("interface-2026-v7-B01")).not.toBeInTheDocument();
  });

  it("renders the fresh run sheet once a refresh retry succeeds", async () => {
    let runSheetCalls = 0;
    let resolveRetry!: () => void;
    const retryDeferred = new Promise<void>((resolve) => {
      resolveRetry = resolve;
    });
    const retried = makeRunSheet();
    retried.batch = { ...retried.batch, status: "ready" };
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        runSheetCalls += 1;
        if (runSheetCalls === 3) {
          await retryDeferred;
          return retried;
        }
        if (runSheetCalls === 2) {
          throw new Error("refresh unavailable");
        }
        return makeRunSheet();
      }
      return undefined;
    });
    await renderReadySheet();

    fireEvent.click(screen.getByRole("button", { name: "Mark ready" }));
    expect(await screen.findByText("Unable to refresh run sheet", { exact: true })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(screen.getByText("Unable to refresh run sheet", { exact: true })).toBeInTheDocument();

    await act(async () => {
      resolveRetry();
      await retryDeferred;
    });
    expect(await screen.findByRole("button", { name: "Start execution" })).toBeInTheDocument();
    expect(screen.queryByText("Unable to refresh run sheet")).not.toBeInTheDocument();
  });

  it("merges an identical-hash preparation only after confirmation", async () => {
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        const sheet = makeRunSheet();
        sheet.preparations.push({
          preparation: preparation(52, "interface-2026-v7-B01-P02", "e".repeat(64)),
          uses: [{ id: 63, solution_preparation_id: 52, batch_condition_id: 21, layer_ordinal: 1, layer_role: "etl", layer_type: "sno2", layer_snapshot_hash: "f".repeat(64) }],
        });
        return sheet;
      }
      if (path.endsWith("/merge")) {
        return makeRunSheet().preparations[0].preparation;
      }
      return undefined;
    });
    await renderReadySheet();

    const card = preparationCard();
    const mergeLabel = within(card).getByText("Merge into this preparation").closest("label") as HTMLLabelElement;
    fireEvent.change(mergeLabel.querySelector("select") as HTMLSelectElement, { target: { value: "52" } });
    fireEvent.click(within(card).getByRole("button", { name: "Merge" }));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("The source preparation will be merged and deleted");
    const postedBeforeConfirm = apiFetchMock.mock.calls.filter((call) => call[0]?.endsWith("/merge"));
    expect(postedBeforeConfirm).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();

    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm" }));

    await waitFor(() => {
      const mergeCall = apiFetchMock.mock.calls.find((call) => call[0]?.endsWith("/merge"));
      expect(mergeCall?.[1]?.method).toBe("POST");
      expect(mergeCall?.[1]?.body).toEqual({ source_id: 52 });
    });
  });

  it("never posts a merge when the confirmation dialog is dismissed", async () => {
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        const sheet = makeRunSheet();
        sheet.preparations.push({
          preparation: preparation(52, "interface-2026-v7-B01-P02", "e".repeat(64)),
          uses: [{ id: 63, solution_preparation_id: 52, batch_condition_id: 21, layer_ordinal: 1, layer_role: "etl", layer_type: "sno2", layer_snapshot_hash: "f".repeat(64) }],
        });
        return sheet;
      }
      return undefined;
    });
    await renderReadySheet();

    const card = preparationCard();
    const mergeLabel = within(card).getByText("Merge into this preparation").closest("label") as HTMLLabelElement;
    fireEvent.change(mergeLabel.querySelector("select") as HTMLSelectElement, { target: { value: "52" } });
    fireEvent.click(within(card).getByRole("button", { name: "Merge" }));
    await screen.findByRole("dialog");

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const posted = apiFetchMock.mock.calls.filter((call) => call[0]?.endsWith("/merge"));
    expect(posted).toHaveLength(0);
  });

  it("requires confirmation before cancelling a batch and posts the cancelled status", async () => {
    sessionState.role = "instructor";
    await renderReadySheet();

    fireEvent.click(screen.getByRole("button", { name: "Cancel batch" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Cancellation is final and the run sheet cannot be reopened");
    const postedBefore = apiFetchMock.mock.calls.filter((call) => call[0]?.endsWith("/status"));
    expect(postedBefore).toHaveLength(0);

    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm" }));

    await waitFor(() => {
      const statusCall = apiFetchMock.mock.calls.find((call) => call[0]?.endsWith("/status"));
      expect(statusCall?.[1]?.body).toEqual({ status: "cancelled" });
    });
  });

  it("surfaces the server detail when a merge is rejected", async () => {
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        const sheet = makeRunSheet();
        sheet.preparations.push({
          preparation: preparation(52, "interface-2026-v7-B01-P02", "e".repeat(64)),
          uses: [{ id: 63, solution_preparation_id: 52, batch_condition_id: 21, layer_ordinal: 1, layer_role: "etl", layer_type: "sno2", layer_snapshot_hash: "f".repeat(64) }],
        });
        return sheet;
      }
      if (path.endsWith("/merge")) {
        throw new Error("merge source preparation has a different planned snapshot");
      }
      return undefined;
    });
    await renderReadySheet();

    const card = preparationCard();
    const mergeLabel = within(card).getByText("Merge into this preparation").closest("label") as HTMLLabelElement;
    fireEvent.change(mergeLabel.querySelector("select") as HTMLSelectElement, { target: { value: "52" } });
    fireEvent.click(within(card).getByRole("button", { name: "Merge" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Confirm" }));

    expect(
      await screen.findByText("merge source preparation has a different planned snapshot"),
    ).toBeInTheDocument();
  });

  it("hides split and merge controls once the batch leaves the draft state", async () => {
    const sheet = makeRunSheet();
    sheet.batch.status = "ready";
    sheet.preparations.push({
      preparation: preparation(52, "interface-2026-v7-B01-P02", "e".repeat(64)),
      uses: [{ id: 63, solution_preparation_id: 52, batch_condition_id: 21, layer_ordinal: 1, layer_role: "etl", layer_type: "sno2", layer_snapshot_hash: "f".repeat(64) }],
    });
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        return sheet;
      }
      return undefined;
    });
    await renderReadySheet();

    expect(screen.queryByText(/Split preparation/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Split execution/)).not.toBeInTheDocument();
    expect(screen.queryByText("Merge into this preparation")).not.toBeInTheDocument();
    expect(screen.queryByText("Merge into this execution")).not.toBeInTheDocument();
  });

  it("does not offer executions with a different layer context as merge candidates", async () => {
    const sheet = makeRunSheet();
    const duplicate = {
      ...sheet.executions[0],
      execution: {
        ...sheet.executions[0].execution,
        id: 72,
        execution_code: "interface-2026-v7-B01-E02",
        layer_name: "C70",
      },
    };
    sheet.executions.push(duplicate);
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        return sheet;
      }
      return undefined;
    });
    await renderReadySheet();

    expect(screen.queryByText("Merge into this execution")).not.toBeInTheDocument();
  });

  it("appends a deviation without overwriting a concurrent preparation save", async () => {
    const sheet = makeRunSheet();
    const updated = { ...sheet.preparations[0].preparation, status: "preparing" };
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        return sheet;
      }
      if (path.endsWith("/solution-preparations/51")) {
        return updated;
      }
      if (path.endsWith("/deviations")) {
        return {
          id: 91,
          fabrication_batch_id: 5,
          category: "process",
          deviation_type: "general",
          severity: "warning",
          description: "Concurrent deviation",
          planned_value: null,
          actual_value: null,
          recorded_by_id: 2,
          recorded_at: "2026-08-04T08:00:00Z",
          supersedes_deviation_id: null,
          solution_preparation_id: null,
          process_execution_id: null,
          substrate_id: null,
          device_id: null,
          created_at: "2026-08-04T08:00:00Z",
        } satisfies Deviation;
      }
      return undefined;
    });
    await renderReadySheet();

    const card = preparationCard();
    fireEvent.change(within(card).getByLabelText("Status"), { target: { value: "preparing" } });
    fireEvent.click(within(card).getByRole("button", { name: "Save preparation" }));
    await waitFor(() => {
      const heading = card.querySelector(".run-sheet-card__heading") as HTMLElement;
      expect(within(heading).getByText("preparing")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Concurrent deviation" } });
    fireEvent.click(screen.getByRole("button", { name: "Record deviation" }));
    expect(await screen.findByText("Concurrent deviation")).toBeInTheDocument();

    const heading = card.querySelector(".run-sheet-card__heading") as HTMLElement;
    expect(within(heading).getByText("preparing")).toBeInTheDocument();
  });

  it("reports a failed refetch after a status transition instead of a success toast", async () => {
    const sheet = makeRunSheet();
    let fetches = 0;
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (runSheetMethod(path, options)) {
        fetches += 1;
        if (fetches >= 2) {
          throw new Error("database unavailable");
        }
        return sheet;
      }
      if (path.endsWith("/status")) {
        return undefined;
      }
      return undefined;
    });
    await renderReadySheet();

    fireEvent.click(screen.getByRole("button", { name: "Mark ready" }));

    // reload() resolves false; the stale run sheet must not masquerade as the
    // current batch, so the error state replaces it and no success toast shows.
    expect(await screen.findByText("Unable to refresh run sheet", { exact: true })).toBeInTheDocument();
    expect(screen.queryByText("Batch status changed to ready.")).not.toBeInTheDocument();
    expect(screen.queryByText("Mark ready")).not.toBeInTheDocument();
  });

  it("rejects a batch URL whose experiment does not match the run sheet", async () => {
    render(
      <MemoryRouter initialEntries={["/experiments/99/batches/5"]}>
        <ToastProvider>
          <Routes>
            <Route path="/experiments/:experimentId/batches/:batchId" element={<BatchDetailPage />} />
          </Routes>
        </ToastProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Batch not found")).toBeInTheDocument();
    expect(screen.getByText("The batch does not belong to the requested experiment.")).toBeInTheDocument();
  });

  it("never renders batch A data or its mutation actions after navigating to a failing batch B", async () => {
    sessionState.role = "instructor";
    const batchA = makeRunSheet();
    const batchB = makeRunSheet();
    batchB.batch.id = 99;
    batchB.batch.batch_code = "interface-2026-v7-B02";
    batchB.preparations[0].preparation.preparation_code = "interface-2026-v7-B02-P01";
    batchB.executions[0].execution.execution_code = "interface-2026-v7-B02-E01";
    apiFetchMock.mockReset();
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if ((options?.method ?? "GET") !== "GET" || !path.endsWith("/run-sheet")) {
        return undefined;
      }
      if (path === "/api/fabrication-batches/5/run-sheet") {
        return batchA;
      }
      if (path === "/api/fabrication-batches/99/run-sheet") {
        throw new Error("database unavailable");
      }
      return undefined;
    });
    renderNavigablePage();
    await screen.findByText("interface-2026-v7-B01");

    // Open a confirmation dialog before navigating, and confirm a prep row is present.
    fireEvent.click(screen.getByRole("button", { name: "Cancel batch" }));
    await screen.findByRole("dialog");

    // Reuse the same mounted router instance to navigate to batch B.
    fireEvent.click(screen.getByRole("button", { name: "navigate-to" }));

    // The error state for batch B must be shown.
    expect(await screen.findByText("Unable to load run sheet")).toBeInTheDocument();
    expect(screen.queryByText("interface-2026-v7-B01")).not.toBeInTheDocument();
    expect(screen.queryByText("interface-2026-v7-B01-P01")).not.toBeInTheDocument();
    expect(screen.queryByText("interface-2026-v7-B01-E01")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark ready" })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    // No mutation may be submitted while batch B is loading/failed.
    const mutations = apiFetchMock.mock.calls.filter((call) => call[1]?.method && call[1].method !== "GET");
    expect(mutations).toHaveLength(0);
  });

  it("surfaces a missing run sheet as the error state", async () => {
    apiFetchMock.mockRejectedValue(new Error("unknown fabrication batch id: 5"));
    renderPage();

    expect(await screen.findByText("Unable to load run sheet")).toBeInTheDocument();
  });
});