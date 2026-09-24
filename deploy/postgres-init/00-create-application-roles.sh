#!/usr/bin/env bash
set -Eeuo pipefail

: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${PEROVSKITE_MIGRATOR_PASSWORD:?PEROVSKITE_MIGRATOR_PASSWORD is required}"
: "${PEROVSKITE_APP_PASSWORD:?PEROVSKITE_APP_PASSWORD is required}"

if [[ "${POSTGRES_USER}" == "perovskite_app" || "${POSTGRES_USER}" == "perovskite_migrator" ]]; then
    echo "POSTGRES_USER must be a separate bootstrap administrator." >&2
    exit 1
fi

psql --set=ON_ERROR_STOP=1 \
    --username "${POSTGRES_USER}" \
    --dbname "${POSTGRES_DB}" \
    --set=database_name="${POSTGRES_DB}" \
    --set=migrator_password="${PEROVSKITE_MIGRATOR_PASSWORD}" \
    --set=app_password="${PEROVSKITE_APP_PASSWORD}" <<'SQL'
CREATE ROLE perovskite_migrator
    LOGIN PASSWORD :'migrator_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE perovskite_app
    LOGIN PASSWORD :'app_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

REVOKE ALL PRIVILEGES ON DATABASE :"database_name" FROM PUBLIC;
ALTER DATABASE :"database_name" OWNER TO perovskite_migrator;
GRANT CONNECT ON DATABASE :"database_name" TO perovskite_app;

ALTER SCHEMA public OWNER TO perovskite_migrator;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO perovskite_app;

ALTER DEFAULT PRIVILEGES FOR ROLE perovskite_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO perovskite_app;
ALTER DEFAULT PRIVILEGES FOR ROLE perovskite_migrator IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO perovskite_app;
ALTER DEFAULT PRIVILEGES FOR ROLE perovskite_migrator IN SCHEMA public
    GRANT USAGE ON TYPES TO perovskite_app;
SQL
