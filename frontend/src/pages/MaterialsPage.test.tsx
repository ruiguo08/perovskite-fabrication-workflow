import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../components/Toast";
import { MaterialsPage } from "./MaterialsPage";

const apiFetchMock = vi.hoisted(() => vi.fn());
const sessionState = vi.hoisted(() => ({
  role: "student" as "student" | "instructor" | "administrator",
}));

vi.mock("../lib/api", () => ({ apiFetch: apiFetchMock }));
vi.mock("../auth/session", () => ({
  useSession: () => ({
    user: {
      id: 2,
      username: "catalog-user",
      display_name: "Catalog User",
      role: sessionState.role,
      csrf_available: true,
    },
  }),
}));

const activeMaterial = {
  id: 11,
  category: "substrate",
  name: "FTO glass",
  formula: "SnO₂:F",
  cas_number: "",
  specification: { sheet_resistance: "7 ohm/sq" },
  status: "active",
  products: [
    {
      id: 21,
      vendor: "GreatCell Solar",
      catalog_number: "TEC7",
      specification: { thickness_mm: 2.2 },
      status: "active",
      created_at: "2026-08-01T08:00:00Z",
      updated_at: "2026-08-01T08:00:00Z",
    },
  ],
  created_at: "2026-08-01T08:00:00Z",
  updated_at: "2026-08-02T08:00:00Z",
};

const pendingMaterial = {
  ...activeMaterial,
  id: 12,
  category: "chemical",
  name: "Phenethylammonium iodide",
  formula: "C₈H₁₂IN",
  status: "pending",
  products: [],
};

function renderPage() {
  return render(
    <ToastProvider>
      <MaterialsPage />
    </ToastProvider>,
  );
}

describe("MaterialsPage", () => {
  beforeEach(() => {
    sessionState.role = "student";
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue([activeMaterial, pendingMaterial]);
  });

  it("gives students a proposal workflow without manager controls", async () => {
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/materials" && options?.method === "POST") {
        return Promise.resolve({
          ...pendingMaterial,
          id: 13,
          name: "Bathocuproine",
          formula: "C₂₆H₂₀N₂",
        });
      }
      return Promise.resolve([activeMaterial, pendingMaterial]);
    });
    renderPage();

    expect(await screen.findByText("FTO glass")).toBeInTheDocument();
    expect(screen.getByText("Phenethylammonium iodide")).toBeInTheDocument();
    expect(screen.queryByText("Edit material")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/status for FTO glass/i)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/^Material category/), {
      target: { value: "chemical" },
    });
    fireEvent.change(screen.getByLabelText(/^Material name/), {
      target: { value: "Bathocuproine" },
    });
    fireEvent.change(screen.getByLabelText("Formula"), {
      target: { value: "C₂₆H₂₀N₂" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit material for review" }));

    expect(await screen.findByText("Bathocuproine")).toBeInTheDocument();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/materials", {
      method: "POST",
      body: {
        category: "chemical",
        name: "Bathocuproine",
        formula: "C₂₆H₂₀N₂",
        cas_number: "",
        specification: {},
      },
    });
  });

  it("lets students propose a supplier product for an active material", async () => {
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/materials/11/products" && options?.method === "POST") {
        return Promise.resolve({
          ...activeMaterial,
          products: [
            ...activeMaterial.products,
            {
              ...activeMaterial.products[0],
              id: 22,
              vendor: "Ossila",
              catalog_number: "S111",
              status: "pending",
            },
          ],
        });
      }
      return Promise.resolve([activeMaterial]);
    });
    renderPage();

    await screen.findByText("FTO glass");
    const materialCard = screen.getByRole("article", { name: "FTO glass" });
    fireEvent.click(within(materialCard).getByText("Propose supplier product"));
    fireEvent.change(within(materialCard).getByLabelText(/^New vendor for FTO glass/), {
      target: { value: "Ossila" },
    });
    fireEvent.change(within(materialCard).getByLabelText(/^New catalog number for FTO glass/), {
      target: { value: "S111" },
    });
    fireEvent.click(within(materialCard).getByRole("button", { name: "Submit product for review" }));

    expect(await screen.findByText("Ossila")).toBeInTheDocument();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/materials/11/products", {
      method: "POST",
      body: { vendor: "Ossila", catalog_number: "S111", specification: {} },
    });
  });

  it.each(["instructor", "administrator"] as const)(
    "shows publishing controls to %s accounts",
    async (role) => {
      sessionState.role = role;
      apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
        if (path === "/api/materials/12" && options?.method === "PATCH") {
          return Promise.resolve({ ...pendingMaterial, status: "active" });
        }
        return Promise.resolve([activeMaterial, pendingMaterial]);
      });
      renderPage();

      expect(await screen.findAllByText("Edit material")).toHaveLength(2);
      const pendingCard = screen.getByRole("article", { name: "Phenethylammonium iodide" });
      fireEvent.click(within(pendingCard).getByText("Edit material"));
      fireEvent.change(within(pendingCard).getByLabelText(/^Status for Phenethylammonium iodide/), {
        target: { value: "active" },
      });
      fireEvent.click(within(pendingCard).getByRole("button", { name: "Save Phenethylammonium iodide" }));

      await waitFor(() => {
        expect(apiFetchMock).toHaveBeenCalledWith("/api/materials/12", {
          method: "PATCH",
          body: expect.objectContaining({ status: "active" }),
        });
      });
    },
  );
});
