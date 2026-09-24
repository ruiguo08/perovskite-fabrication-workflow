# Local development on Windows

This workflow is for a single developer using PostgreSQL on the same Windows
computer as the application. It does not expose PostgreSQL or FastAPI to the
local network and does not replace the HTTPS deployment guidance in
`DEPLOYMENT.md`.

## Prerequisites

- PostgreSQL 18 running as the `postgresql-x64-18` Windows service;
- PostgreSQL listening only on `localhost`;
- Python 3.14 in the `PSC314` Conda environment;
- uv 0.12.1 and the committed lockfile used for the project environment;
- Node.js 24 and `pnpm` (pnpm 11, available through `corepack pnpm`) for the
  React application under `frontend/`.

The verified local database separation is:

| Purpose | Role | Database |
| --- | --- | --- |
| Application data | `perovskite_app` | `perovskite_registry` |
| Disposable integration-test data | `perovskite_test` | `perovskite_test` |

Both roles should have `LOGIN` but no superuser, database-creation,
role-creation, replication, or row-level-security-bypass privileges. Each role
owns only its corresponding database.

## Common commands

Run these commands from the repository root:

| Task | Command |
| --- | --- |
| Install the locked development environment | `uv sync --locked --extra test --no-dev` |
| Configure the disposable test database (once, or to reset its password) | `.\scripts\Configure-LocalTestDatabase.ps1` |
| Start the local application | `.\scripts\Start-LocalDevelopment.ps1 -EnableDocs` |
| Run the complete test suite against PostgreSQL | `.\scripts\Test-LocalPostgreSQL.ps1` |
| Run only the PostgreSQL integration checks | `.\scripts\Test-LocalPostgreSQL.ps1 -PostgreSQLOnly` |

The test commands use the encrypted credential stored for the current Windows
user and refuse to connect to the application database.

## Start a PowerShell session

From the repository root:

```powershell
conda activate PSC314
python -m pip install uv==0.12.1
uv sync --locked --extra test --no-dev
.\scripts\Set-LocalDatabaseUrls.ps1
```

The script prompts for both database passwords as secure strings, URL-encodes
them, and sets process-only environment variables. It does not write a password
or database URL to disk. Closing PowerShell clears both URLs.

Do not print, paste, commit, or use `setx` with either database URL because the
URL contains the password.

## Initialize or update the schema

```powershell
.\scripts\Initialize-LocalDatabases.ps1
```

The command safely re-runs Alembic for both databases, verifies that the schema
is at the current head, checks for model/schema drift, and restores the
application URL after inspecting the test database.

## Create the first administrator

Run this once against an empty application database:

```powershell
python -m web.admin_cli create-user admin `
  --display-name "Lab Administrator" `
  --role administrator
```

The password is entered interactively. It must contain 12 to 128 characters and
must not contain the username.

## Run the application

```powershell
.\scripts\Start-LocalDevelopment.ps1 -EnableDocs
```

This is the normal one-command startup. If the application URL is not already
configured in the current PowerShell process, the script securely prompts for
the `perovskite_app` password. It then applies pending migrations, checks the
schema, and starts the server with the repository's `.venv` Python when
available.

Open <http://localhost:8000/login>. The script refuses any database other than
the loopback `perovskite_app` / `perovskite_registry` pair and disables the HTTPS
requirement only for this local process. Stop it with `Ctrl+C`. Do not use this
HTTP mode for access from another computer.

## Run the React application during development

The React application lives in `frontend/` and is served by FastAPI at `/app/`
in production. During development, run the Vite dev server and the FastAPI app
side by side:

```powershell
# Terminal 1: the FastAPI API (as above)
.\scripts\Start-LocalDevelopment.ps1 -EnableDocs
# Terminal 2: the Vite dev server
cd frontend
corepack pnpm install
corepack pnpm dev
```

Open <http://localhost:5173/app/>. The Vite server proxies `/api`, `/healthz`,
and the narrow export download paths (experiment and fabrication-batch
JSON/PDF) to the FastAPI app on `127.0.0.1:8000`, so the browser stays
same-origin and the production CSP holds.

Phase 2 planning and reusable-directory routes plus the Phase 3 execution,
results, and provenance routes are complete under `/app/`, including the
experiment builder at `/app/experiments/new`, the fabrication-batch run sheet
at `/app/experiments/:id/batches/:batchId`, result upload at
`/app/experiments/:id/upload`, and result analysis at `/app/results/:resultId`.
Since the Phase 4 cutover, `/app/` is the only frontend: classic URLs return
303 redirects to their React equivalents, so a legacy bookmark such as
`/experiments` or `/login?next=...` still lands correctly in React.

To update the committed production bundle that ships inside the Python wheel:

```powershell
cd frontend
corepack pnpm build
```

The build writes the compiled application into `src/web/static-app/` (method A
in `docs/react-migration.md`); commit that output together with the frontend
source changes.

Frontend test and type-check commands:

```powershell
cd frontend
corepack pnpm test        # Vitest component and page tests
corepack pnpm typecheck   # tsc --noEmit
corepack pnpm lint        # ESLint
corepack pnpm build       # production Vite build into src/web/static-app/
```

## Run all tests against PostgreSQL

Configure the disposable test database once. The administrator password is used
only during setup; the generated test password is saved with Windows user-bound
encryption outside the repository:

```powershell
.\scripts\Configure-LocalTestDatabase.ps1
```

After that, this command works in future PowerShell sessions without another
password prompt:

```powershell
.\scripts\Test-LocalPostgreSQL.ps1
```

The script migrates and validates the test database before running the complete
suite. `tests.test_postgresql_integration` must report `ok`, not `skipped`.
It temporarily sets both database variables to the loopback
`perovskite_test` / `perovskite_test` pair and restores them afterward. The
script fails before running a test if either the role or database name differs,
so records in `perovskite_registry` or a deployed production database remain
untouched.

## Verify the listener

PostgreSQL should listen on IPv4 and optionally IPv6 loopback only:

```powershell
netstat -ano | Select-String "5432"
```

Expected listeners are `127.0.0.1:5432` and optionally `[::1]:5432`. A listener
on `0.0.0.0:5432` or a non-loopback address must be corrected before continuing.
