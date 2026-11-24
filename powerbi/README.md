# powerbi

Power BI dashboard on the analytics database: funnel, conversion, response time and lost deals.
The `.pbix` file is not committed (it is binary and holds a copy of the data); screenshots are in `docs/images/`.

## Connection

PostgreSQL connector, server `localhost:5433`, database `analytics`, **Import** mode, signed in as the read-only `powerbi_reader`.
The local database has no SSL, so Power BI asks to connect without encryption; a real server would use SSL.
Publishing to the Power BI Service with scheduled refresh would need an on-premises data gateway on the machine that runs the database.

## Model

| Table | Source view | One row per | Role |
|---|---|---|---|
| Leads | `v_pbi_leads` | genuine lead | Main fact table |
| Stage visits | `v_pbi_stage_visits` | stage visit | Funnel and time-in-stage detail |
| Stages | `stages` | stage | Dimension; `stage` sorted by `sequence` |
| Date | DAX `CALENDAR` (full months) | day | Marked date table; `Month` sorted by `Month Number` |

Relationships, all one-to-many and single direction:
- Date[Date] → Leads[created_date] (active)
- Date[Date] → Leads[closed_date] (inactive, used by `Won by Close Date`)
- Leads[lead_id] → Stage visits[lead_id]
- Stages[stage] → Stage visits[stage]

## Measures

| Measure | Definition |
|---|---|
| Leads | Genuine enquiries (spam excluded), by the date they arrived (Dubai time) |
| Won / Lost / Open Leads | Leads by outcome. `Won` counts by arrival month |
| Win Rate | Won ÷ (Won + Lost). Decided deals only; 0% (not blank) when deals were decided but none won |
| Leads Reached | Distinct leads that ever entered a stage |
| Conversion from Top % | Leads reaching the stage ÷ leads at the first stage |
| Conversion from Previous % | Leads reaching the stage ÷ leads reaching the stage before (stage numbers must have no gaps) |
| Median Days in Stage | Median days in a stage before moving on or closing; visits still in progress are ignored |
| Median Reply Minutes | Median clock minutes to first reply; unanswered leads ignored |
| Replied Within 15 Min % | Share of all genuine leads answered within 15 minutes; unanswered leads count as misses |
| No Reply Leads | Genuine leads that never got a reply |
| Leads Previous Month / Leads MoM % | Previous calendar month and change against it; the current month is month to date |
| Won by Close Date | Won deals in the month they closed |
| Won Revenue | Expected revenue (AED) of won deals, from the budget the customer stated; not invoiced revenue |

Every measure has the same description inside the model, so it shows as a tooltip in Power BI.

## Checks

A hidden **Checks** page holds tables that were reconciled against the SQL views (totals, monthly counts, conversion rates).
Reconciling caught two blank-handling bugs before the pages were built:
- `BLANK <= 15` is true in DAX, which counted unanswered leads as fast replies.
- A rate with no wins returned blank instead of 0%, which hid the "No reply" bucket.

## Caveats

- All data is synthetic, so the patterns repeat the generator's assumptions.
- Reply times are clock time, not business hours.
- Fast replies and wins are linked here, but that does not prove cause.
