import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../components/Toast";
import { ResultsPage } from "./ResultsPage";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", () => ({ apiFetch: apiFetchMock }));

function makeResult(overrides: Record<string, unknown> = {}) {
  return {
    id: 71,
    experiment_id: 7,
    experiment_code: "interface-2026-v7",
    fabrication_batch_id: 5,
    batch_code: "interface-2026-v7-B01",
    filename: "run-001.csv",
    content_type: "text/csv",
    size_bytes: 1024,
    sha256: "a".repeat(64),
    group_assignment: "",
    metrics: { pce: 10.2 },
    analysis_schema_version: 2,
    created_at: "2026-08-14T08:00:00Z",
    ...overrides,
  };
}

function renderPage(initialPath = "/results") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <ToastProvider>
        <Routes>
          <Route path="/results" element={<ResultsPage />} />
          <Route path="/results/:resultId" element={<div data-testid="detail" />} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe("ResultsPage", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue([]);
  });

  it("renders result rows linking to the detail route with integrity metadata", async () => {
    apiFetchMock.mockResolvedValue([makeResult()]);
    renderPage();

    await screen.findByText("run-001.csv");
    expect(screen.getByText("interface-2026-v7")).toBeInTheDocument();
    expect(screen.getByText("interface-2026-v7-B01")).toBeInTheDocument();
    expect(screen.getByText(/a{16}/)).toBeInTheDocument();
    expect(screen.getByText("Schema v2")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "run-001.csv" });
    expect(link).toHaveAttribute("href", "/results/71");
  });

  it("sends both server filters with the exact query parameter names", async () => {
    apiFetchMock.mockResolvedValue([]);
    renderPage();
    await screen.findByText(/No characterization results/);

    fireEvent.change(screen.getByLabelText("Experiment"), { target: { value: "7" } });
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/api/results?experiment_id=7"));
    fireEvent.change(screen.getByLabelText("Batch"), { target: { value: "5" } });
    await waitFor(() =>
      expect(apiFetchMock).toHaveBeenCalledWith("/api/results?experiment_id=7&fabrication_batch_id=5"),
    );
    fireEvent.change(screen.getByLabelText("Experiment"), { target: { value: "" } });
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/api/results?fabrication_batch_id=5"));
  });

  it("shows an empty state when there are no results", async () => {
    apiFetchMock.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText(/No characterization results/)).toBeInTheDocument();
  });

  it("shows an error state with a retry on an initial load failure", async () => {
    apiFetchMock.mockRejectedValueOnce(new Error("results unavailable"));
    renderPage();
    expect(await screen.findByText("Unable to load results")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("does not retain old rows after a filter request fails", async () => {
    apiFetchMock.mockResolvedValueOnce([makeResult({ id: 71, filename: "run-001.csv" })]);
    renderPage();
    await screen.findByText("run-001.csv");

    apiFetchMock.mockRejectedValueOnce(new Error("filter unavailable"));
    fireEvent.change(screen.getByLabelText("Experiment"), { target: { value: "9" } });

    await waitFor(() => expect(screen.queryByText("run-001.csv")).not.toBeInTheDocument());
    expect(await screen.findByText("Unable to load results")).toBeInTheDocument();
  });

  it("links to direction-specific statistics without displaying pooled metrics", async () => {
    apiFetchMock.mockResolvedValue([makeResult({ metrics: { pce: 12.5, voc: 1.1 } })]);
    renderPage();
    expect(await screen.findByRole("link", { name: "View direction-specific statistics" })).toHaveAttribute("href", "/results/71");
    expect(screen.queryByText(/PCE 12\.5/)).not.toBeInTheDocument();
  });
});
