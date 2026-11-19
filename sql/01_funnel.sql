-- Funnel: how many genuine leads ever reached each stage.
-- Spam (genuine = false) is left out so it doesn't swell the top of the funnel.
CREATE OR REPLACE VIEW v_funnel AS
WITH genuine_events AS (
    SELECT e.lead_id, e.stage
    FROM stage_events e
    JOIN leads l ON l.lead_id = e.lead_id
    WHERE l.genuine
)
SELECT s.sequence,
       s.stage,
       count(DISTINCT g.lead_id) AS leads_reached
FROM stages s
LEFT JOIN genuine_events g ON g.stage = s.stage
GROUP BY s.sequence, s.stage;