import { useEffect, useState, type FormEvent } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../auth/session";
import { FormField } from "../components/FormField";

const FORBIDDEN_PATHS = ["/api", "/healthz", "/login", "/app/login"];
const EXPORT_PATTERN = /\/export\.(json|pdf)$/;

/** Sanitize an app-internal path for React Router navigation.
 * Strips at most one leading `/app` prefix (so a `next` value from a 401
 * redirect works), rejects repeated `/app/app/...` prefixes, rejects
 * unsafe/non-UI destinations, and falls back to `/`.
 *
 * The pathname is validated separately from query/fragment: an export URL
 * with `?query` or `#fragment` is still rejected by EXPORT_PATTERN.
 *
 * The result is passed directly to `navigate()` — BrowserRouter with
 * `basename="/app"` prepends `/app` automatically.
 */
function sanitizeNext(next: string | null): string {
  if (!next) return "/";
  let path = next;
  // Strip at most one leading /app prefix
  if (path.startsWith("/app/")) {
    path = path.slice("/app".length);
  } else if (path === "/app") {
    path = "/";
  }
  // Reject repeated /app prefixes (/app/app/experiments/42)
  if (path.startsWith("/app/") || path === "/app") {
    return "/";
  }
  // Split pathname from query/fragment for separate validation
  const hashIndex = path.indexOf("#");
  const queryIndex = path.indexOf("?");
  const pathnameEnd = Math.min(
    hashIndex === -1 ? Infinity : hashIndex,
    queryIndex === -1 ? Infinity : queryIndex,
  );
  const pathname = pathnameEnd === Infinity ? path : path.slice(0, pathnameEnd);
  const suffix = pathnameEnd === Infinity ? "" : path.slice(pathnameEnd);
  // Reject backslashes (including URL-encoded and double-encoded variants),
  // control characters, protocol-relative paths, and scheme-prefixed URLs.
  const lowerPath = path.toLowerCase();
  if (
    path.includes("\\") ||
    pathname.includes("\\") ||
    lowerPath.includes("%5c") ||
    lowerPath.includes("%255c") ||
    [...path].some((ch) => ch.charCodeAt(0) < 0x20) ||
    !pathname.startsWith("/") ||
    pathname.startsWith("//") ||
    pathname.toLowerCase().startsWith("http://") ||
    pathname.toLowerCase().startsWith("https://") ||
    EXPORT_PATTERN.test(pathname) ||
    EXPORT_PATTERN.test(path) ||
    FORBIDDEN_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"))
  ) {
    return "/";
  }
  return pathname + suffix;
}

export function LoginPage() {
  const { login, status } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function computeDestination(): string {
    const state = location.state as {
      from?: { pathname?: string; search?: string; hash?: string };
    } | null;
    const fromState = state?.from;
    if (fromState?.pathname) {
      return sanitizeNext(
        `${fromState.pathname}${fromState.search ?? ""}${fromState.hash ?? ""}`,
      );
    }
    return sanitizeNext(searchParams.get("next"));
  }

  // Redirect already-authenticated users away from the login form.
  useEffect(() => {
    if (status === "authenticated") {
      navigate(computeDestination(), { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      navigate(computeDestination(), { replace: true });
    } catch (submittedError) {
      setError(
        submittedError instanceof Error
          ? submittedError.message
          : "Sign in failed. Please try again.",
      );
      setPassword("");
    } finally {
      setSubmitting(false);
    }
  }

  if (status === "loading") {
    return <div className="app-loading" role="status">Loading…</div>;
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={handleSubmit} noValidate>
        <h1 className="login-card__title">Sign in</h1>
        <p className="login-card__subtitle">
          Perovskite solar-cell fabrication workflow
        </p>
        {error ? (
          <p className="login-card__error" role="alert">
            {error}
          </p>
        ) : null}
        <FormField label="Username" htmlFor="login-username" required>
          <input
            id="login-username"
            className="text-input"
            name="username"
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            required
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </FormField>
        <FormField label="Password" htmlFor="login-password" required>
          <input
            id="login-password"
            className="text-input"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </FormField>
        <button
          type="submit"
          className="button button--primary button--block"
          disabled={submitting}
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
