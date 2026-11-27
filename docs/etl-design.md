# ETL design: Odoo CRM → analytics database

**Version 1.0 · status: agreed, not built yet**

A scheduled Python job that copies real leads and their stage history from Odoo into the analytics database, so the SQL views and the Power BI dashboard work on live data next to the synthetic history.

## 1. Decisions

| Decision | Choice | Why |
|---|---|---|
| Load style | **Incremental** with watermarks | Only what changed since the last successful run is read. Scales with Odoo, keeps API calls small. |
| Write style | **Upsert** (`INSERT … ON CONFLICT DO UPDATE`) in **one transaction** per run | Re-running is safe (idempotent); a failed run changes nothing. |
| Vehicle, quantity, destination for real leads | **Left empty (NULL)** | They are not Odoo fields, only text in the description. Proper fix later: Odoo custom fields filled by n8n. |
| Phone, name, email, message text | **Not copied** | Reporting does not need personal data. |
| Stage matching | **By name** | Odoo stage ids and sequence numbers do not match the analytics `stages` table. |

## 2. What Odoo holds (from `odoo/explore_for_etl.py`, Nov 2026)

- n8n creates `crm.lead` records with `type = lead`. Converting to an opportunity sets `date_conversion`.
- Stage history is in `mail.tracking.value` (old and new stage **names**, `create_date`). Each row points to a `mail.message`; the message's `res_id` is the lead id.
- A reply to the customer is a `mail.message` with `message_type = comment` and subtype **Discussions**. A Log note has subtype Note.
- All Odoo datetimes are returned in **UTC without a zone marker**.
- Spam leads created by n8n are archived with lost reason "Not genuine / spam" but **no `date_closed`**.
- Posting a message on a lead does **not** change the lead's `write_date`.

## 3. Watermarks (what "changed since last run" means)

Two watermarks are kept, because one is not enough:

| Watermark | Catches | Rule |
|---|---|---|
| `leads_write_date` | New leads, stage changes, won/lost, edits | Read leads with `write_date >= watermark` |
| `message_id` | Replies posted later (they don't touch `write_date`) | Read Discussions messages on leads with `id > watermark`, then re-process those leads |

- The new watermark is the **highest value actually read**, not the clock time of the run, so records saved while the run is going are not skipped.
- `>=` on `write_date` re-reads the boundary records. That is harmless because loading is an upsert.
- Watermarks are only saved when the run **succeeds**.

**Deletes:** an incremental read cannot see leads deleted in Odoo. Each run also fetches the list of all lead ids (ids only, cheap) and removes real rows (`is_synthetic = false`) whose id no longer exists in Odoo.

## 4. Field mapping: `leads`

| Analytics column | From Odoo | Rule |
|---|---|---|
| `lead_id` | `id` | Odoo ids are far below 1,000,000, so they never clash with synthetic ids |
| `created_at` | `create_date` | Label as UTC |
| `source` | `source_id` name | Must be Web form, WhatsApp, Email or Referral; missing → `Unknown` |
| `customer_type` | tag names | Buyer, Distributor or Importer tag; none → `Unknown` |
| `vehicle`, `quantity`, `destination_country` | — | NULL (decision A) |
| `budget_aed` | `expected_revenue` | 0 → NULL |
| `urgent` | tag names | `true` if the Urgent tag is present |
| `genuine` | `lost_reason_id` name | `false` if "Not genuine / spam", otherwise `true` |
| `first_response_at` | `mail.message` | Earliest Discussions message on the lead written by an **internal user**, at or after `create_date`; none → NULL |
| `outcome` | stage, `active` | Stage `is_won` → `won`; archived → `lost`; otherwise `open` |
| `lost_reason` | `lost_reason_id` name | Only when lost |
| `closed_at` | `date_closed` | Lost without `date_closed` → `write_date` |
| `expected_revenue` | `expected_revenue` | As is |
| `is_synthetic` | — | `false` |
| `loaded_at` | — | Time of the load |

## 5. Field mapping: `stage_events`

For every lead that changed in this run, its stage history is **rebuilt completely** (delete that lead's rows, insert fresh), so moves backwards and forwards are always right.

| Event | Entered at |
|---|---|
| `Lead` | `create_date` (every lead) |
| `New` | `date_conversion` if converted; opportunity created directly → `create_date` |
| Later stages | each `mail.tracking.value` row: `new_value_char` at its `create_date` |

A stage name that does not exist in `stages` makes the run fail (foreign key). That is deliberate: a renamed Odoo stage must be noticed, not loaded silently.

## 6. Run log: `etl_runs` (new table)

| Column | Meaning |
|---|---|
| `run_id` | Sequence number |
| `started_at`, `finished_at` | Run times |
| `status` | `success` or `failed` |
| `leads_write_date`, `message_id` | Watermarks reached (success only) |
| `leads_upserted`, `events_written`, `leads_deleted` | Counts |
| `error` | Error text when failed |

The first run has no watermark, so it reads everything (an initial full load). The run log also lets the dashboard show "data as of".

## 7. Failure handling

- Everything for one run happens in one database transaction. On any error: roll back, write a `failed` row to `etl_runs` (separate transaction), exit with an error code.
- API calls have timeouts; read calls retry with a short wait (reads are safe to retry).
- The schedule (step 6) alerts when a run fails or when no successful run happened for a day.

## 8. Known limits

- Replies made outside Odoo (WhatsApp, phone) are not seen, so `first_response_at` is empty or late for those leads.
- n8n and staff post as the same Odoo user today. If n8n ever posts a Discussions message, it would count as a reply. Fix: a separate integration user for the API.
- Vehicle, quantity and destination are empty for real leads (decision A).
- Expected revenue comes from the classifier, which mis-reads "per vehicle" budgets (seen live: 10 units at 90k each → 90,000). Fixed on the `classifier-v3` branch, not yet merged.
