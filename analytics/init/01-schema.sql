-- Analytics database: the reporting copy of the sales pipeline.
-- Runs once, automatically, the first time the analytics-db container starts.
--
-- Why a separate database: Odoo is the operational system. Reports read from
-- this copy, so heavy queries never slow Odoo down, and history can be kept
-- even for test data that Odoo itself cannot backdate.

-- The ordered list of pipeline stages. Power BI uses "sequence" to sort the funnel.
CREATE TABLE stages (
    stage       text PRIMARY KEY,
    sequence    integer NOT NULL UNIQUE
);

INSERT INTO stages (stage, sequence) VALUES
    ('Lead',                         0),
    ('New',                          1),
    ('Qualified',                    2),
    ('Vehicle Sourced / Inspection', 3),
    ('Quotation Sent',               4),
    ('Negotiation',                  5),
    ('Won - Deposit Paid',           6);

-- One row per enquiry.
CREATE TABLE leads (
    lead_id             bigint PRIMARY KEY,   -- Odoo id for real leads; 1,000,000+ for generated history
    created_at          timestamptz NOT NULL, -- when the enquiry arrived
    source              text NOT NULL,        -- Web form, WhatsApp, Email, Referral
    customer_type       text NOT NULL,        -- Buyer, Distributor, Importer, Unknown
    vehicle             text,
    quantity            integer,
    budget_aed          numeric(14, 2),
    destination_country text,
    urgent              boolean NOT NULL DEFAULT false,
    genuine             boolean NOT NULL DEFAULT true,
    first_response_at   timestamptz,          -- first reply to the customer; NULL = not answered yet
    outcome             text NOT NULL DEFAULT 'open'
                        CHECK (outcome IN ('open', 'won', 'lost')),
    lost_reason         text,
    closed_at           timestamptz,          -- when it was won or lost
    expected_revenue    numeric(14, 2),
    is_synthetic        boolean NOT NULL DEFAULT false,  -- true = generated history, not from Odoo
    loaded_at           timestamptz NOT NULL DEFAULT now(),
    CHECK (closed_at IS NULL OR closed_at >= created_at),
    CHECK (first_response_at IS NULL OR first_response_at >= created_at)
);

-- One row each time a lead enters a stage. A lead that goes backwards
-- and forwards gets several rows, which is how time in stage is measured.
CREATE TABLE stage_events (
    lead_id     bigint NOT NULL REFERENCES leads (lead_id) ON DELETE CASCADE,
    stage       text   NOT NULL REFERENCES stages (stage),
    entered_at  timestamptz NOT NULL,
    PRIMARY KEY (lead_id, stage, entered_at)
);

CREATE INDEX stage_events_stage_idx ON stage_events (stage);
CREATE INDEX leads_created_at_idx   ON leads (created_at);
