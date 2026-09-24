import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../components/Toast";
import { DeviceLayoutsPage } from "./DeviceLayoutsPage";

const apiFetchMock = vi.hoisted(() => vi.fn());
const sessionState = vi.hoisted(() => ({
  role: "student" as "student" | "instructor" | "administrator",
}));

vi.mock("../lib/api", () => ({ apiFetch: apiFetchMock }));
vi.mock("../auth/session", () => ({
  useSession: () => ({
    user: { id: 2, username: "layout-user", display_name: "Layout User", role: sessionState.role, csrf_available: true },
  }),
}));

function renderPage() {
  return render(<ToastProvider><DeviceLayoutsPage /></ToastProvider>);
}

const LAYOUT_ROWS = [
  {
    code: "25x25_six_010",
    version: 1,
    substrate_width_mm: "25",
    substrate_length_mm: "25",
    devices_per_substrate: 6,
    device_active_area_cm2: "0.10",
    total_active_area_cm2: "0.60",
    description: "25 × 25 mm substrate, 6 devices",
  },
];

describe("DeviceLayoutsPage", () => {
  beforeEach(() => {
    sessionState.role = "student";
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue(LAYOUT_ROWS);
  });

  it("renders versioned dimensions and active areas with units", async () => {
    renderPage();

    expect(await screen.findByText("25 × 25 mm")).toBeInTheDocument();
    expect(screen.getByText("0.10 cm²")).toBeInTheDocument();
    expect(screen.getByText("0.60 cm²")).toBeInTheDocument();
    expect(screen.getByText("6")).toBeInTheDocument();
    expect(screen.getByText("v1")).toBeInTheDocument();
  });

  it("hides the create form from non-administrators", async () => {
    renderPage();

    await screen.findByText("25 × 25 mm");
    expect(screen.queryByLabelText("Code")).not.toBeInTheDocument();
  });

  it("lets an administrator create a layout version and reloads the directory", async () => {
    sessionState.role = "administrator";
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/device-layouts" && options?.method === "POST") {
        return Promise.resolve({
          code: "10x10_single_005",
          version: 1,
          substrate_width_mm: "10",
          substrate_length_mm: "10",
          devices_per_substrate: 1,
          device_active_area_cm2: "0.05",
          total_active_area_cm2: "0.05",
          description: "10 × 10 mm substrate, 1 device",
        });
      }
      return Promise.resolve(LAYOUT_ROWS);
    });
    renderPage();
    await screen.findByText("25 × 25 mm");

    fireEvent.change(screen.getByLabelText(/^Code/), { target: { value: "10x10_single_005" } });
    fireEvent.change(screen.getByLabelText(/Substrate width/i), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText(/Substrate length/i), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText(/Active area per device/i), { target: { value: "0.05" } });
    fireEvent.change(screen.getByLabelText(/Total active area/i), { target: { value: "0.05" } });
    fireEvent.change(screen.getByLabelText(/^Description/), { target: { value: "10 × 10 mm substrate, 1 device" } });
    fireEvent.click(screen.getByRole("button", { name: "Create layout" }));

    expect(await screen.findByText(/v1 created/i)).toBeInTheDocument();
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/api/device-layouts", {
      method: "POST",
      body: {
        code: "10x10_single_005",
        version: 1,
        substrate_width_mm: "10",
        substrate_length_mm: "10",
        devices_per_substrate: 1,
        device_active_area_cm2: "0.05",
        total_active_area_cm2: "0.05",
        description: "10 × 10 mm substrate, 1 device",
      },
    }));
  });
});
