# sql

Reporting views on the analytics database. Power BI reads these through the read-only `powerbi_reader` login.

Views are kept here, not in `analytics/init/`, because init scripts only run when the database is first created. Apply a file from PowerShell in the repo folder:

```powershell
Get-Content sql\01_funnel.sql | docker compose exec -T analytics-db psql -U analytics -d analytics -v ON_ERROR_STOP=1
```

Apply the files in number order, because later views read from earlier ones. Every file uses `CREATE OR REPLACE VIEW`, so running it again is safe.

All views count **genuine leads only** (spam is left out).

| File | View | One row per | Shows |
|---|---|---|---|
| `01_funnel.sql` | `v_funnel` | stage | Leads that ever reached each stage |
| `02_stage_conversion.sql` | `v_stage_conversion` | stage | % moving on from the previous stage and from the top |
| `03_response_time.sql` | `v_lead_response` | lead | Minutes to first reply and a reply-speed bucket |
| | `v_response_buckets` | bucket | Win rate (won ÷ won + lost) by reply speed |
| | `v_response_by_source` | source | Median and average reply time |
| `04_lost_and_stage_time.sql` | `v_lost_deals` | lost lead | Lost reason and the last stage reached |
| | `v_lost_reasons` | reason | Lost deals by reason, with share of total |
| | `v_stage_visits` | stage visit | When a lead entered and left each stage |
| | `v_time_in_stage` | stage | Median days spent in each stage |

Reply times are clock time, not business hours. The history is synthetic, so the patterns repeat the generator's assumptions (see `analytics/generate_history.py`).
