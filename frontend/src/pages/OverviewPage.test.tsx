import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { OverviewPage } from "./OverviewPage";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.hoisted(() => vi.fn());
const sessionState = vi.hoisted(() => ({
  role: "instructor" as "student" | "instructor" | "administrator",
}));

vi.mock("../lib/api", () => ({ apiFetch: apiFetchMock }));
vi.mock("../auth/session", () => ({
  useSession: () => ({
    user: { id: 1, username: "overview-user", display_name: "Overview User", role: sessionState.role, csrf_available: true },
  }),
}));

function renderPage() {
  return render(<MemoryRouter><OverviewPage /></MemoryRouter>);
}

function experiment(id: number, code: string, updatedAt: string) {
  return {
    id,
    status: "suggested",
    created_at: updatedAt,
    updated_at: updatedAt,
    campaign_id: "campaign-a",
    experiment_code: code,
    series_version: id,
    plan_type: "standalone",
    plan_status: "draft",
    recipe: { device_recipe: null },
  };
}

describe("OverviewPage", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    sessionState.role = "instructor";
  });

  it("shows a loading state while overview requests are pending", () => {
    apiFetchMock.mockReturnValue(new Promise(() => undefined));

    renderPage();

    expect(
      screen.getByRole("status", { name: "Loading overview data" }),
    ).toBeInTheDocument();
  });

  it("orders recent experiments by updated time", async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === "/api/experiments") {
        return Promise.resolve([
          experiment(99, "older-record", "2026-08-01T08:00:00Z"),
          experiment(1, "newer-record", "2026-08-12T08:00:00Z"),
        ]);
      }
      if (path === "/api/device-layouts") {
        return Promise.resolve([{ code: "15x15_dual_005" }]);
      }
      if (path === "/api/campaigns") {
        return Promise.resolve([{ code: "campaign-a", display_name: "Campaign A", status: "active" }]);
      }
      return Promise.resolve([]);
    });

    renderPage();

    const table = await screen.findByRole("table", {
      name: "Recent experiments",
    });
    const dataRows = within(table).getAllByRole("row").slice(1);
    expect(dataRows).toHaveLength(2);
    expect(within(dataRows[0]).getByText("newer-record")).toBeInTheDocument();
  });

  it("shows the first-use setup checklist when layouts and campaigns are missing", async () => {
    apiFetchMock.mockResolvedValue([]);

    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Finish the first-use setup" }),
    ).toBeInTheDocument();
    expect(screen.getByText("No device layouts yet")).toBeInTheDocument();
    expect(screen.getByText("No active campaign yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open device layouts" })).toHaveAttribute("href", "/device-layouts");
    expect(screen.getByRole("link", { name: "Open campaigns" })).toHaveAttribute("href", "/campaigns");
  });

  it("hides the setup checklist once a layout and an active campaign exist", async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === "/api/device-layouts") {
        return Promise.resolve([{ code: "15x15_dual_005" }]);
      }
      if (path === "/api/campaigns") {
        return Promise.resolve([{ code: "campaign-a", display_name: "Campaign A", status: "active" }]);
      }
      if (path === "/api/experiments") {
        return Promise.resolve([experiment(1, "only-record", "2026-08-12T08:00:00Z")]);
      }
      return Promise.resolve([]);
    });

    renderPage();

    await screen.findByRole("table", { name: "Recent experiments" });
    expect(screen.queryByRole("heading", { name: "Finish the first-use setup" })).not.toBeInTheDocument();
  });

  it("tells students who to ask instead of linking them to admin pages", async () => {
    sessionState.role = "student";
    apiFetchMock.mockResolvedValue([]);

    renderPage();

    expect(await screen.findByText("No device layouts yet")).toBeInTheDocument();
    expect(screen.getByText(/Ask an administrator to create the first device layout/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Open device layouts" })).not.toBeInTheDocument();
  });
});
