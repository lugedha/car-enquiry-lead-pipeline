-- Conversion: share of leads that moved on from the previous stage, and from the top.
-- Built on v_funnel, so it uses genuine leads only.
CREATE OR REPLACE VIEW v_stage_conversion AS
SELECT sequence,
       stage,
       leads_reached,
       LAG(leads_reached) OVER (ORDER BY sequence) AS prev_stage_leads,
       round(100.0 * leads_reached
             / NULLIF(LAG(leads_reached) OVER (ORDER BY sequence), 0), 1) AS pct_from_prev,
       round(100.0 * leads_reached
             / NULLIF(first_value(leads_reached) OVER (ORDER BY sequence), 0), 1) AS pct_from_top
FROM v_funnel;