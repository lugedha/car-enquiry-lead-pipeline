-- Response time: how fast each genuine lead got its first reply, and whether speed pays off.

-- 1) One row per genuine lead, with reply minutes and a reply-speed bucket.
CREATE OR REPLACE VIEW v_lead_response AS
WITH reply AS (
    SELECT lead_id,
           source,
           created_at,
           outcome,
           extract(epoch FROM first_response_at - created_at) / 60 AS reply_minutes
    FROM leads
    WHERE genuine
)
SELECT lead_id,
       source,
       created_at,
       outcome,
       round(reply_minutes, 1) AS reply_minutes,
       CASE
           WHEN reply_minutes IS NULL THEN 'No reply'
           WHEN reply_minutes <= 15   THEN 'Within 15 min'
           WHEN reply_minutes <= 60   THEN '15 to 60 min'
           WHEN reply_minutes <= 240  THEN '1 to 4 hours'
           ELSE 'Over 4 hours'
       END AS reply_bucket,
       CASE
           WHEN reply_minutes IS NULL THEN 5
           WHEN reply_minutes <= 15   THEN 1
           WHEN reply_minutes <= 60   THEN 2
           WHEN reply_minutes <= 240  THEN 3
           ELSE 4
       END AS bucket_order
FROM reply;

-- 2) Win rate by reply-speed bucket (decided deals only: won + lost).
CREATE OR REPLACE VIEW v_response_buckets AS
SELECT bucket_order,
       reply_bucket,
       count(*)                                                   AS leads,
       count(*) FILTER (WHERE outcome = 'won')                    AS won,
       count(*) FILTER (WHERE outcome IN ('won', 'lost'))         AS decided,
       round(100.0 * count(*) FILTER (WHERE outcome = 'won')
             / NULLIF(count(*) FILTER (WHERE outcome IN ('won', 'lost')), 0), 1) AS win_rate_pct
FROM v_lead_response
GROUP BY bucket_order, reply_bucket;

-- 3) Median and average reply time by source (unanswered leads are ignored).
CREATE OR REPLACE VIEW v_response_by_source AS
SELECT source,
       count(*)                                     AS leads,
       count(reply_minutes)                         AS answered,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY reply_minutes)::numeric, 1) AS median_minutes,
       round(avg(reply_minutes), 1)                 AS avg_minutes
FROM v_lead_response
GROUP BY source;