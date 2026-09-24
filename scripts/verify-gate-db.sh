#!/usr/bin/env bash
set -Eeuo pipefail

# ── Credential handling ─────────────────────────────────────────────
# Passwords come from the environment or the test-db.env file; they are
# never echoed, logged, or committed to version control.
if [ -z "${PGPASSWORD:-}" ]; then
  ENV_FILE="${LOCALAPPDATA}/PerovskiteWorkflow/test-db.env"
  if [ -f "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    # Extract the password from PEROVSKITE_TEST_POSTGRESQL_URL
    _pw=$(printf '%s' "${PEROVSKITE_TEST_POSTGRESQL_URL:-}" \
      | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
    export PGPASSWORD="$_pw"
    unset _pw
  else
    echo "FATAL: PGPASSWORD not set and $ENV_FILE not found" >&2
    exit 2
  fi
fi

PSQL="/c/Program Files/PostgreSQL/18/bin/psql.exe"
PGDUMP="/c/Program Files/PostgreSQL/18/bin/pg_dump.exe"
PGHOST="127.0.0.1"
PGPORT="5433"
PGUSER="perovskite_test"
PGSUPER="postgres"

# ── Generate unique names ───────────────────────────────────────────
RAND=$(date +%s%N | md5sum | head -c 8)
GATE_DB="perovskite_gate_${RAND}"
RESTORE_DB="perovskite_restore_${RAND}"
BACKUP_FILE="/tmp/${GATE_DB}_backup.sql"

# ── Cleanup trap: terminate connections, drop DBs, verify gone ─────
cleanup() {
  EXIT_CODE=$?
  # Disarm traps so we don't recurse
  trap - EXIT INT TERM ERR

  # Terminate all non-self connections to both databases so DROP can succeed
  for db in "${GATE_DB}" "${RESTORE_DB}"; do
    "${PSQL}" -h "${PGHOST}" -p "${PGPORT}" -U "${PGSUPER}" -d postgres -tAc \
      "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${db}' AND pid <> pg_backend_pid()" \
      >/dev/null 2>&1 || true
  done

  # Drop both databases (no || true — we need to know if it failed)
  DROP_OK=1
  for db in "${GATE_DB}" "${RESTORE_DB}"; do
    "${PSQL}" -h "${PGHOST}" -p "${PGPORT}" -U "${PGSUPER}" -d postgres \
      -c "DROP DATABASE IF EXISTS ${db}" >/dev/null 2>&1 || DROP_OK=0
    # Verify the database is actually gone
    still_exists=$("${PSQL}" -h "${PGHOST}" -p "${PGPORT}" -U "${PGSUPER}" -d postgres -tAc \
      "SELECT 1 FROM pg_database WHERE datname='${db}'" 2>/dev/null || echo "QUERY_FAILED")
    if [ "${still_exists}" = "1" ] || [ "${still_exists}" = "QUERY_FAILED" ]; then
      echo "CLEANUP FAILED: database ${db} still exists or verification failed" >&2
      DROP_OK=0
    fi
  done

  rm -f "${BACKUP_FILE}" 2>/dev/null || true

  if [ "${DROP_OK}" -ne 1 ] && [ "${EXIT_CODE}" -eq 0 ]; then
    # Cleanup failed on the success path — must not exit 0
    echo "FATAL: gate passed but cleanup failed; temp databases may remain" >&2
    exit 1
  fi

  echo "cleanup: GATE_DB=${GATE_DB} RESTORE_DB=${RESTORE_DB} backup=${BACKUP_FILE} all removed (DROP_OK=${DROP_OK})"
  exit $EXIT_CODE
}
# INT/TERM set non-zero exit code before EXIT trap runs cleanup
on_int()  { exit 130; }
on_term() { exit 143; }
trap cleanup EXIT
trap on_int INT
trap on_term TERM
trap cleanup ERR

echo "=== Gate DB: ${GATE_DB} ==="
echo "=== Restore DB: ${RESTORE_DB} ==="

# ── 1. Create gate DB ───────────────────────────────────────────────
"${PSQL}" -h "${PGHOST}" -p "${PGPORT}" -U "${PGSUPER}" -d postgres \
  -c "CREATE DATABASE ${GATE_DB} OWNER ${PGUSER}" >/dev/null 2>&1
echo "CREATE GATE_DB exit=$?"

# ── 2. Apply migrations ────────────────────────────────────────────
export PEROVSKITE_DATABASE_URL="postgresql+asyncpg://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${GATE_DB}"
export PEROVSKITE_TEST_POSTGRESQL_URL="${PEROVSKITE_DATABASE_URL}"
export PEROVSKITE_MIGRATION_DATABASE_URL="${PEROVSKITE_DATABASE_URL}"

uv run --no-sync python -m alembic upgrade head 2>&1 | tail -1
echo "alembic upgrade head exit=$?"

uv run --no-sync python -m alembic check 2>&1 | tail -1
echo "alembic check exit=$?"

# ── 3. Full discover (PG + VITE_SMOKE) ──────────────────────────────
PEROVSKITE_VITE_SMOKE=1 uv run --no-sync python -m unittest discover -s tests 2>&1 | tail -1
echo "full discover exit=$?"

# ── 4. PG integration tests ────────────────────────────────────────
uv run --no-sync python -m unittest tests.test_postgresql_integration -v 2>&1 | tail -1
echo "PG integration exit=$?"

# ── 5. Concurrency 3 groups ×5 ────────────────────────────────────
for i in 1 2 3 4 5; do
  result=$(uv run --no-sync python -m unittest \
    tests.test_postgresql_integration.PostgreSQLIntegrationTests.test_concurrent_same_mark_assignment_commits_exactly_once \
    tests.test_postgresql_integration.PostgreSQLIntegrationTests.test_two_concurrent_completions_commit_exactly_once \
    tests.test_postgresql_integration.PostgreSQLIntegrationTests.test_condition_edits_serialize_with_plan_status_transitions \
    2>&1 | grep -E "^(OK|FAIL|ERROR)")
  echo "  run ${i}: ${result}"
  [ "${result}" = "OK" ] || { echo "FATAL: concurrency run ${i} failed" >&2; exit 1; }
done
echo "concurrency exit=0"

# ── 6. Migration cycle on gate DB ───────────────────────────────────
result=$(uv run --no-sync python -m unittest \
  tests.test_postgresql_integration.PostgreSQLIntegrationTests.test_populated_0012_to_head_to_0013_to_head_cycle \
  tests.test_postgresql_integration.PostgreSQLIntegrationTests.test_0013_to_0012_downgrade_blocked_with_unchanged_fingerprint \
  tests.test_postgresql_integration.PostgreSQLIntegrationTests.test_0014_repairs_assignment_rows_with_legacy_substrate_ids \
  2>&1 | grep -E "^(OK|FAIL|ERROR|Ran)")
echo "migration cycle: ${result}"
echo "${result}" | grep -q "^OK" || { echo "FATAL: migration cycle failed" >&2; exit 1; }

# ── 7. Backup gate DB ──────────────────────────────────────────────
"${PGDUMP}" -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" "${GATE_DB}" > "${BACKUP_FILE}" 2>&1
BACKUP_SIZE=$(wc -c < "${BACKUP_FILE}")
BACKUP_SHA=$(sha256sum "${BACKUP_FILE}" | cut -d' ' -f1)
echo "backup size=${BACKUP_SIZE} sha256=${BACKUP_SHA}"

# ── 8. Create restore DB and restore ───────────────────────────────
"${PSQL}" -h "${PGHOST}" -p "${PGPORT}" -U "${PGSUPER}" -d postgres \
  -c "CREATE DATABASE ${RESTORE_DB} OWNER ${PGUSER}" >/dev/null 2>&1
echo "CREATE RESTORE_DB exit=$?"

"${PSQL}" -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${RESTORE_DB}" \
  -f "${BACKUP_FILE}" >/dev/null 2>&1
echo "restore exit=$?"

# ── 9. Per-table deterministic content hash comparison ───────────────
# Each hash must be a valid 32-char MD5; any query failure or invalid
# output is an immediate non-zero exit — never a comparable placeholder.
TABLES="users experiments fabrication_batches fabrication_batch_conditions fabrication_substrates fabrication_devices solution_preparations solution_preparation_uses process_executions process_execution_members execution_deviations result_files result_device_assignments audit_events baselines layer_presets materials campaigns device_layout_versions"

echo "=== Per-table content hash (gate vs restore) ==="
HASH_MISMATCH=0
MD5_RE='^[0-9a-f]{32}$'
for tbl in ${TABLES}; do
  gate_hash=$("${PSQL}" -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${GATE_DB}" -tAc \
    "SELECT COALESCE(md5(string_agg(t::text, ',' ORDER BY t::text)), md5('')) FROM (SELECT * FROM ${tbl} ORDER BY 1) t" 2>/dev/null) || gate_hash=""
  rest_hash=$("${PSQL}" -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${RESTORE_DB}" -tAc \
    "SELECT COALESCE(md5(string_agg(t::text, ',' ORDER BY t::text)), md5('')) FROM (SELECT * FROM ${tbl} ORDER BY 1) t" 2>/dev/null) || rest_hash=""

  # Both must be valid 32-char MD5 hex strings — no failure placeholders
  if ! [[ "${gate_hash}" =~ ${MD5_RE} ]]; then
    echo "  ${tbl}: FATAL gate hash invalid (got '${gate_hash:0:20}')" >&2
    exit 1
  fi
  if ! [[ "${rest_hash}" =~ ${MD5_RE} ]]; then
    echo "  ${tbl}: FATAL restore hash invalid (got '${rest_hash:0:20}')" >&2
    exit 1
  fi

  match="MATCH"
  [ "${gate_hash}" = "${rest_hash}" ] || { match="MISMATCH"; HASH_MISMATCH=1; }
  echo "  ${tbl}: ${match} (${gate_hash:0:12}…)"
done

# ── 10. Revision and index comparison ──────────────────────────────
gate_rev=$("${PSQL}" -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${GATE_DB}" -tAc \
  "SELECT version_num FROM alembic_version LIMIT 1" 2>/dev/null)
rest_rev=$("${PSQL}" -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${RESTORE_DB}" -tAc \
  "SELECT version_num FROM alembic_version LIMIT 1" 2>/dev/null)
rev_match="MATCH"
[ "${gate_rev}" = "${rest_rev}" ] || { rev_match="MISMATCH"; HASH_MISMATCH=1; }
echo "revision: gate=${gate_rev} restore=${rest_rev} ${rev_match}"

gate_idx=$("${PSQL}" -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${GATE_DB}" -tAc \
  "SELECT count(*) FROM pg_indexes WHERE schemaname='public'" 2>/dev/null)
rest_idx=$("${PSQL}" -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${RESTORE_DB}" -tAc \
  "SELECT count(*) FROM pg_indexes WHERE schemaname='public'" 2>/dev/null)
idx_match="MATCH"
[ "${gate_idx}" = "${rest_idx}" ] || { idx_match="MISMATCH"; HASH_MISMATCH=1; }
echo "indexes: gate=${gate_idx} restore=${rest_idx} ${idx_match}"

# ── 11. Fail if any mismatch ────────────────────────────────────────
if [ "${HASH_MISMATCH}" -ne 0 ]; then
  echo "FATAL: content hash, revision, or index mismatch detected" >&2
  exit 1
fi

echo "=== ALL CHECKS PASSED ==="
