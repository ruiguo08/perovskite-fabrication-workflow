import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ToastProvider } from "./Toast";
import { DeviceScanHistoryPanel } from "./DeviceScanHistoryPanel";
import type { ResultAssignment } from "../types/api";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", () => ({ apiFetch: apiFetchMock }));

beforeEach(() => {
  apiFetchMock.mockReset();
  apiFetchMock.mockImplementation(async (path: string) => ({
    fabrication_device_id: Number(path.match(/devices\/(\d+)/)?.[1]),
    device_code: `D${path.match(/devices\/(\d+)/)?.[1]}`,
    device_mark: null,
    representative: { forward: null, reverse: null },
    scans: [],
  }));
});

it("loads only the selected device and keeps its scan list collapsed", async () => {
  const assignments = [1, 2].map((id) => ({
    fabrication_device_id: id,
    device_code: `D${id}`,
    device_mark: null,
  })) as ResultAssignment[];
  render(<ToastProvider><DeviceScanHistoryPanel assignments={assignments} /></ToastProvider>);
  await screen.findByText("No valid forward scan on record.");
  expect(apiFetchMock).toHaveBeenCalledTimes(1);
  expect(apiFetchMock).toHaveBeenCalledWith("/api/fabrication-devices/1/jv-scans");
  expect(screen.getByText("All scans (0)").closest("details")).not.toHaveAttribute("open");
  fireEvent.change(screen.getByLabelText("Device"), { target: { value: "2" } });
  await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/api/fabrication-devices/2/jv-scans"));
  expect(screen.getAllByText("No valid forward scan on record.")).toHaveLength(1);
});
