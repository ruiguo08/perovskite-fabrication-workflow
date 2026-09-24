import { useCallback, useMemo, useState, type FormEvent } from "react";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { FormField } from "../components/FormField";
import { InlineFormError } from "../components/InlineFormError";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { apiFetch } from "../lib/api";
import { formatDateTime, titleCase } from "../lib/format";
import { useApiResource } from "../lib/useApiResource";
import type { Role, UserAccount } from "../types/api";

const ROLES: Role[] = ["student", "instructor", "administrator"];

function sortAccounts(accounts: UserAccount[]): UserAccount[] {
  return [...accounts].sort((left, right) => left.username.localeCompare(right.username));
}

export function UsersPage() {
  const { show } = useToast();
  const loadUsers = useCallback(() => apiFetch<UserAccount[]>("/api/users"), []);
  const resource = useApiResource(loadUsers);
  const [users, setUsers] = useState<UserAccount[] | null>(null);
  const rows = useMemo(() => sortAccounts(users ?? resource.data ?? []), [users, resource.data]);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("student");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function replaceUser(replacement: UserAccount) {
    setUsers((current) => sortAccounts((current ?? rows).some((account) => account.id === replacement.id)
      ? (current ?? rows).map((account) => account.id === replacement.id ? replacement : account)
      : [...(current ?? rows), replacement]));
  }

  async function createAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const created = await apiFetch<UserAccount>("/api/users", {
        method: "POST",
        body: {
          username: username.trim(),
          display_name: displayName.trim(),
          password,
          role,
        },
      });
      replaceUser(created);
      setUsername("");
      setDisplayName("");
      setRole("student");
      show("Account created.", "success");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create the account.");
    } finally {
      setPassword("");
      setSubmitting(false);
    }
  }

  if (resource.status === "loading" && resource.data === null) {
    return <div className="page-loading" role="status">Loading accounts…</div>;
  }
  if (resource.status === "error" && resource.data === null) {
    return <ErrorState message={resource.error ?? "Unable to load accounts."} action={
      <button type="button" className="button button--secondary" onClick={() => void resource.reload()}>Retry</button>
    } />;
  }

  return (
    <>
      <PageHeader
        title="User administration"
        description="Create local accounts, control role-based access, and reset passwords."
      />
      <section className="panel panel--accent" aria-labelledby="create-account-title">
        <h2 className="panel__title" id="create-account-title">Create account</h2>
        <form className="account-create-grid" onSubmit={(event) => void createAccount(event)}>
          <FormField label="Username" htmlFor="new-username" required>
            <input id="new-username" className="text-input mono" required maxLength={64} autoComplete="off" value={username} onChange={(event) => setUsername(event.target.value)} />
          </FormField>
          <FormField label="Display name" htmlFor="new-display-name" required>
            <input id="new-display-name" className="text-input" required maxLength={120} value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
          </FormField>
          <FormField label="Temporary password" htmlFor="new-password" required hint="Use at least 12 characters.">
            <input id="new-password" className="text-input" type="password" required minLength={12} maxLength={128} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} />
          </FormField>
          <FormField label="Role" htmlFor="new-role" required>
            <select id="new-role" className="text-input" value={role} onChange={(event) => setRole(event.target.value as Role)}>
              {ROLES.map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}
            </select>
          </FormField>
          <div className="form-grid__action">
            <button className="button button--primary" type="submit" disabled={submitting}>{submitting ? "Creating…" : "Create account"}</button>
          </div>
        </form>
        <InlineFormError message={error} />
      </section>

      <section className="panel" aria-labelledby="account-directory-title">
        <div className="panel__heading">
          <h2 className="panel__title" id="account-directory-title">Accounts</h2>
          <span className="record-count">{rows.length} records</span>
        </div>
        {rows.length === 0 ? <EmptyState title="No accounts are available." /> : (
          <div className="table-scroll">
            <table className="data-table account-table" aria-label="User accounts">
              <thead><tr><th>User</th><th>State</th><th>Access</th><th>Password reset</th><th>Activity</th></tr></thead>
              <tbody>
                {rows.map((account) => <AccountRow key={account.id} account={account} onChange={replaceUser} />)}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

function AccountRow({ account, onChange }: { account: UserAccount; onChange: (account: UserAccount) => void }) {
  const { show } = useToast();
  const [role, setRole] = useState<Role>(account.role);
  const [isActive, setIsActive] = useState(account.is_active);
  const [password, setPassword] = useState("");
  const [accessError, setAccessError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function saveAccess() {
    setSubmitting(true);
    setAccessError(null);
    try {
      const updated = await apiFetch<UserAccount>(`/api/users/${account.id}`, {
        method: "PATCH",
        body: { role, is_active: isActive },
      });
      onChange(updated);
      show("Account access updated.", "success");
    } catch (caught) {
      setAccessError(caught instanceof Error ? caught.message : "Unable to update account access.");
    } finally {
      setSubmitting(false);
    }
  }

  async function resetPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setPasswordError(null);
    try {
      await apiFetch<void>(`/api/users/${account.id}/password`, {
        method: "POST",
        body: { password },
      });
      show(`Password reset for ${account.username}.`, "success");
    } catch (caught) {
      setPasswordError(caught instanceof Error ? caught.message : "Unable to reset the password.");
    } finally {
      setPassword("");
      setSubmitting(false);
    }
  }

  return (
    <tr>
      <td><div className="record-title"><strong>{account.display_name}</strong><code>{account.username}</code></div></td>
      <td><StatusBadge status={account.is_active ? "active" : "inactive"} /><span className="account-state-text">{account.is_active ? "Active" : "Inactive"}</span></td>
      <td>
        <div className="account-access-controls">
          <label>
            <span className="visually-hidden">Role for {account.username}</span>
            <select className="text-input text-input--compact" aria-label={`Role for ${account.username}`} value={role} onChange={(event) => setRole(event.target.value as Role)}>
              {ROLES.map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}
            </select>
          </label>
          <label className="checkbox-control">
            <input type="checkbox" aria-label={`Active account for ${account.username}`} checked={isActive} onChange={(event) => setIsActive(event.target.checked)} />
            Active
          </label>
          <button className="button button--secondary button--small" type="button" disabled={submitting} onClick={() => void saveAccess()}>Save access for {account.username}</button>
        </div>
        <InlineFormError message={accessError} />
      </td>
      <td>
        <form className="password-reset-form" onSubmit={(event) => void resetPassword(event)}>
          <label>
            <span className="visually-hidden">New password for {account.username}</span>
            <input
              className="text-input"
              type="password"
              aria-label={`New password for ${account.username}`}
              minLength={12}
              maxLength={128}
              autoComplete="new-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <button className="button button--secondary button--small" type="submit" disabled={submitting}>Reset password for {account.username}</button>
        </form>
        <InlineFormError message={passwordError} />
      </td>
      <td className="account-activity">
        <span className="account-activity__row">
          <span className="account-activity__label">Last login</span>
          <time dateTime={account.last_login_at ?? undefined}>{formatDateTime(account.last_login_at)}</time>
        </span>
        <span className="account-activity__row">
          <span className="account-activity__label">Password changed</span>
          <time dateTime={account.password_changed_at}>{formatDateTime(account.password_changed_at)}</time>
        </span>
        {account.locked_until ? (
          <span className="account-activity__row">
            <span className="account-activity__label">Locked until</span>
            <time dateTime={account.locked_until}>{formatDateTime(account.locked_until)}</time>
          </span>
        ) : null}
      </td>
    </tr>
  );
}
