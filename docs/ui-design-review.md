# UI Design Review — Web Console (React app)

Date: 2026-08-29 · Scope: `frontend/` (React 19 + Vite), reviewed against the
[Refactoring UI](https://www.refactoringui.com/) heuristics (hierarchy, type scale,
color, spacing, depth, forms, states, accessibility) plus a functional audit of
interactive components. All findings verified against HEAD `cd3e595`.

## Verdict

The console has a **clear, intentional design personality** — "desktop-first lab
console: porcelain surface, graphite text, steel rules, ITO cyan for active/process,
perovskite violet for planned/configuration" (`frontend/src/styles.css:1-4`). It
deliberately avoids AI-default aesthetics (purple gradients, SaaS template look):
colors are muted and domain-meaningful, radii are small, elevation is restrained.
The accessibility foundation is strong (skip link, `:focus-visible`,
`prefers-reduced-motion`, focus-trapped dialogs, ~102 `aria-*` usages).

The problem is **not the design intent — it is that the system behind it has
eroded**. Design tokens are defined but barely used; typography has 13 ad-hoc
sizes and no scale; the declared brand font is never loaded; several declared
component styles are missing; and one interaction (layer drag-and-drop) is
functionally broken in the common case.

## Findings

### A. Design tokens exist but are not adopted (highest leverage)

`styles.css:6-48` defines a good token set (palette, spacing on an 8px grid,
shadows), but the 2,539-line file references `var(--space-*)` only **4 times**
against **474 lines containing raw px values**. Consequences:

- **No type scale**: 13 distinct `font-size` values (10, 11, 12, 12.5, 13, 14, 15,
  16, 17, 19, 20, 22, 26px) with no named steps. Hierarchy is expressed through
  size alone instead of the size + weight + color trio.
- **Off-grid spacing**: `7px 14px` buttons (`:246`), `2px 8px` badges (`:549`),
  `9px 0` version rows (`:1000`), `7px 10px` table cells (`:488`).
- **Off-palette colors** (~15 one-offs): `.nav-group__label { color: #8fa3ab }`
  (`:163`), `.nav-item:hover { background: #24343b }` (`:182`), status-badge
  borders `#b7dde4 / #d4cbec / #ecd3ae / #ecc9c6 / #bfe0d0` (`:560-584`),
  `.data-table tbody tr:hover { background: #f0f6f7 }` (`:503`),
  `.status-badge--neutral { background: #eef1f2 }` (`:588`), and others.
- One `!important` (`:1781-1783`); one-off shadows (`:1311`, `:2022`, `:2091`).

### B. Declared brand font is never loaded

`--font-ui` declares "IBM Plex Sans" and `--font-mono` "IBM Plex Mono"
(`styles.css:26-31`), but there is no `@font-face`, no font files in the repo,
and no external stylesheet (CSP `style-src 'self'` would block one). Every user
sees the `system-ui` fallback — the intended Plex personality never ships. CSP
already has `font-src 'self'` (`src/web/middleware.py:72`), so **self-hosted
woff2 files work with no CSP change**.

### C. Layout

- `.shell__content` has `max-width: 1280px` but no `margin-inline: auto`
  (`styles.css:223-227`) — on wide monitors all content hugs the left edge of
  the space next to the sidebar.
- Exactly one breakpoint (`max-width: 720px`, three blocks `:2113`, `:2433`,
  `:2534`). Tables with `min-width: 1060px` (`.account-table`, `:1083`) force
  horizontal scrolling. Run-sheet primary buttons measure ~29px tall
  (`.button` = 13px font + 7px vertical padding, `:246`) — below the 44px touch
  target standard, relevant if batches are ever driven from a tablet at the bench.
- Focus ring uses `box-shadow` with `outline: none` (`:85-89`) — clipped inside
  `overflow-x: auto` containers (`.table-scroll`, `.snapshot-json`).

### D. Missing / inconsistent component styles

- `.button--link` is used (`AppShell.tsx:190`) but has **no CSS definition**;
  `.logout-control`, `.empty-state__action`, `.error-state__action` are unstyled
  hooks.
- Some forms bypass the shared `FormField` component with hand-rolled
  `<label className="form-field">` markup and no `aria-describedby` wiring
  (e.g. `CompleteBatchDialog.tsx:129-175`, `BatchDetailPage.tsx:87-99`).
- `CompleteBatchDialog` lacks the focus trap its sibling `ConfirmDialog` has.
- Toasts auto-dismiss after a fixed 5s (`Toast.tsx`) — error toasts vanish too,
  and there is no pause on hover.
- Loading vs empty are conflated: `DataTable` renders "No records." whenever
  `rows.length === 0`, including during the initial fetch (no loading prop);
  loaders are text-only (no skeletons).
- Numeric table columns (JV metrics) are left-aligned proportional text rather
  than right-aligned `tabular-nums`.

### E. Functional defect: layer drag-and-drop (user-confirmed)

`LayerStackEditor.tsx:113-124` + `state.ts:314-334`:

- `reorderLayer` reorders **only if every layer between source and target has
  the same role AND layer_type**; otherwise it is a documented *silent no-op*
  (`state.ts:310-312`). A typical stack (substrate → HTL → perovskite → ETL →
  electrode) has no same-type neighbors, so **every drop is silently ignored**.
- The drag ghost is the tiny ⠿ handle `<span>`, not the card; there is no drop
  indicator, no valid-target highlight, no feedback of any kind.
- `handleDragStart` never calls `dataTransfer.setData()` — in Firefox the drag
  does not even start.
- The handle is rendered on every card with `title="Drag to reorder"` even when
  reordering is impossible; the ↑/↓ buttons are the only real mechanism.
- Tests cover only the rare valid case (two adjacent NiOx layers,
  `LayerStackEditor.test.tsx:93-125`), so the suite is green while the common
  experience is broken.

### F. Maintainability

- `styles.css` is a single 2,539-line file with ~15 accretion "Phase" banners.
- `BatchDetailPage.tsx` is 1,344 lines covering six run-sheet sub-domains in one
  file.

## Roadmap

| Batch | Contents |
|---|---|
| PR1 | This report; **Phase 0** layer drag-and-drop fix; **Phase 1** token system + sweep; **Phase 2** self-hosted IBM Plex |
| PR2 | **Phase 3** layout centering + touch guardrails; **Phase 4** component/state consistency (DataTable loading, FormField migration, focus trap, toasts, focus ring, empty states) |
| PR3 | **Phase 5** split `styles.css` into modules; **Phase 6** split `BatchDetailPage.tsx` (pure refactor) |

Guiding rule for Phases 1–2: **visual intent does not change** — ad-hoc values
are normalized into the token system, and the brand font finally renders.
Screenshots of key pages are compared before/after each batch.

## Deferred (tracked in `docs/deferred-issues.md`)

- Dark mode — revisit after the token system lands (low cost to add later);
  the lab is a bright-environment, light-theme context today.
- Full tablet/touch adaptation (long-press drag gestures, touch-friendly
  selection models) — current scope is guardrails only (≥40px primary targets,
  ≥8px target gaps, hover-only information given a fallback).
- In-app FAQ/user guide — the contextual `HelpHint` strategy continues.
