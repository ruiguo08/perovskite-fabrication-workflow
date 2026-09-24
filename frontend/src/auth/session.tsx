import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { apiFetch, ApiError } from "../lib/api";

export type Role = "student" | "instructor" | "administrator";

export interface SessionUser {
  id: number;
  username: string;
  display_name: string;
  role: Role;
  csrf_available: boolean;
}

export type SessionStatus =
  | "loading"
  | "authenticated"
  | "unauthenticated"
  | "error";

interface LoginResult {
  id: number;
  username: string;
  display_name: string;
  role: Role;
  csrf_available: boolean;
}

interface SessionContextValue {
  user: SessionUser | null;
  status: SessionStatus;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const session = await apiFetch<SessionUser>("/api/session", {
        redirectOnUnauthorized: false,
      });
      setUser(session);
      setStatus("authenticated");
      setError(null);
    } catch (refreshError) {
      setUser(null);
      if (refreshError instanceof ApiError && refreshError.status === 401) {
        setStatus("unauthenticated");
        setError(null);
      } else {
        setStatus("error");
        setError(
          refreshError instanceof Error
            ? refreshError.message
            : "Unable to verify the current session.",
        );
      }
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(
    async (username: string, password: string) => {
      const csrf = await apiFetch<{ login_csrf_token: string }>(
        "/api/auth/login-csrf",
      );
      const session = await apiFetch<LoginResult>("/api/auth/login", {
        method: "POST",
        body: { username, password, login_csrf: csrf.login_csrf_token },
      });
      setUser(session);
      setStatus("authenticated");
      setError(null);
    },
    [],
  );

  const logout = useCallback(async () => {
    try {
      await apiFetch<void>("/api/auth/logout", { method: "POST" });
    } finally {
      setUser(null);
      setStatus("unauthenticated");
      setError(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, status, error, login, logout, refresh }),
    [user, status, error, login, logout, refresh],
  );

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (context === null) {
    throw new Error("useSession must be used within a SessionProvider");
  }
  return context;
}
