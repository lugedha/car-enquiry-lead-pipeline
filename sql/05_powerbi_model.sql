-- Views shaped for the Power BI model.
-- Times are converted to Dubai time here, so Power BI never has to deal with UTC.
-- Genuine leads only, like every other view.

-- Fact 1: one row per genuine lead.
CREATE OR REPLACE VIEW v_pbi_leads AS
SELECT l.lead_id,
       (l.created_at AT TIME ZONE 'Asia/Dubai')        AS created_at_dubai,
       (l.created_at AT TIME ZONE 'Asia/Dubai')::date  AS created_date,
       l.source,
       l.customer_type,
       l.vehicle,
       l.quantity,
       l.budget_aed,
       l.destination_country,
       l.urgent,
       l.outcome,
       l.lost_reason,
       d.lost_at_stage,
       (l.closed_at AT TIME ZONE 'Asia/Dubai')::date   AS closed_date,
       l.expected_revenue,
       r.reply_minutes,
       r.reply_bucket,
       r.bucket_order,
       l.is_synthetic
FROM leads l
JOIN v_lead_response r  ON r.lead_id = l.lead_id      -- genuine leads only
LEFT JOIN v_lost_deals d ON d.lead_id = l.lead_id;    -- filled for lost deals only

-- Fact 2: one row per stage visit of a genuine lead.
CREATE OR REPLACE VIEW v_pbi_stage_visits AS
SELECT v.lead_id,
       v.stage,
       (v.entered_at AT TIME ZONE 'Asia/Dubai')        AS entered_at_dubai,
       (v.left_at    AT TIME ZONE 'Asia/Dubai')        AS left_at_dubai,
       round((extract(epoch FROM v.left_at - v.entered_at) / 86400)::numeric, 2) AS days_in_stage
FROM v_stage_visits v;