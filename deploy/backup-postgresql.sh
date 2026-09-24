#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

: "${PEROVSKITE_BACKUP_DIRECTORY:?PEROVSKITE_BACKUP_DIRECTORY is required}"
: "${PEROVSKITE_BACKUP_RETENTION_DAYS:?PEROVSKITE_BACKUP_RETENTION_DAYS is required}"

readonly compose_file="${PEROVSKITE_COMPOSE_FILE:-/opt/perovskite/deploy/postgresql.compose.yaml}"
readonly postgres_env_file="${PEROVSKITE_POSTGRES_ENV_FILE:-/etc/perovskite/postgresql.env}"
readonly backup_directory="$PEROVSKITE_BACKUP_DIRECTORY"
readonly retention_days="$PEROVSKITE_BACKUP_RETENTION_DAYS"

case "$backup_directory" in
    /*) ;;
    *) echo "PEROVSKITE_BACKUP_DIRECTORY must be an absolute path" >&2; exit 2 ;;
esac
if ! [[ "$retention_days" =~ ^[1-9][0-9]*$ ]]; then
    echo "PEROVSKITE_BACKUP_RETENTION_DAYS must be a positive integer" >&2
    exit 2
fi
if ! command -v docker >/dev/null; then
    echo "docker is required for PostgreSQL backups" >&2
    exit 2
fi
if [[ ! -r "$compose_file" || ! -r "$postgres_env_file" ]]; then
    echo "The Compose file or PostgreSQL environment file is not readable" >&2
    exit 2
fi

install -d -m 0700 "$backup_directory"
readonly timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
readonly backup_file="$backup_directory/perovskite_registry-$timestamp.dump"
readonly temporary_file="$backup_file.partial"

cleanup() {
    rm -f -- "$temporary_file"
}
trap cleanup EXIT

docker compose --env-file "$postgres_env_file" -f "$compose_file" exec -T database \
    sh -ceu 'PGPASSWORD="$PEROVSKITE_MIGRATOR_PASSWORD" exec pg_dump \
        --format=custom --no-owner --no-privileges \
        --username=perovskite_migrator --dbname="$POSTGRES_DB"' > "$temporary_file"

test -s "$temporary_file"
mv -- "$temporary_file" "$backup_file"
sha256sum "$backup_file" > "$backup_file.sha256"
find "$backup_directory" -maxdepth 1 -type f \
    \( -name 'perovskite_registry-*.dump' -o -name 'perovskite_registry-*.dump.sha256' \) \
    -mtime "+$retention_days" -delete
echo "Created PostgreSQL backup: $backup_file"
