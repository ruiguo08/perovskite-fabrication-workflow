import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BaselineAuthoring } from "./BaselineAuthoring";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api", () => ({ apiFetch: apiFetchMock }));

const sessionUser = vi.hoisted(() => ({
  id: 101,
  username: "student-one",
  display_name: "Student One",
  role: "student" as "student" | "instructor" | "administrator",
  csrf_available: true,
}));
vi.mock("../../auth/session", () => ({
  useSession: () => ({ user: sessionUser, status: "authenticated", error: null }),
}));

function mockCatalogs(options: { failMaterials?: boolean } = {}) {
  apiFetchMock.mockImplementation(async (path: string) => {
    if (path === "/api/layer-presets") return [];
    if (path === "/api/materials") {
      if (options.failMaterials) {
        throw new Error("materials catalog unavailable");
      }
      return [];
    }
    if (path === "/api/device-layouts") return [];
    return undefined;
  });
}

function storedDraft(): { name: string } | null {
  const raw = window.localStorage.getItem("perovskite-bo:baseline-draft:101");
  if (raw === null) return null;
  const parsed = JSON.parse(raw) as { draft?: { name?: unknown } };
  return parsed.draft && typeof parsed.draft.name === "string" ? { name: parsed.draft.name } : null;
}

describe("BaselineAuthoring catalogs", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    window.localStorage.clear();
  });

  it("shows an actionable error and retry when a catalog fails, never a stuck spinner", async () => {
    mockCatalogs({ failMaterials: true });
    render(<BaselineAuthoring scope="shared" onSubmit={vi.fn()} />);

    expect(
      await screen.findByText(/unable to load authoring catalogs/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/loading authoring catalogs/i),
    ).not.toBeInTheDocument();

    mockCatalogs();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => {
      expect(screen.getByLabelText(/new baseline name/i)).toBeInTheDocument();
    });
  });

  it("renders the authoring form once catalogs resolve", async () => {
    mockCatalogs();
    render(<BaselineAuthoring scope="shared" onSubmit={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByLabelText(/new baseline name/i)).toBeInTheDocument();
    });
  });
});

describe("BaselineAuthoring draft persistence", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    mockCatalogs();
    window.localStorage.clear();
  });

  it("keeps the entered name when the page is left and reopened", async () => {
    const { unmount } = render(<BaselineAuthoring scope="personal" onSubmit={vi.fn()} />);
    const nameInput = await screen.findByLabelText(/new baseline name/i);
    fireEvent.change(nameInput, { target: { value: "FA-remainder baseline" } });
    expect(storedDraft()?.name).toBe("FA-remainder baseline");
    unmount();

    render(<BaselineAuthoring scope="personal" onSubmit={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByLabelText(/new baseline name/i)).toHaveValue("FA-remainder baseline");
    });
    expect(screen.getByRole("button", { name: /discard draft/i })).toBeInTheDocument();
  });

  it("ignores an empty stored draft instead of announcing a restore", async () => {
    render(<BaselineAuthoring scope="personal" onSubmit={vi.fn()} />);
    await screen.findByLabelText(/new baseline name/i);
    expect(screen.queryByRole("button", { name: /discard draft/i })).not.toBeInTheDocument();
  });

  it("discards the restored draft and starts from a blank form", async () => {
    window.localStorage.setItem(
      "perovskite-bo:baseline-draft:101",
      JSON.stringify({
        version: 1,
        draft: {
          name: "stale draft",
          draft: {
          campaign_id: "",
          source_baseline_version_id: null,
          source_baseline_name: null,
          setup_mode: "blank",
          junction_type: "single_junction",
          perovskite_bandgap: "normal_bandgap",
          architecture: "pin",
          substrate: { material: "ITO", vendor: "", type_number: "", width_mm: 0, length_mm: 0 },
          layers: [],
          deposition_process: {
            method: "spin_coating_vcd",
            spin_steps: [],
            vcd_stages: [],
            gas_backfill_stages: [],
            vcd_step_sequence: [],
            anneal_steps: [],
          },
          plan_type: "comparative",
          conditions: [],
        },
        },
      }),
    );

    render(<BaselineAuthoring scope="personal" onSubmit={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByLabelText(/new baseline name/i)).toHaveValue("stale draft");
    });
    fireEvent.click(screen.getByRole("button", { name: /discard draft/i }));
    await waitFor(() => {
      expect(screen.getByLabelText(/new baseline name/i)).toHaveValue("");
      expect(screen.queryByRole("button", { name: /discard draft/i })).not.toBeInTheDocument();
    });
    expect(storedDraft()).toBeNull();
  });
});
