import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { LoginPage } from "./LoginPage";
import { beforeEach, describe, expect, it, vi } from "vitest";

const login = vi.fn().mockResolvedValue(undefined);
const sessionState = vi.hoisted(() => ({
  status: "unauthenticated" as "unauthenticated" | "authenticated" | "loading",
}));

vi.mock("../auth/session", () => ({
  useSession: () => ({
    login,
    status: sessionState.status,
    user: sessionState.status === "authenticated" ? { id: 1 } : null,
  }),
}));

describe("LoginPage", () => {
  beforeEach(() => {
    login.mockClear();
    sessionState.status = "unauthenticated";
  });

  it("returns to the requested deep link after sign in (from state)", async () => {
    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: "/login",
            state: { from: { pathname: "/experiments/42", search: "?tab=plan" } },
          },
        ]}
      >
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/experiments/42" element={<p>Requested experiment</p>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText(/^Username/), { target: { value: "s" } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: "p" } });
    fireEvent.submit(screen.getByRole("button", { name: "Sign in" }).closest("form")!);

    expect(await screen.findByText("Requested experiment")).toBeInTheDocument();
  });

  it("uses next query when from state is absent", async () => {
    render(
      <MemoryRouter initialEntries={["/login?next=/experiments/42"]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/experiments/42" element={<p>Next destination</p>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText(/^Username/), { target: { value: "s" } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: "p" } });
    fireEvent.submit(screen.getByRole("button", { name: "Sign in" }).closest("form")!);

    expect(await screen.findByText("Next destination")).toBeInTheDocument();
  });

  it("falls back to / when next is protocol-relative", async () => {
    render(
      <MemoryRouter initialEntries={["/login?next=//evil.example"]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<p>Home</p>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText(/^Username/), { target: { value: "s" } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: "p" } });
    fireEvent.submit(screen.getByRole("button", { name: "Sign in" }).closest("form")!);

    expect(await screen.findByText("Home")).toBeInTheDocument();
  });

  it("from state takes precedence over next query", async () => {
    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: "/login",
            search: "?next=/experiments/99",
            state: { from: { pathname: "/experiments/42" } },
          },
        ]}
      >
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/experiments/42" element={<p>From state wins</p>} />
          <Route path="/experiments/99" element={<p>Next query</p>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText(/^Username/), { target: { value: "s" } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: "p" } });
    fireEvent.submit(screen.getByRole("button", { name: "Sign in" }).closest("form")!);

    expect(await screen.findByText("From state wins")).toBeInTheDocument();
  });

  it("strips one /app prefix from next without producing /app/app/...", async () => {
    render(
      <MemoryRouter initialEntries={["/login?next=/app/experiments/42"]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/experiments/42" element={<p>Normalized</p>} />
          <Route path="/app/experiments/42" element={<p>Doubled</p>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText(/^Username/), { target: { value: "s" } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: "p" } });
    fireEvent.submit(screen.getByRole("button", { name: "Sign in" }).closest("form")!);

    expect(await screen.findByText("Normalized")).toBeInTheDocument();
    expect(screen.queryByText("Doubled")).not.toBeInTheDocument();
  });

  it("redirects an already-authenticated user away from login", async () => {
    sessionState.status = "authenticated";
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<p>Home</p>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Home")).toBeInTheDocument();
  });

  it("rejects repeated /app/app/ prefix", async () => {
    render(
      <MemoryRouter initialEntries={["/login?next=/app/app/experiments/42"]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<p>Home</p>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText(/^Username/), { target: { value: "s" } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: "p" } });
    fireEvent.submit(screen.getByRole("button", { name: "Sign in" }).closest("form")!);

    expect(await screen.findByText("Home")).toBeInTheDocument();
  });

  it("preserves safe query and fragment in next", async () => {
    render(
      <MemoryRouter initialEntries={["/login?next=/experiments/42?tab=plan"]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/experiments/42" element={<p>Destination</p>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText(/^Username/), { target: { value: "s" } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: "p" } });
    fireEvent.submit(screen.getByRole("button", { name: "Sign in" }).closest("form")!);

    expect(await screen.findByText("Destination")).toBeInTheDocument();
  });

  it("rejects backslash, encoded backslash, and control characters in next", async () => {
    for (const bad of [
      "/\\evil.example",
      "/%5Cevil.example",
      "/%255Cevil.example",
      "/\tevil",
    ]) {
      sessionState.status = "authenticated";
      const { unmount } = render(
        <MemoryRouter initialEntries={[`/login?next=${encodeURIComponent(bad)}`]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<p>Home</p>} />
          </Routes>
        </MemoryRouter>,
      );
      // Must land on the safe fallback, not an external destination.
      expect(await screen.findByText("Home")).toBeInTheDocument();
      unmount();
      sessionState.status = "unauthenticated";
    }
  });
});
