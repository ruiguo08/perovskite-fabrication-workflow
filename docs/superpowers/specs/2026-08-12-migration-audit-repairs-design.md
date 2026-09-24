# Migration Audit Repairs Design

## Goal

Resolve every issue identified during the Phase 0 and Phase 1 migration audit
without weakening authentication, authorization, provenance, or the existing
legacy workflow.

## Data catalogs

Materials, supplier products, substrates, and layer presets are reusable
PostgreSQL catalog data. Built-in layer presets and the initial material list
are bootstrap inputs only. A catalog seed-version table records each completed
bootstrap so later application starts do not recreate records that an
administrator deleted or renamed.

Layer presets have an explicit `personal` or `shared` scope. Personal presets
have an owner and remain visible and editable only to that owner. Shared
presets have no owner, are visible to all authenticated users, and can be
created, revised, or deactivated only by instructors and administrators. Every
revision remains immutable. A composite foreign key guarantees that a preset's
current version belongs to that same preset.

Substrate material names are validated as bounded catalog identifiers instead
of as the hard-coded `ITO`/`FTO` pair. The experiment builder obtains active
substrate materials and products from the material API and expands the chosen
values into the saved recipe snapshot.

## Migration strategy

Previously shipped migrations remain unchanged. Migration `0010` adds catalog
seed tracking, layer-preset scope and integrity constraints, and indexes for
foreign-key and visibility columns. Existing layer presets become `personal`.
The migration remains compatible with both a populated PostgreSQL database and
the SQLAlchemy-created SQLite test schema.

## Backend behavior

Student material-product proposals are accepted only for active materials or
for the student's own pending material. No write is committed when the parent
material is inactive or invisible. Successful hashed SPA assets receive
immutable caching; error responses do not.

The Vite proxy integration fixture creates its isolated schema before seeding
and retains and closes subprocess log handles. Its opt-in suite must exercise
login, logout, CSRF rejection, and cross-origin rejection through a live Vite
server.

## React behavior

Logout waits for the server response before navigation. Session bootstrap
distinguishes a real 401 from service or network errors. Authentication keeps
the originally requested deep link. Route guards enforce role access even when
a user enters a URL directly.

The shell supports narrow viewports, includes a skip link, and meets text
contrast requirements. Confirmation dialogs trap and restore focus and use
unique labels. Loading, empty, and error states are distinct. Recent
experiments are ordered by `updated_at`. Login metadata and username input
behavior follow browser accessibility conventions.

## Verification

Every behavior change receives a regression test written and observed failing
before implementation. Final verification includes frontend type checking,
linting, unit tests and production build; the opt-in Vite proxy suite; the full
Python suite; PostgreSQL migration, schema-drift and integration tests; and an
isolated installation of the built wheel.
