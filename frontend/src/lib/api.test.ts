import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, csrfToken } from "./api";

function setCookie(name: string, value: string): void {
  Object.defineProperty(document, "cookie", {
    configurable: true,
    get: () => `${name}=${value}`,
  });
}

describe("csrfToken", () => {
  it("reads the host-prefixed CSRF cookie first", () => {
    setCookie("__Host-perovskite_csrf", "host-token");
    expect(csrfToken()).toBe("host-token");
  });

  it("falls back to the plain cookie", () => {
    setCookie("perovskite_csrf", "plain-token");
    expect(csrfToken()).toBe("plain-token");
  });

  it("returns an empty string when no CSRF cookie exists", () => {
    setCookie("other", "value");
    expect(csrfToken()).toBe("");
  });
});

describe("apiFetch", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    setCookie("perovskite_csrf", "csrf-value");
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("serializes JSON bodies and attaches the CSRF header on writes", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await apiFetch("/api/example", { method: "POST", body: { value: 1 } });

    const [path, init] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(path).toBe("/api/example");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(init.headers["X-CSRF-Token"]).toBe("csrf-value");
    expect(JSON.parse(init.body)).toEqual({ value: 1 });
  });

  it("does not attach the CSRF header to GET requests", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } }),
    );

    await apiFetch("/api/experiments");

    const [, init] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(init.headers["X-CSRF-Token"]).toBeUndefined();
  });

  it("normalizes a FastAPI detail string into an ApiError", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "invalid or missing CSRF token" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const failure = apiFetch("/api/example", { method: "POST", body: {} });
    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({
      status: 403,
      message: "invalid or missing CSRF token",
    });
  });

  it("prefixes 422 items with their field location so the operator can find the input", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: [
            {
              type: "greater_than_equal",
              loc: ["body", "deposition_process", "vcd_stages", 2, "seconds"],
              msg: "Input should be greater than or equal to 1",
            },
            {
              type: "greater_than",
              loc: ["body", "gas_backfill_stages", 0, "flow_sccm"],
              msg: "Input should be greater than 0",
            },
          ],
        }),
        { status: 422, headers: { "Content-Type": "application/json" } },
      ),
    );

    const failure = apiFetch("/api/example", { method: "POST", body: {} });
    await expect(failure).rejects.toMatchObject({
      status: 422,
      message:
        "deposition_process vcd_stages stage 3 seconds: Input should be greater than or equal to 1; " +
        "gas_backfill_stages stage 1 flow_sccm: Input should be greater than 0",
    });
  });

  it("redirects to login on 401 away from the login page", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "authentication required" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { pathname: "/app/experiments", search: "", assign },
    });

    await expect(apiFetch("/api/session")).rejects.toBeInstanceOf(ApiError);
    expect(assign).toHaveBeenCalledWith(
      expect.stringMatching(/^\/app\/login\?next=/),
    );
  });

  it("encodes the current app route as next on 401", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "authentication required" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { pathname: "/app/results/42", search: "?tab=curves", hash: "", assign },
    });

    await expect(apiFetch("/api/results/42")).rejects.toBeInstanceOf(ApiError);
    expect(assign).toHaveBeenCalledWith(
      `/app/login?next=${encodeURIComponent("/results/42?tab=curves")}`,
    );
  });

  it("encodes the current app route with hash as next on 401", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "authentication required" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { pathname: "/app/results/42", search: "?tab=curves", hash: "#chart", assign },
    });

    await expect(apiFetch("/api/results/42")).rejects.toBeInstanceOf(ApiError);
    expect(assign).toHaveBeenCalledWith(
      `/app/login?next=${encodeURIComponent("/results/42?tab=curves#chart")}`,
    );
  });

  it("does not redirect when already on the login page", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "authentication required" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { pathname: "/app/login", assign },
    });

    await expect(apiFetch("/api/session")).rejects.toBeInstanceOf(ApiError);
    expect(assign).not.toHaveBeenCalled();
  });

  it("returns undefined for 204 responses", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));

    const result = await apiFetch<void>("/api/auth/logout", { method: "POST" });
    expect(result).toBeUndefined();
  });
});