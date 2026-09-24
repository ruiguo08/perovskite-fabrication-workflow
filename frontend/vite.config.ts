/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import type { ClientRequest, IncomingMessage, ServerResponse } from "node:http";

// The browser origin (localhost:5173 during development) differs from the
// FastAPI origin the proxy forwards to. http-proxy rewrites the Host header
// with `changeOrigin` but preserves the browser's Origin header, so the
// backend same-origin middleware would reject every state-changing dev
// request (login, logout, all POST/PUT/PATCH/DELETE APIs). Rewrite Origin to
// the API origin for proxied requests instead; the browser-driven
// `Sec-Fetch-Site` signal and the CSRF token are still enforced by the
// backend, and production has no proxy at all.
const PROXY_TARGET = process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000";

const PROXY_ROUTES = ["/api", "/healthz"];

// Narrow regex proxy rules for non-API export download URLs. These must reach
// the backend in dev so React <a href> export links work. Do NOT proxy every
// /experiments/* request — React routes like /app/experiments/... must remain
// handled by Vite/React.
const EXPORT_PATTERNS: string[] = [
  "^/experiments/\\d+/export\\.(json|pdf)$",
  "^/experiments/\\d+/batches/\\d+/export\\.(json|pdf)$",
];

function apiProxy() {
  return {
    target: PROXY_TARGET,
    changeOrigin: true,
    configure: (proxy: {
      on: (
        event: "proxyReq",
        handler: (
          proxyReq: ClientRequest,
          _req: IncomingMessage,
          _res: ServerResponse,
        ) => void,
      ) => void;
    }) => {
      proxy.on("proxyReq", (proxyReq) => {
        proxyReq.setHeader("Origin", PROXY_TARGET);
      });
    },
  };
}

// The built application is served by FastAPI under /app/ and packaged inside
// the Python wheel (docs/react-migration.md, method A). The Vite base must
// match so compiled assets are requested as /app/assets/... during both
// development (via the proxy) and production (self-hosted, CSP-safe).
export default defineConfig({
  base: "/app/",
  plugins: [react()],
  build: {
    outDir: "../src/web/static-app",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      ...Object.fromEntries(
        PROXY_ROUTES.map((route) => [route, apiProxy()]),
      ),
      ...Object.fromEntries(
        EXPORT_PATTERNS.map((pattern) => [pattern, apiProxy()]),
      ),
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});