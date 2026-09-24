# Office-network deployment

The supported network layout is:

~~~text
student browser --HTTPS--> Caddy --HTTP on loopback--> FastAPI
                                             |
                                      PostgreSQL on loopback
~~~

Neither FastAPI nor PostgreSQL should listen on an office-facing interface. Only the HTTPS reverse proxy should accept network traffic. No firewall change is part of this repository.

## Ubuntu LTS prerequisite

Ubuntu 24.04 LTS is the recommended deployment baseline. Ubuntu 20.04 reached
the end of standard support in May 2025: do not deploy on 20.04 unless Ubuntu
Pro / ESM is enabled and remains enabled for the server's lifetime. Confirm
the status before every release:

~~~bash
pro status
~~~

This project requires Python 3.14. Ubuntu's system Python is too old; leave it
untouched and use the uv-managed Python described below. uv installs prebuilt
CPython distributions in `/opt/perovskite/.python`, so the service does not
depend on a system-wide Python upgrade.

## 0. Prepare the Ubuntu host

Use a supported CPU architecture, a stable internal DNS name, and encrypted
server storage. Install the current Docker Engine with the Compose plugin from
the [Docker Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).
Install Caddy from its [official Ubuntu package repository](https://caddyserver.com/docs/install).
Then install the small host prerequisites and the locked uv executable:

~~~bash
sudo apt update
sudo apt install -y ca-certificates curl git
curl -LsSf https://astral.sh/uv/0.12.1/install.sh -o /tmp/uv-install.sh
sudo env UV_UNMANAGED_INSTALL=/usr/local/bin sh /tmp/uv-install.sh
rm /tmp/uv-install.sh
~~~

Create separate non-login Unix accounts. The web account can read the release
and its own database credential; the migration account can read only the
migration credential. Do not add either account to the `docker` group.

~~~bash
sudo useradd --system --home-dir /opt/perovskite --shell /usr/sbin/nologin perovskite
sudo useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin perovskite-migrator
sudo install -d -o perovskite -g perovskite -m 0750 /opt/perovskite
sudo -u perovskite git clone <reviewed-release-repository-url> /opt/perovskite
sudo usermod -aG perovskite perovskite-migrator
sudo -u perovskite -H env HOME=/opt/perovskite \
  UV_CACHE_DIR=/opt/perovskite/.uv-cache \
  UV_PYTHON_INSTALL_DIR=/opt/perovskite/.python \
  /usr/local/bin/uv python install 3.14
sudo -u perovskite -H env HOME=/opt/perovskite \
  UV_CACHE_DIR=/opt/perovskite/.uv-cache \
  UV_PYTHON_INSTALL_DIR=/opt/perovskite/.python \
  /usr/local/bin/uv sync --locked --no-dev --no-editable
~~~

The server may fetch only reviewed release dependencies. For an isolated lab
network, populate a reviewed internal package/Python mirror before this step;
do not weaken TLS verification.

## 1. Build one reviewed release

The committed `uv.lock` is the dependency source of truth. Install and test the
exact locked environment that will run in production:

~~~bash
uv --version
uv lock --check
cd frontend
corepack pnpm install --frozen-lockfile
corepack pnpm build
cd ..
uv sync --locked --extra test --no-dev --no-editable
uv run --no-sync python -m unittest discover -s tests -v
uv build
~~~

Deploy the reviewed source commit with its locked environment; the Alembic files
and service configuration intentionally remain beside the installed package.
The wheel build is a release validation artifact, not a standalone deployment
bundle. Do not deploy from a dirty working tree. The package metadata and
FastAPI API version both come from `src/web/version.py`; change that single value
when preparing a release.

The React application (served at `/app/`) is committed as a built artifact in
`src/web/static-app/` (release method A in `docs/react-migration.md`), so the
server needs no Node or pnpm. Rebuild it from `frontend/` with pnpm on a
development machine; Vite writes directly to `src/web/static-app/`. Commit the
updated output before the release; the wheel packages it automatically.

The Phase 3 production bundle extends the Phase 2 routes with
`/app/fabrication-batches`, `/app/results`,
`/app/experiments/:id/batches/:batchId` (run sheet),
`/app/experiments/:id/upload`, and `/app/results/:resultId` (analysis and
assignment). Statistics are server-computed; chart rendering uses hand-written
SVG with no chart library, so the production CSP `script-src 'self'` is
preserved. Since the Phase 4 cutover, `/app/` is the canonical application:
legacy GET URLs (`/`, `/experiments`, `/login`, `/campaigns`, `/materials`,
`/admin/users`, and the detail/upload/batch pages) return 303 redirects to
their React equivalents, the legacy form-POST routes, Jinja templates, and
static JavaScript are removed, and the wheel ships only React static-app
assets (no external CDNs; the production CSP is `script-src 'self'; style-src
'self'`).

After `uv build`, verify the wheel from outside the source checkout so local
package files cannot satisfy imports accidentally:

~~~bash
wheel_path="$(pwd)/$(find dist -maxdepth 1 -name '*.whl' -print -quit)"
verification_dir="$(mktemp -d)"
uv venv --python 3.14 "$verification_dir/venv"
uv pip install --python "$verification_dir/venv/bin/python" "$wheel_path"
cd "$verification_dir"
"$verification_dir/venv/bin/python" -c "from importlib.resources import files; root = files('web').joinpath('static-app'); assert root.joinpath('index.html').is_file(); assert any(root.joinpath('assets').iterdir()); print('installed wheel SPA assets: OK')"
cd -
rm -rf "$verification_dir"
~~~

The committed `tests/test_installed_wheel_smoke.py` automates a deeper
installed-wheel check without network: it creates a throwaway
`--system-site-packages` venv, installs the newest `dist/*.whl` with
`--no-deps`, and exercises real HTTP responses against the installed package
outside the source tree — React entry and immutable hashed assets at `/app/`,
303 redirects for legacy GETs, `/api/session` 401 and `/healthz` 200,
404/405 for removed legacy POST routes, no installed `web/templates` or
`web/static` directories, and JSON/PDF experiment exports as attachment
downloads. Run it after any release build:

~~~bash
python -m unittest tests.test_installed_wheel_smoke -v
~~~

## 2. Prepare PostgreSQL

PostgreSQL 18 is the tested major version. For a native Windows development
installation, use [LOCAL_DEVELOPMENT_WINDOWS.md](LOCAL_DEVELOPMENT_WINDOWS.md).

Fresh production deployments only. The retired legacy SQLite registry is
not supported as an upgrade source. PostgreSQL/Alembic migrations remain
supported for development and test databases — with one exception below.

### Pre-squash databases are incompatible (check before migrating)

Any database that ran the **old pre-squash `0007_fabrication_batches`
migration chain** (multiple revisions numbered 0001–0007) is incompatible
with the squashed initial schema: the new chain reuses the revision id
`0007_fabrication_batches` for a *different* end state, so such a database
would be treated as mid-history and fail late with confusing errors. Do not
run the squashed chain over it. Such databases must be recreated from a
verified backup (or, when their data must be preserved, wait for a dedicated
import path to be designed — do not attempt an in-place conversion).

Before running migrations against an existing database, verify it is not
stamped with the old chain. The squashed initial schema widened
`fabrication_substrates.substrate_mark` to 9 characters; the old chain left
it at 3:

~~~sql
SELECT character_maximum_length
FROM information_schema.columns
WHERE table_name = 'fabrication_substrates' AND column_name = 'substrate_mark';
~~~

* `9` — squashed initial schema (safe to `upgrade head`).
* `3` — old pre-squash chain (incompatible; recreate the database).
* no row — fresh database (safe).

### Legacy analysis rows that could not be repaired automatically

Migration `0014` rewrites legacy result analyses whose every device carries an
unambiguous full laser mark and an explicit channel ordinal, writing
`device_ordinal`, rebuilding substrate grouping, and updating both JSON
`schema_version` and the `analysis_schema_version` column to 3. Ambiguous
rows (devices missing a channel, disagreeing marks, or missing device_mark)
are left at schema 2. Count them before deploying with:

~~~sql
SELECT count(*) FROM result_files
WHERE analysis_schema_version < 3
  AND analysis IS NOT NULL
  AND EXISTS (
    SELECT 1 FROM jsonb_array_elements(analysis->'substrates') AS s
    WHERE length(s->>'substrate_id') = 3
  );
~~~

A non-zero count means those files keep their legacy truncated ids and
should be reviewed or re-uploaded after deployment.

The database uses three separate roles:

| Role | Purpose | Production privileges |
| --- | --- | --- |
| `perovskite_bootstrap` | Initial container setup and emergency administration | Superuser; never used by the app |
| `perovskite_migrator` | Applies reviewed Alembic migrations | Owns the database schema; not used by the app |
| `perovskite_app` | Runs the web application | Data access only; cannot create roles, databases, or schema objects |

Generate a different long random password for each role and store them outside
version control. Copy `deploy/postgresql.env.example` to an access-restricted
location, replace every password, and start PostgreSQL with that file:

~~~bash
sudo install -d -m 0700 /etc/perovskite
sudo install -o root -g root -m 0600 deploy/postgresql.env.example /etc/perovskite/postgresql.env
sudoedit /etc/perovskite/postgresql.env
sudo docker compose --env-file /etc/perovskite/postgresql.env -f deploy/postgresql.compose.yaml up -d
~~~

The initialization script creates the migration and runtime roles with least
privilege. It runs only for an empty PostgreSQL data volume. The Compose service
publishes PostgreSQL only on `127.0.0.1`. A system PostgreSQL installation is
also supported. The [PostgreSQL official image documentation](https://hub.docker.com/_/postgres#pgdata)
explains that version 18 stores `PGDATA` in a version-specific subdirectory, so
the Compose volume intentionally mounts `/var/lib/postgresql`, not the pre-18
`/var/lib/postgresql/data` path. Do not attach a PostgreSQL 17 volume without a
planned `pg_upgrade` or dump/restore migration.

Install the separate migration and runtime environment files. Use URL-encoded
passwords in URLs. The migration credential belongs only to the
`perovskite-migrator` account; the web credential belongs only to
`perovskite`.

~~~bash
sudo install -o perovskite-migrator -g perovskite-migrator -m 0600 \
  deploy/perovskite-migrator.env.example /etc/perovskite/perovskite-migrator.env
sudoedit /etc/perovskite/perovskite-migrator.env
sudo install -o perovskite -g perovskite -m 0600 \
  deploy/perovskite-web.env.example /etc/perovskite/perovskite.env
sudoedit /etc/perovskite/perovskite.env
sudo install -o root -g root -m 0644 deploy/perovskite-migrate.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start perovskite-migrate.service
sudo systemctl status perovskite-migrate.service
~~~

The migration unit is deliberately one-shot and is never enabled. Run it only
when deploying a reviewed release that contains a new forward migration. The
web service refuses to start if its runtime role cannot reach a fully migrated
database.

Alembic migrations are the ordered, versioned history of database-structure
changes under `migrations/versions`. They create or alter tables, columns,
indexes, constraints, and reference data while preserving compatible production
records. `upgrade head` applies only revisions not yet recorded in the database's
`alembic_version` table. `check` detects model changes that do not yet have a
migration. The pre-deployment development history has been squashed into one
initial revision. After real deployment data exists, do not squash or renumber
that revision; append a new forward migration for every schema change. Always
rehearse upgrades on a restored staging backup first.

Two forward repairs ship in `0014_deployment_integrity_repairs`: batches
completed before the actual-count column existed backfill the planned count
as the documented conservative historical value (unfinished batches stay
null), and unambiguous truncated legacy substrate ids in result analyses are
rewritten to their full laser marks. Downgrading past `0013` is
intentionally blocked: the migration raises `RuntimeError` immediately
before any DDL or DML because the pre-0013 narrow mark model cannot
hold physical laser marks without destroying provenance. Restore from a
verified backup instead.

Create the first administrator interactively so the password does not appear in shell history or process listings:

~~~bash
sudo -u perovskite sh -c 'set -a; . /etc/perovskite/perovskite.env; set +a; \
  exec /opt/perovskite/.venv/bin/perovskite-workflow-admin create-user admin \
  --display-name "Lab Administrator" --role administrator'
~~~

Additional accounts can be created from **Users** after the administrator signs in. Administrators can create, disable, change roles, reset passwords, create new Baseline revisions, and archive Baselines. Instructors can manage Campaigns, create Baselines, decide substrate-count exceptions, and access every experiment. Students can access only experiments they created and can select only active instructor-created Campaigns and active Baselines.

## 3. Configure HTTPS and run the web service

For private-IP access, a public certificate authority normally cannot issue the certificate. `deploy/Caddyfile.internal` uses Caddy's internal CA. Install that CA's root certificate on each authorized laboratory computer through a trusted channel before use. A stable internal DNS name is preferable to a changing IP address.

If the university can issue a certificate for an internal DNS name, use that certificate instead and remove `tls internal`. Do not train users to click through browser certificate warnings.

Copy `deploy/Caddyfile.internal` to `/etc/caddy/Caddyfile`, replace
`perovskite.lab.example` with the exact DNS name, and include that same name in
`PEROVSKITE_ALLOWED_HOSTS`. Keep `PEROVSKITE_REQUIRE_HTTPS=true`. FastAPI
trusts forwarded headers only from loopback by default.

~~~bash
sudo install -o root -g root -m 0644 deploy/Caddyfile.internal /etc/caddy/Caddyfile
sudoedit /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo install -o root -g root -m 0644 deploy/perovskite-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl unmask caddy
sudo systemctl enable --now caddy perovskite-web
sudo caddy trust
curl --fail https://perovskite.lab.example/healthz
~~~

The final command runs on the server. Locate the Caddy root certificate with
`sudo find /var/lib/caddy -path '*pki/authorities/local/root.crt' -print` and
distribute it to authorized lab computers by a trusted channel before opening
the service to them. Do not use a self-signed browser exception.

The web unit refuses to start unless the database is reachable and migrated, runs as
the unprivileged `perovskite` account, restarts after failures, and writes logs to
the system journal. The entry point binds to `127.0.0.1:8000`; it is not directly
reachable by students. Caddy is the network endpoint. Monitor `/healthz` through
Caddy for application and database availability.

## 4. Back up and rehearse restoration

Install and enable the root-owned backup timer. It creates a PostgreSQL custom
format dump and SHA-256 sidecar every day at 02:15 server local time, keeps 35 days by
default, and needs an encrypted, access-controlled backup filesystem.

~~~bash
sudo install -o root -g root -m 0750 deploy/backup-postgresql.sh /opt/perovskite/deploy/
sudo install -o root -g root -m 0600 \
  deploy/perovskite-backup.env.example /etc/perovskite/perovskite-backup.env
sudoedit /etc/perovskite/perovskite-backup.env
sudo install -o root -g root -m 0644 deploy/perovskite-backup.service /etc/systemd/system/
sudo install -o root -g root -m 0644 deploy/perovskite-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now perovskite-backup.timer
sudo systemctl start perovskite-backup.service
sudo systemctl status perovskite-backup.service
sudo systemctl list-timers perovskite-backup.timer
~~~

Copy completed backups and their `.sha256` files to a separate encrypted
location. A local disk is not a disaster-recovery backup. Before collecting
laboratory data, rehearse a restore on a separate staging server with the same
roles and an empty database. Stop its web service, verify the checksum, restore
with the migration role, then start the web service and check `/healthz`:

~~~bash
sha256sum --check /secure/staging/perovskite_registry-<timestamp>.dump.sha256
sudo systemctl stop perovskite-web
sudo docker compose --env-file /etc/perovskite/postgresql.env \
  -f /opt/perovskite/deploy/postgresql.compose.yaml exec -T database \
  sh -ceu 'PGPASSWORD="$PEROVSKITE_MIGRATOR_PASSWORD" exec pg_restore \
    --clean --if-exists --no-owner --no-privileges \
    --username=perovskite_migrator --dbname="$POSTGRES_DB"' \
  < /secure/staging/perovskite_registry-<timestamp>.dump
sudo systemctl start perovskite-web
~~~

Never run the restore command against the production database unless executing
an approved incident-recovery procedure.

## 4b. Purge expired sessions daily

Expired session rows are never presented again, but they accumulate in the
`sessions` table until removed. Enable the cleanup timer to run the
`cleanup-sessions` administration subcommand daily at 03:15 server local time
(after the 02:15 backup). The unit runs as the unprivileged `perovskite`
account with the same environment file and database preflight as the web
service:

~~~bash
sudo install -o root -g root -m 0644 deploy/perovskite-session-cleanup.service /etc/systemd/system/
sudo install -o root -g root -m 0644 deploy/perovskite-session-cleanup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now perovskite-session-cleanup.timer
sudo systemctl start perovskite-session-cleanup.service
sudo systemctl status perovskite-session-cleanup.service
~~~

Each run prints the number of deleted rows to the system journal. Two more
read-only subcommands support operations: `perovskite-workflow-admin status`
prints monitoring counters (users, active sessions, experiments, fabrication
batches, result files, audit events in the last 24 hours), and
`perovskite-workflow-admin export-audit --format json --since <ISO-8601>`
streams matching `audit_events` rows as JSON lines (or CSV) for review, with
optional `--until`, `--actor <username>`, `--action <prefix>`, and `--limit`
filters. A fourth read-only subcommand feeds future analysis:
`perovskite-workflow-admin export-training-data --experiment-id <id>` (or
`--batch-id <id>`) emits one row per frozen condition of each completed
batch as JSON lines or CSV, combining the recipe features from the BO
search space with aggregated device metrics and batch provenance.

## 5. Protect data

- Restrict the service environment file, Caddy private keys, PostgreSQL data, and backups to the service administrators.
- Use full-disk encryption on the server and encrypted, access-controlled backups. Test restoration periodically.
- Back up PostgreSQL with `pg_dump` or an equivalent managed process; copying live database files is not a valid backup.
- Keep the OS, PostgreSQL, Caddy, Python, and dependencies patched.
- Review `audit_events` after account changes and unexpected uploads. Uploaded raw bytes, their size, uploader, and SHA-256 digest are stored transactionally.
- Do not place database dumps, uploaded data, passwords, `.env` files, or Caddy keys in the Git repository or a shared OneDrive folder.
- Keep API documentation disabled on the network unless instructors genuinely need it.

Session cookies are `Secure`, `HttpOnly` for the session secret, host-only, and `SameSite=Strict`. State-changing requests also require a separate CSRF token and pass same-origin checks. Sessions have absolute and idle expiration, account disabling/password reset revokes active sessions, repeated failures temporarily lock the account, and session secrets are hashed in the database.
