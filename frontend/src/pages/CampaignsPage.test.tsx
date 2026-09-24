import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../components/Toast";
import { CampaignsPage } from "./CampaignsPage";

const apiFetchMock = vi.hoisted(() => vi.fn());
const sessionState = vi.hoisted(() => ({
  role: "student" as "student" | "instructor" | "administrator",
}));

vi.mock("../lib/api", () => ({ apiFetch: apiFetchMock }));
vi.mock("../auth/session", () => ({
  useSession: () => ({
    user: {
      id: 2,
      username: "campaign-user",
      display_name: "Campaign User",
      role: sessionState.role,
      csrf_available: true,
    },
  }),
}));

const activeCampaign = {
  id: 1,
  code: "stability-2026",
  display_name: "Stability series",
  description: "Track encapsulated devices",
  status: "active",
  created_at: "2026-08-01T08:00:00Z",
  updated_at: "2026-08-02T08:00:00Z",
  closed_at: null,
};

function renderPage() {
  return render(
    <ToastProvider>
      <CampaignsPage />
    </ToastProvider>,
  );
}

describe("CampaignsPage", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    sessionState.role = "student";
    apiFetchMock.mockResolvedValue([activeCampaign]);
  });

  it("shows students a read-only active Campaign directory", async () => {
    renderPage();

    expect(await screen.findByText("Stability series")).toBeInTheDocument();
    expect(screen.getByText("stability-2026")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Create Campaign" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/status for stability series/i)).not.toBeInTheDocument();
  });

  it("lets an instructor create a Campaign", async () => {
    sessionState.role = "instructor";
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/campaigns" && options?.method === "POST") {
        return Promise.resolve({
          ...activeCampaign,
          id: 2,
          code: "interface-screen",
          display_name: "Interface screening",
        });
      }
      return Promise.resolve([activeCampaign]);
    });
    renderPage();

    await screen.findByText("Stability series");
    fireEvent.change(screen.getByLabelText(/^Campaign code/), {
      target: { value: "interface-screen" },
    });
    fireEvent.change(screen.getByLabelText(/^Display name/), {
      target: { value: "Interface screening" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Create Campaign" }).closest("form")!);

    expect(await screen.findByText("Interface screening")).toBeInTheDocument();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/campaigns", {
      method: "POST",
      body: {
        code: "interface-screen",
        display_name: "Interface screening",
        description: "",
      },
    });
    await waitFor(() => expect(screen.getByLabelText(/^Campaign code/)).toHaveValue(""));
  });

  it("lets an instructor update Campaign status", async () => {
    sessionState.role = "instructor";
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/campaigns/stability-2026" && options?.method === "PATCH") {
        return Promise.resolve({ ...activeCampaign, status: "closed" });
      }
      return Promise.resolve([activeCampaign]);
    });
    renderPage();

    const status = await screen.findByLabelText("Status for Stability series");
    fireEvent.change(status, { target: { value: "closed" } });

    await waitFor(() => expect(status).toHaveValue("closed"));
    expect(apiFetchMock).toHaveBeenCalledWith("/api/campaigns/stability-2026", {
      method: "PATCH",
      body: { status: "closed" },
    });
  });

  it("keeps server errors inline without clearing the create form", async () => {
    sessionState.role = "instructor";
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/campaigns" && options?.method === "POST") {
        return Promise.reject(new Error("Campaign code already exists."));
      }
      return Promise.resolve([activeCampaign]);
    });
    renderPage();

    await screen.findByText("Stability series");
    fireEvent.change(screen.getByLabelText(/^Campaign code/), {
      target: { value: "stability-2026" },
    });
    fireEvent.change(screen.getByLabelText(/^Display name/), {
      target: { value: "Duplicate series" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Create Campaign" }).closest("form")!);

    expect(await screen.findByRole("alert")).toHaveTextContent("Campaign code already exists.");
    expect(screen.getByLabelText(/^Campaign code/)).toHaveValue("stability-2026");
    expect(screen.getByLabelText(/^Display name/)).toHaveValue("Duplicate series");
  });
});
