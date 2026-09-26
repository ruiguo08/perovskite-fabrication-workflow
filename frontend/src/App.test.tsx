import { fireEvent, render, screen } from "@testing-library/react";
import App from "./App";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sessionState = vi.hoisted(() => ({
  status: "authenticated" as "authenticated" | "unauthenticated",
  role: "student" as "student" | "instructor" | "administrator",
}));

vi.mock("./auth/session", () => ({
  SessionProvider: ({ children }: { children: React.ReactNode }) => children,
  useSession: () => ({
    user: {
      id: 1,
      username: "student-one",
      display_name: "Student One",
      role: sessionState.role,
      csrf_available: true,
    },
    status: sessionState.status,
    login: vi.fn().mockImplementation(async () => {
      sessionState.status = "authenticated";
    }),
    logout: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.mock("./pages/OverviewPage", () => ({
  OverviewPage: () => <p>Overview page</p>,
}));

vi.mock("./pages/ExperimentDetailPage", () => ({
  ExperimentDetailPage: () => <p>React experiment detail</p>,
}));

describe("application route authorization", () => {
  beforeEach(() => {
    sessionState.status = "authenticated";
    sessionState.role = "student";
    window.history.replaceState({}, "", "/app/users");
  });

  it("does not render administrator routes for a student", async () => {
    render(<App />);

    expect(await screen.findByText(/not authorized/i)).toBeInTheDocument();
    expect(
      screen.queryByText("Users is not part of the current migration phase"),
    ).not.toBeInTheDocument();
  });

  it("opens the workflow guide for a student and explains the analysis gate", async () => {
    window.history.replaceState({}, "", "/app/workflow");

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Workflow guide" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Workflow guide" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Start an experiment" })).toHaveAttribute(
      "href",
      "/app/experiments/new",
    );
    expect(screen.getByText(/J-V curves are available immediately after upload/i)).toBeInTheDocument();
    expect(screen.getByText(/save assignments before group statistics and uniformity/i)).toBeInTheDocument();
  });

  it("preserves an unauthenticated deep link through sign in", async () => {
    sessionState.status = "unauthenticated";
    window.history.replaceState({}, "", "/app/experiments/42?tab=plan");

    render(<App />);
    fireEvent.change(await screen.findByLabelText(/^Username/), {
      target: { value: "student-one" },
    });
    fireEvent.change(screen.getByLabelText(/^Password/), {
      target: { value: "password" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Sign in" }).closest("form")!);

    expect(await screen.findByText("React experiment detail")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/app/experiments/42");
    expect(window.location.search).toBe("?tab=plan");
  });
});
