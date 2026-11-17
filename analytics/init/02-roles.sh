#!/bin/sh
# Creates a read-only login for Power BI.
# Runs once, after 01-schema.sql, the first time the container starts.
# The password comes from the POWERBI_READER_PASSWORD environment variable (set in .env),
# so it is never written in this file.
set -e

psql -v ON_ERROR_STOP=1 \
     -v reader_password="$POWERBI_READER_PASSWORD" \
     --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'EOSQL'
CREATE ROLE powerbi_reader LOGIN PASSWORD :'reader_password';
GRANT CONNECT ON DATABASE analytics TO powerbi_reader;
GRANT USAGE ON SCHEMA public TO powerbi_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO powerbi_reader;
-- Tables and views created later are readable too, without granting each one.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO powerbi_reader;
EOSQL
