-- Lost deals and time in stage.

-- 1) Lost genuine deals: the reason, and the last stage each one reached.
CREATE OR REPLACE VIEW v_lost_deals AS
WITH last_stage AS (
    SELECT lead_id,
           stage,
           ROW_NUMBER() OVER (PARTITION BY lead_id ORDER BY entered_at DESC) AS rn
    FROM stage_events
)
SELECT l.lead_id,
       l.source,
       l.customer_type,
       l.closed_at,
       COALESCE(l.lost_reason, 'Not recorded') AS lost_reason,
       ls.stage                                AS lost_at_stage,
       s.sequence                              AS lost_at_sequence
FROM leads l
JOIN last_stage ls ON ls.lead_id = l.lead_id AND ls.rn = 1
JOIN stages s      ON s.stage = ls.stage
WHERE l.outcome = 'lost'
  AND l.genuine;

-- 2) Lost reasons ranked, with each reason's share of all lost deals.
CREATE OR REPLACE VIEW v_lost_reasons AS
SELECT lost_reason,
       count(*)                                               AS deals,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1)     AS pct_of_lost
FROM v_lost_deals
GROUP BY lost_reason;

-- 3) Every stage visit, with when the lead left it.
--    Left = when the next stage started, or when the deal was closed.
CREATE OR REPLACE VIEW v_stage_visits AS
SELECT e.lead_id,
       e.stage,
       e.entered_at,
       COALESCE(
           LEAD(e.entered_at) OVER (PARTITION BY e.lead_id ORDER BY e.entered_at),
           l.closed_at
       ) AS left_at
FROM stage_events e
JOIN leads l ON l.lead_id = e.lead_id
WHERE l.genuine;

-- 4) Median days spent in each stage (finished visits only; the final Won stage has no duration).
CREATE OR REPLACE VIEW v_time_in_stage AS
SELECT s.sequence,
       v.stage,
       count(*) AS finished_visits,
       round(percentile_cont(0.5) WITHIN GROUP (
                 ORDER BY extract(epoch FROM v.left_at - v.entered_at) / 86400
             )::numeric, 1) AS median_days
FROM v_stage_visits v
JOIN stages s ON s.stage = v.stage
WHERE v.left_at IS NOT NULL
  AND v.stage <> 'Won - Deposit Paid'
GROUP BY s.sequence, v.stage;