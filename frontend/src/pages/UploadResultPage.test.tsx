import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../components/Toast";
import { UploadResultPage } from "./UploadResultPage";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", () => ({ apiFetch: apiFetchMock }));

const LIMIT = 10 * 1024 * 1024;

function makeExperiment() {
  // Mirrors the current ExperimentDetail API: per-condition records; the
  // legacy recipe.device_recipe blob no longer travels with the response.
  return {
    experiment: {
      id: 7,
      recipe: null,
    },
    conditions: [
      {
        id: 21,
        experiment_id: 7,
        role: "control",
        condition_code: "EXPERIMENT-v1-C",
        condition_name: "Control",
        recipe_snapshot: {},
        recipe_schema_version: 3,
        canonical_hash: "hash-c",
        source_baseline_version_id: null,
        device_layout_code: "25x25_six_010",
        device_layout_snapshot: {},
        planned_substrate_count: 3,
        expected_device_count: 18,
        requires_manual_review: false,
        created_at: "2026-08-14T08:00:00Z",
      },
      {
        id: 22,
        experiment_id: 7,
        role: "target",
        condition_code: "EXPERIMENT-v1-T1",
        condition_name: "ADH",
        recipe_snapshot: {},
        recipe_schema_version: 3,
        canonical_hash: "hash-t",
        source_baseline_version_id: null,
        device_layout_code: "25x25_six_010",
        device_layout_snapshot: {},
        planned_substrate_count: 3,
        expected_device_count: 18,
        requires_manual_review: false,
        created_at: "2026-08-14T08:00:00Z",
      },
    ],
    substrate_exceptions: [],
    fabrication_batches: [
      { id: 5, batch_code: "B01", status: "draft" },
      { id: 6, batch_code: "B02", status: "in_progress" },
      { id: 7, batch_code: "B03", status: "completed" },
      { id: 8, batch_code: "B04", status: "cancelled" },
    ],
    results: [],
  } as unknown as Record<string, unknown>;
}

function makeExperimentWithoutConditions() {
  const detail = makeExperiment();
  detail.conditions = [];
  return detail;
}

function renderPage(experimentId = "7") {
  return render(
    <MemoryRouter initialEntries={[`/experiments/${experimentId}/upload`]}>
      <ToastProvider>
        <Routes>
          <Route path="/experiments/:experimentId/upload" element={<UploadResultPage />} />
          <Route path="/results/:resultId" element={<div data-testid="detail" />} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe("UploadResultPage", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue(makeExperiment());
  });

  it("offers only in_progress and completed batches", async () => {
    renderPage();
    await screen.findByText("B02 (in progress)");
    expect(screen.getByText("B03 (completed)")).toBeInTheDocument();
    expect(screen.queryByText("B01 (draft)")).not.toBeInTheDocument();
    expect(screen.queryByText("B04 (cancelled)")).not.toBeInTheDocument();
  });

  it("shows the expected conditions as a badge strip", async () => {
    renderPage();
    expect(await screen.findByText("Control")).toBeInTheDocument();
    expect(screen.getByText("ADH")).toBeInTheDocument();
    // The control condition renders with the neutral badge style.
    expect(screen.getByText("Control").className).toContain("status-badge--neutral");
    expect(screen.getByText("ADH").className).toContain("status-badge--planned");
  });

  it("does not render the expected-groups section without conditions", async () => {
    apiFetchMock.mockResolvedValue(makeExperimentWithoutConditions());
    renderPage();
    await screen.findByText("B02 (in progress)");
    expect(screen.queryByText(/Expected groups/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Control")).not.toBeInTheDocument();
  });

  it("posts a FormData payload with result_file and fabrication_batch_id", async () => {
    renderPage();
    await screen.findByText("B02 (in progress)");
    const file = new File(["voltage,current_density\n0,-20\n1,0\n"], "run.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/CSV result file/), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText(/Fabrication batch/), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: /Read devices and continue/ }));

    await waitFor(() => {
      const calls = apiFetchMock.mock.calls.filter(
        (call) => typeof call[0] === "string" && call[0].endsWith("/results"),
      );
      expect(calls).toHaveLength(1);
      const payload = calls[0][1].multipart as FormData;
      expect(payload.get("fabrication_batch_id")).toBe("6");
      expect(payload.get("result_file")).toBeInstanceOf(File);
    });
  });

  it("accepts a file exactly at the 10 MiB limit", async () => {
    renderPage();
    await screen.findByText("B02 (in progress)");
    const exact = new File([new Uint8Array(LIMIT)], "exact.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/CSV result file/), { target: { files: [exact] } });
    fireEvent.change(screen.getByLabelText(/Fabrication batch/), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: /Read devices and continue/ }));
    await waitFor(() => {
      expect(apiFetchMock.mock.calls.some((call) => typeof call[0] === "string" && call[0].endsWith("/results"))).toBe(true);
    });
  });

  it("rejects a file above the 10 MiB limit before submitting", async () => {
    renderPage();
    await screen.findByText("B02 (in progress)");
    const over = new File([new Uint8Array(LIMIT + 1)], "over.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/CSV result file/), { target: { files: [over] } });
    fireEvent.change(screen.getByLabelText(/Fabrication batch/), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: /Read devices and continue/ }));
    expect(await screen.findByText(/must not exceed 10 MB/i)).toBeInTheDocument();
    expect(apiFetchMock.mock.calls.some((call) => typeof call[0] === "string" && call[0].endsWith("/results"))).toBe(false);
  });

  it("renders a normalized server error inline", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path.endsWith("/results")) {
        const error = new Error("this result file has already been uploaded for the batch");
        (error as Error & { status?: number }).status = 400;
        throw error;
      }
      return makeExperiment();
    });
    renderPage();
    await screen.findByText("B02 (in progress)");
    const file = new File(["voltage,current_density\n0,-20\n1,0\n"], "run.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/CSV result file/), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText(/Fabrication batch/), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: /Read devices and continue/ }));
    expect(await screen.findByText(/already been uploaded/)).toBeInTheDocument();
  });

  it("navigates to the returned result detail on success", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path.endsWith("/results")) {
        return { id: 42, experiment_id: 7, fabrication_batch_id: 6 };
      }
      return makeExperiment();
    });
    renderPage();
    await screen.findByText("B02 (in progress)");
    const file = new File(["voltage,current_density\n0,-20\n1,0\n"], "run.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/CSV result file/), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText(/Fabrication batch/), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: /Read devices and continue/ }));
    await waitFor(() => expect(screen.getByTestId("detail")).toBeInTheDocument());
  });

  it("does not navigate or toast when an upload resolves after unmount", async () => {
    let resolveUpload!: (value: unknown) => void;
    const deferred = new Promise((resolve) => { resolveUpload = resolve; });
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path.endsWith("/results")) return deferred;
      return makeExperiment();
    });
    const { unmount } = renderPage();
    await screen.findByText("B02 (in progress)");
    const file = new File(["voltage,current_density\n0,-20\n1,0\n"], "run.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/CSV result file/), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText(/Fabrication batch/), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: /Read devices and continue/ }));
    unmount();
    await act(async () => { resolveUpload({ id: 99 }); await deferred.catch(() => undefined); });
    expect(screen.queryByTestId("detail")).not.toBeInTheDocument();
    expect(screen.queryByText(/Result uploaded/)).not.toBeInTheDocument();
  });

  it("does not let experiment A's file be submitted on experiment B's route", async () => {
    const experimentB = makeExperiment();
    (experimentB.experiment as Record<string, unknown>).id = 99;
    let fetchCount = 0;
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/experiments/7") return makeExperiment();
      if (path === "/api/experiments/99") return experimentB;
      if (path.endsWith("/results")) {
        fetchCount += 1;
        return { id: 50 };
      }
      return undefined;
    });
    function Nav() {
      const navigate = useNavigate();
      return <button type="button" onClick={() => navigate("/experiments/99/upload")}>nav-b</button>;
    }
    render(
      <MemoryRouter initialEntries={["/experiments/7/upload"]}>
        <ToastProvider>
          <Nav />
          <Routes>
            <Route path="/experiments/:experimentId/upload" element={<UploadResultPage />} />
            <Route path="/results/:resultId" element={<div data-testid="detail" />} />
          </Routes>
        </ToastProvider>
      </MemoryRouter>,
    );
    await screen.findByText("B02 (in progress)");
    const file = new File(["voltage,current_density\n0,-20\n1,0\n"], "run.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/CSV result file/), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText(/Fabrication batch/), { target: { value: "6" } });
    // Navigate to experiment B before the upload resolves.
    fireEvent.click(screen.getByRole("button", { name: "nav-b" }));
    await screen.findByText("B02 (in progress)");
    // The file input on B should be empty (A's file did not carry over).
    expect((screen.getByLabelText(/CSV result file/) as HTMLInputElement).files?.length ?? 0).toBe(0);
    expect(fetchCount).toBe(0);
  });
});
