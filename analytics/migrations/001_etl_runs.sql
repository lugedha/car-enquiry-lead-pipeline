-- Run log for etl/sync_odoo.py: one row per run, with the watermarks it reached.
-- Apply once (PowerShell, repo folder):
--   Get-Content analytics\migrations\001_etl_runs.sql | docker compose exec -T analytics-db psql -U analytics -d analytics -v ON_ERROR_STOP=1
CREATE TABLE IF NOT EXISTS etl_runs (
    run_id            bigserial PRIMARY KEY,
    started_at        timestamptz NOT NULL,
    finished_at       timestamptz NOT NULL DEFAULT now(),
    status            text NOT NULL CHECK (status IN ('success', 'failed')),
    leads_write_date  timestamptz,   -- lead watermark reached (success only)
    message_id        bigint,        -- message watermark reached (success only)
    leads_upserted    integer,
    events_written    integer,
    leads_deleted     integer,
    error             text
);
