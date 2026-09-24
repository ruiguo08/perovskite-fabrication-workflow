import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./AppShell";
import { ToastProvider } from "./Toast";
import { beforeEach, describe, expect, it, vi } from "vitest";

let resolveLogout: (() => void) | null = null;
const logout = vi.fn(
  () =>
    new Promise<void>((resolve) => {
      resolveLogout = resolve;
    }),
);

vi.mock("../auth/session", () => ({
  useSession: () => ({
    user: {
      id: 1,
      username: "student-one",
      display_name: "Student One",
      role: "student",
      csrf_available: true,
    },
    status: "authenticated",
    login: vi.fn(),
    logout,
    refresh: vi.fn(),
  }),
}));

describe("AppShell", () => {
  beforeEach(() => {
    logout.mockClear();
    resolveLogout = null;
  });

  it("does not leave the authenticated route until logout finishes", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <ToastProvider>
          <Routes>
          <Route element={<AppShell />}>
            <Route index element={<p>Authenticated content</p>} />
          </Route>
          <Route path="/login" element={<p>Login route</p>} />
          </Routes>
        </ToastProvider>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Log out" }));
    expect(screen.getByText("Authenticated content")).toBeInTheDocument();

    resolveLogout?.();

    expect(await screen.findByText("Login route")).toBeInTheDocument();
  });

  it("provides a skip link to the main content", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <ToastProvider>
          <Routes>
          <Route element={<AppShell />}>
            <Route index element={<p>Authenticated content</p>} />
          </Route>
          </Routes>
        </ToastProvider>
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute(
      "href",
      "#main-content",
    );
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });

  it("uses the complete solar-cell workflow brand", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <ToastProvider>
          <Routes>
          <Route element={<AppShell />}>
            <Route index element={<p>Authenticated content</p>} />
          </Route>
          </Routes>
        </ToastProvider>
      </MemoryRouter>,
    );

    expect(screen.getByText("Perovskite Solar Cell")).toBeInTheDocument();
    expect(screen.getByText("Fabrication Workflow")).toBeInTheDocument();
  });

  it("shows an actionable error and retry when logout fails, without navigating away", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <ToastProvider>
          <Routes>
          <Route element={<AppShell />}>
            <Route index element={<p>Authenticated content</p>} />
          </Route>
          <Route path="/login" element={<p>Login route</p>} />
          </Routes>
        </ToastProvider>
      </MemoryRouter>,
    );

    logout.mockImplementationOnce(() => Promise.reject(new Error("logout endpoint down")));
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    // The error surfaces; the user stays on the authenticated route and can retry.
    expect(await screen.findByText(/logout endpoint down|unable to log out/i)).toBeInTheDocument();
    expect(screen.getByText("Authenticated content")).toBeInTheDocument();
    expect(screen.queryByText("Login route")).not.toBeInTheDocument();

    // Retry (the visible action button is still "Retry") succeeds and
    // navigates to login.
    logout.mockImplementationOnce(() => Promise.resolve());
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findByText("Login route")).toBeInTheDocument();
  });
});
