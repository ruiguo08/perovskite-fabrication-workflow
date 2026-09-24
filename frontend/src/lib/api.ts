/**
 * Same-origin API client for the FastAPI backend.
 *
 * - Sends session cookies with `credentials: "same-origin"`.
 * - Attaches the CSRF cookie value as `X-CSRF-Token` on state-changing
 *   requests (the CSRF cookie is intentionally not HttpOnly).
 * - Normalizes FastAPI `{detail: ...}` errors into a readable message.
 * - Redirects to the login page when a request is rejected with 401, unless
 *   the login page is already active (avoids a redirect loop during login).
 */

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** JSON body; serialized automatically. Mutually exclusive with `multipart`. */
  body?: unknown;
  /** Raw form body for multipart uploads. Mutually exclusive with `body`. */
  multipart?: FormData;
  /** Disable global login navigation when the caller owns 401 handling. */
  redirectOnUnauthorized?: boolean;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const CSRF_COOKIE_NAMES = ["__Host-perovskite_csrf", "perovskite_csrf"];

function readCookie(name: string): string | null {
  const prefix = `${name}=`;
  for (const part of document.cookie.split(";")) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length));
    }
  }
  return null;
}

export function csrfToken(): string {
  for (const name of CSRF_COOKIE_NAMES) {
    const value = readCookie(name);
    if (value) {
      return value;
    }
  }
  return "";
}

/** Human-readable field location for a FastAPI 422 error item, e.g.
 * ["body", "deposition_process", "vcd_stages", 2, "seconds"] ->
 * "deposition_process vcd_stages stage 3 seconds". Body/query/path markers
 * are dropped because they carry no meaning for the operator; array indexes
 * are rendered 1-based to match the stage rows the operator sees. */
function formatErrorLocation(location: unknown): string | null {
  if (!Array.isArray(location)) return null;
  const segments = location
    .filter((part) => typeof part === "string" || typeof part === "number")
    .filter((part) => part !== "body" && part !== "query" && part !== "path");
  const parts: string[] = [];
  for (const part of segments) {
    if (typeof part === "number") {
      if (parts.length > 0) {
        parts[parts.length - 1] = `${parts[parts.length - 1]} stage ${part + 1}`;
      }
    } else {
      parts.push(part);
    }
  }
  return parts.length > 0 ? parts.join(" ") : null;
}

function detailMessage(detail: unknown): string | null {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== "object" || !("msg" in item)) return null;
        const message = String((item as { msg: unknown }).msg);
        const record = item as { loc?: unknown };
        const location = formatErrorLocation(record.loc);
        return location ? `${location}: ${message}` : message;
      })
      .filter((message): message is string => message !== null);
    if (messages.length > 0) {
      return messages.join("; ");
    }
  }
  return null;
}

function redirectToLogin(): void {
  if (!window.location.pathname.startsWith("/app/login")) {
    let currentPath =
      window.location.pathname + window.location.search + window.location.hash;
    // Strip one leading /app prefix so the next value is app-internal
    // (BrowserRouter with basename="/app" prepends /app on navigation).
    if (currentPath.startsWith("/app/")) {
      currentPath = currentPath.slice("/app".length);
    } else if (currentPath === "/app") {
      currentPath = "/";
    }
    const params = new URLSearchParams({ next: currentPath });
    window.location.assign(`/app/login?${params.toString()}`);
  }
}

export async function apiFetch<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {};
  let payload: BodyInit | undefined;

  if (options.multipart !== undefined) {
    payload = options.multipart;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(options.body);
  }

  const token = csrfToken();
  if (token && method !== "GET") {
    headers["X-CSRF-Token"] = token;
  }

  const response = await fetch(path, {
    method,
    headers,
    body: payload,
    credentials: "same-origin",
  });

  if (response.status === 401 && options.redirectOnUnauthorized !== false) {
    redirectToLogin();
  }
  if (!response.ok) {
    let detail: unknown = null;
    try {
      const data: unknown = await response.json();
      if (data && typeof data === "object" && "detail" in data) {
        detail = (data as { detail: unknown }).detail;
      }
    } catch {
      // Non-JSON error body; fall through to the status-based message.
    }
    const message =
      detailMessage(detail) ?? `Request failed (${response.status})`;
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
