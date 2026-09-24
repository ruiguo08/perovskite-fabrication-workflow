import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../components/Toast";
import { UsersPage } from "./UsersPage";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", () => ({ apiFetch: apiFetchMock }));

const administrator = {
  id: 1,
  username: "admin",
  display_name: "Administrator",
  role: "administrator",
  is_active: true,
  locked_until: null,
  last_login_at: "2026-08-12T08:00:00Z",
  password_changed_at: "2026-08-01T08:00:00Z",
  created_at: "2026-08-01T08:00:00Z",
  updated_at: "2026-08-12T08:00:00Z",
};

const student = {
  ...administrator,
  id: 2,
  username: "student-one",
  display_name: "Student One",
  role: "student",
  is_active: false,
  last_login_at: null,
};

function renderPage() {
  return render(<ToastProvider><UsersPage /></ToastProvider>);
}

describe("UsersPage", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue([administrator, student]);
  });

  it("lists account metadata without rendering secret fields", async () => {
    renderPage();

    expect(await screen.findByText("Student One")).toBeInTheDocument();
    expect(screen.getByText("Inactive")).toBeInTheDocument();
    expect(screen.queryByText(/password_hash/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/failed_login_count/i)).not.toBeInTheDocument();
    expect(screen.getAllByLabelText(/new password for/i)).toHaveLength(2);
    expect(screen.getByLabelText("New password for student-one")).toHaveValue("");
  });

  it("renders activity labels separately from their timestamp values", async () => {
    renderPage();

    await screen.findByText("Student One");
    expect(screen.getAllByText("Last login")).toHaveLength(2);
    expect(screen.getAllByText("Password changed")).toHaveLength(2);
  });

  it("creates an account and clears the temporary password", async () => {
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/users" && options?.method === "POST") {
        return Promise.resolve({ ...student, id: 3, username: "new-student", display_name: "New Student", is_active: true });
      }
      return Promise.resolve([administrator, student]);
    });
    renderPage();

    await screen.findByText("Student One");
    fireEvent.change(screen.getByLabelText(/^Username/), { target: { value: "new-student" } });
    fireEvent.change(screen.getByLabelText(/^Display name/), { target: { value: "New Student" } });
    fireEvent.change(screen.getByLabelText(/^Temporary password/), { target: { value: "Temporary password 2026" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("New Student")).toBeInTheDocument();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/users", {
      method: "POST",
      body: {
        username: "new-student",
        display_name: "New Student",
        password: "Temporary password 2026",
        role: "student",
      },
    });
    expect(screen.getByLabelText(/^Temporary password/)).toHaveValue("");
  });

  it("updates access and keeps self-deactivation errors inline", async () => {
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/users/2" && options?.method === "PATCH") {
        return Promise.resolve({ ...student, role: "instructor", is_active: true });
      }
      if (path === "/api/users/1" && options?.method === "PATCH") {
        return Promise.reject(new Error("you cannot deactivate your own account"));
      }
      return Promise.resolve([administrator, student]);
    });
    renderPage();

    const studentRow = await screen.findByRole("row", { name: /Student One/ });
    fireEvent.change(within(studentRow).getByLabelText("Role for student-one"), { target: { value: "instructor" } });
    fireEvent.click(within(studentRow).getByLabelText("Active account for student-one"));
    fireEvent.click(within(studentRow).getByRole("button", { name: "Save access for student-one" }));
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/api/users/2", {
      method: "PATCH",
      body: { role: "instructor", is_active: true },
    }));

    const adminRow = screen.getByRole("row", { name: /Administrator/ });
    fireEvent.click(within(adminRow).getByLabelText("Active account for admin"));
    fireEvent.click(within(adminRow).getByRole("button", { name: "Save access for admin" }));
    expect(await within(adminRow).findByRole("alert")).toHaveTextContent("you cannot deactivate your own account");
  });

  it("resets a password and immediately clears the field", async () => {
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/users/2/password" && options?.method === "POST") {
        return Promise.resolve(undefined);
      }
      return Promise.resolve([administrator, student]);
    });
    renderPage();

    const studentRow = await screen.findByRole("row", { name: /Student One/ });
    const input = within(studentRow).getByLabelText("New password for student-one");
    fireEvent.change(input, { target: { value: "Replacement password 2026" } });
    fireEvent.click(within(studentRow).getByRole("button", { name: "Reset password for student-one" }));

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/api/users/2/password", {
      method: "POST",
      body: { password: "Replacement password 2026" },
    }));
    expect(input).toHaveValue("");
  });
});
