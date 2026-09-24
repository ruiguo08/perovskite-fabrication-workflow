import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FabricationBatchesPage } from "./FabricationBatchesPage";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", () => ({ apiFetch: apiFetchMock }));

const batches = [
  {
    id: 11,
    experiment_id: 7,
    experiment_code: "interface-2026-v7",
    batch_number: 1,
    batch_code: "interface-2026-v7-B01",
    status: "draft",
    condition_set_hash: "a".repeat(64),
    notes: "First batch",
    created_by_id: 2,
    created_at: "2026-08-01T08:00:00Z",
    updated_at: "2026-08-01T08:00:00Z",
    started_at: null,
    completed_at: null,
    cancelled_at: null,
  },
  {
    id: 12,
    experiment_id: 9,
    experiment_code: "stability-2026-v2",
    batch_number: 1,
    batch_code: "stability-2026-v2-B01",
    status: "completed",
    condition_set_hash: "b".repeat(64),
    notes: "",
    created_by_id: 2,
    created_at: "2026-08-02T08:00:00Z",
    updated_at: "2026-08-03T08:00:00Z",
    started_at: "2026-08-02T09:00:00Z",
    completed_at: "2026-08-03T08:00:00Z",
    cancelled_at: null,
  },
];

describe("FabricationBatchesPage", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue(batches);
  });

  it("renders the role-scoped batch list as React run-sheet links", async () => {
    render(<MemoryRouter><FabricationBatchesPage /></MemoryRouter>);

    const first = await screen.findByRole("link", { name: "interface-2026-v7-B01" });
    expect(first).toHaveAttribute("href", "/experiments/7/batches/11");
    const secondCard = screen.getByText("stability-2026-v2-B01").closest("article");
    expect(screen.getByRole("link", { name: "stability-2026-v2-B01" })).toHaveAttribute("href", "/experiments/9/batches/12");
    expect(within(secondCard as HTMLElement).getByText("completed")).toBeInTheDocument();
    expect(screen.getByText("interface-2026-v7")).toBeInTheDocument();
  });

  it("refetches server-side with the selected status filter", async () => {
    render(<MemoryRouter><FabricationBatchesPage /></MemoryRouter>);
    await screen.findByRole("link", { name: "interface-2026-v7-B01" });
    apiFetchMock.mockClear();
    apiFetchMock.mockResolvedValue([batches[1]]);

    fireEvent.change(screen.getByLabelText("Batch status"), { target: { value: "completed" } });

    expect(await screen.findByRole("link", { name: "stability-2026-v2-B01" })).toBeInTheDocument();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/fabrication-batches?status=completed");
  });

  it("shows the empty state when the server returns no batches", async () => {
    apiFetchMock.mockResolvedValue([]);
    render(<MemoryRouter><FabricationBatchesPage /></MemoryRouter>);

    expect(await screen.findByText("No fabrication batches yet.")).toBeInTheDocument();
  });

  it("shows a clear error instead of stale results when the filter request fails", async () => {
    apiFetchMock.mockResolvedValueOnce(batches);
    apiFetchMock.mockRejectedValueOnce(new Error("the server refused the request"));
    render(<MemoryRouter><FabricationBatchesPage /></MemoryRouter>);
    await screen.findByRole("link", { name: "interface-2026-v7-B01" });

    fireEvent.change(screen.getByLabelText("Batch status"), { target: { value: "completed" } });

    expect(await screen.findByText("Unable to load fabrication batches")).toBeInTheDocument();
    expect(screen.queryByText("interface-2026-v7-B01")).not.toBeInTheDocument();
    expect(screen.queryByText("stability-2026-v2-B01")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("surfaces load failures with a retry action", async () => {
    apiFetchMock.mockRejectedValue(new Error("the server refused the request"));
    render(<MemoryRouter><FabricationBatchesPage /></MemoryRouter>);

    expect(await screen.findByText("Unable to load fabrication batches")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});