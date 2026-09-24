import { useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useSession, type Role } from "../auth/session";
import { useToast } from "./Toast";
import { titleCase } from "../lib/format";

const ROLE_RANK: Record<Role, number> = {
  student: 1,
  instructor: 2,
  administrator: 3,
};

interface NavItemDef {
  label: string;
  /** React route path relative to /app; overrides legacyPath when present. */
  path?: string;
  /** Full legacy URL used until the React route exists in a later phase. */
  legacyPath?: string;
  /** Minimum role that may see the item. */
  minRole?: Role;
  /** Marked until a React route (or legacy page) exists for it. */
  disabled?: boolean;
}

const NAV_GROUPS: { label: string; items: NavItemDef[] }[] = [
  {
    label: "Laboratory",
    items: [
      { label: "Overview", path: "/" },
      { label: "Experiments", path: "/experiments" },
      { label: "Fabrication batches", path: "/fabrication-batches" },
      { label: "Results", path: "/results" },
    ],
  },
  {
    label: "Library",
    items: [
      { label: "Materials", path: "/materials" },
      { label: "Layer presets", path: "/layer-presets" },
      { label: "Baselines", path: "/baselines" },
      { label: "Device layouts", path: "/device-layouts" },
    ],
  },
  {
    label: "Management",
    items: [
      { label: "Campaigns", path: "/campaigns" },
      { label: "Review queue", disabled: true, minRole: "instructor" },
      { label: "Users", path: "/users", minRole: "administrator" },
    ],
  },
];

function canSee(item: NavItemDef, role: Role): boolean {
  const minimum = item.minRole ? ROLE_RANK[item.minRole] : 1;
  return ROLE_RANK[role] >= minimum;
}

export function AppShell() {
  const { user } = useSession();
  const location = useLocation();
  const { show: showToast } = useToast();
  if (!user) {
    return null;
  }

  return (
    <div className="shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <aside className="shell__nav">
        <Link to="/" className="shell__brand">
          <span className="shell__brand-title">Perovskite Solar Cell</span>
          <span className="shell__brand-subtitle">Fabrication Workflow</span>
        </Link>
        <nav aria-label="Primary">
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="nav-group">
              <h2 className="nav-group__label">{group.label}</h2>
              <ul className="nav-group__list">
                {group.items
                  .filter((item) => canSee(item, user.role))
                  .map((item) => {
                    // A nav item is active when the current path's first
                    // segment matches the item's path, so /experiments/6/batches/1
                    // highlights "Experiments" while the run-sheet route
                    // (/experiments/:id/batches/:batchId) is excluded and
                    // reported by pathSegments below as "Fabrication batches".
                    const active =
                      item.path !== undefined && item.path !== "/"
                        ? location.pathname.startsWith(item.path)
                        : location.pathname === "/";
                    const effectiveActive =
                      item.path === "/experiments" &&
                      /^\/experiments\/[^/]+\/batches(\/|$)/.test(location.pathname)
                        ? false
                        : item.path === "/fabrication-batches" &&
                            /^\/experiments\/[^/]+\/batches(\/|$)/.test(location.pathname)
                          ? true
                          : active;
                    if (item.disabled) {
                      return (
                        <li key={item.label}>
                          <button
                            type="button"
                            className="nav-item nav-item--disabled"
                            aria-disabled="true"
                            title="Becomes available in a later migration phase"
                            onClick={() =>
                              showToast(
                                `${item.label} becomes available in a later migration phase.`,
                                "info",
                              )
                            }
                          >
                            {item.label}
                          </button>
                        </li>
                      );
                    }
                    if (item.path !== undefined) {
                      return (
                        <li key={item.label}>
                          <Link
                            to={item.path}
                            className={`nav-item${effectiveActive ? " nav-item--active" : ""}`}
                            aria-current={effectiveActive ? "page" : undefined}
                          >
                            {item.label}
                          </Link>
                        </li>
                      );
                    }
                    return (
                      <li key={item.label}>
                        <a className="nav-item" href={item.legacyPath}>
                          {item.label}
                        </a>
                      </li>
                    );
                  })}
              </ul>
            </div>
          ))}
        </nav>
      </aside>
      <div className="shell__main">
        <header className="topbar">
          <span className="topbar__role">
            {titleCase(user.role)}
          </span>
          <span className="topbar__user">{user.display_name}</span>
          <LogoutButton />
        </header>
        <main id="main-content" className="shell__content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function LogoutButton() {
  const { logout } = useSession();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLogout() {
    setSubmitting(true);
    setError(null);
    try {
      await logout();
    } catch (caught) {
      // The server session may still be active; show an actionable error
      // instead of silently navigating away or swallowing the rejection.
      setError(caught instanceof Error ? caught.message : "Unable to log out.");
      setSubmitting(false);
      return;
    }
    navigate("/login", { replace: true });
  }

  return (
    <div className="logout-control">
      <button
        type="button"
        className="button button--secondary button--small"
        disabled={submitting}
        onClick={() => void handleLogout()}
      >
        {submitting ? "Logging out…" : "Log out"}
      </button>
      {error ? (
        <p className="inline-form-error" role="alert">
          {error}{" "}
          <button
            type="button"
            className="button button--link"
            onClick={() => void handleLogout()}
          >
            Retry
          </button>
        </p>
      ) : null}
    </div>
  );
}
