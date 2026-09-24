# Application Brand and Account Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the React application branding consistent with the project name and align the account-creation and account-activity layouts.

**Architecture:** Keep the visual changes local to the React shell, Users page semantic markup, CSS, and their existing Vitest coverage. Build the Vite bundle after source verification so the Python application serves the corrected static assets.

**Tech Stack:** React 19, TypeScript, CSS, Vitest, Vite, pnpm.

## Global Constraints

- Store all project-file text in English (United States).
- Do not change database schema, migrations, API behavior, or authorization.
- Use the exact product name `Perovskite Solar Cell Fabrication Workflow`.
- Preserve accessibility labels and native form behavior.

---

### Task 1: Brand and user-administration alignment

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/components/AppShell.test.tsx`
- Modify: `frontend/src/pages/UsersPage.tsx`
- Modify: `frontend/src/pages/UsersPage.test.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: `AppShell` navigation markup and `UserAccount` activity timestamps.
- Produces: a two-line shell brand, grid-aligned account-creation controls, and activity rows with labels distinct from their date-time values.

- [x] **Step 1: Write failing frontend tests**

```tsx
expect(screen.getByText("Perovskite Solar Cell")).toBeInTheDocument();
expect(screen.getByText("Fabrication Workflow")).toBeInTheDocument();
expect(screen.getByText("Last login")).toBeInTheDocument();
expect(screen.getByText(/Password changed/)).toBeInTheDocument();
```

- [x] **Step 2: Run the affected tests and verify red state**

Run: `corepack pnpm --dir frontend test -- AppShell.test.tsx UsersPage.test.tsx`

Expected: the new brand assertion fails before the shell text is changed.

- [x] **Step 3: Implement the minimal markup and CSS**

```tsx
<span className="shell__brand-title">Perovskite Solar Cell</span>
<span>Fabrication Workflow</span>
```

```tsx
<span className="account-activity__row">
  <span className="account-activity__label">Last login</span>
  <time>{formatDateTime(account.last_login_at)}</time>
</span>
```

Use CSS grid rows for the account-creation form, placing all labels in the same row, inputs in the next row, and the password hint below that input. Use two columns for each activity row so a wrapped time value remains aligned beneath its time column.

- [x] **Step 4: Run the affected tests and verify green state**

Run: `corepack pnpm --dir frontend test -- AppShell.test.tsx UsersPage.test.tsx`

Expected: all selected tests pass.

- [x] **Step 5: Build the production bundle and verify static output**

Run: `corepack pnpm --dir frontend typecheck`; `corepack pnpm --dir frontend lint`; `corepack pnpm --dir frontend build`

Expected: all commands exit 0 and write the hashed assets under `src/web/static-app/assets/`.
