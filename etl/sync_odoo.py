"""Sync real leads from Odoo CRM into the analytics database (incremental).

Design: docs/etl-design.md

Run:
    python etl/sync_odoo.py                 normal run: from the last successful watermarks
    python etl/sync_odoo.py --full          re-read everything (ignores watermarks)
    python etl/sync_odoo.py --dry-run       print what would be loaded; write nothing
    python etl/sync_odoo.py --dry-run --since "2026-11-26 17:00:00" --since-message-id 95

Needs the run-log table: analytics/migrations/001_etl_runs.sql
Exit code 0 = success, 1 = failed (the failure is also written to etl_runs).
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import psycopg
import requests
from dotenv import load_dotenv

load_dotenv()

ODOO_URL = os.environ["ODOO_URL"]
HEADERS = {"Authorization": f"bearer {os.environ['ODOO_API_KEY']}",
           "X-Odoo-Database": os.environ["ODOO_DB"]}
INCLUDE_ARCHIVED = {"active_test": False}   # lost leads are archived in Odoo

SPAM_REASON = "Not genuine / spam"
CUSTOMER_TYPES = {"Buyer", "Distributor", "Importer"}
KNOWN_SOURCES = {"Web form", "WhatsApp", "Email", "Referral"}
LEAD_FIELDS = ["id", "type", "create_date", "write_date", "date_conversion", "date_closed",
               "stage_id", "active", "lost_reason_id", "source_id", "tag_ids", "expected_revenue"]


# ---------------------------------------------------------------------------
# Extract: small helpers around the Odoo JSON-2 API
# ---------------------------------------------------------------------------

def odoo(model, method, retries=3, **params):
    """Call Odoo. Every call in this script only reads, so retrying is safe."""
    error = ""
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(f"{ODOO_URL}/json/2/{model}/{method}",
                              headers=HEADERS, json=params, timeout=30)
            if r.status_code < 500:
                r.raise_for_status()          # 4xx = our mistake: fail now, don't retry
                return r.json()
            error = f"HTTP {r.status_code}: {r.text[:200]}"
        except (requests.ConnectionError, requests.Timeout) as e:
            error = str(e)
        if attempt < retries:
            time.sleep(2 * attempt)           # wait 2 s, then 4 s
    raise RuntimeError(f"Odoo {model}.{method} failed after {retries} tries: {error}")


def parse_utc(value):
    """Odoo returns '2026-11-26 16:57:24' in UTC with no zone marker, or False."""
    if not value:
        return None
    return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def name_of(link):
    """Odoo links come back as [id, 'Name'] or False."""
    return link[1] if link else None


def get_lookups():
    """Small reference lists read on every run: stages, tags, staff, the 'Discussions' subtype."""
    stages = {s["id"]: s for s in odoo("crm.stage", "search_read", domain=[],
                                         fields=["id", "name", "is_won"])}
    tags = {t["id"]: t["name"] for t in odoo("crm.tag", "search_read", domain=[],
                                              fields=["id", "name"])}
    # Partners that belong to internal users (staff), including archived users.
    users = odoo("res.users", "search_read", domain=[["share", "=", False]],
                 fields=["partner_id"], context=INCLUDE_ARCHIVED)
    staff_partners = {u["partner_id"][0] for u in users if u["partner_id"]}
    # 'Discussions' found by its technical id (mail.mt_comment), not by its translatable name.
    xmlid = odoo("ir.model.data", "search_read",
                 domain=[["module", "=", "mail"], ["name", "=", "mt_comment"]], fields=["res_id"])
    return stages, tags, staff_partners, xmlid[0]["res_id"]


def get_changed_leads(since):
    """Leads created or changed since the watermark (all leads on the first run)."""
    domain = [["write_date", ">=", since]] if since else []
    return odoo("crm.lead", "search_read", domain=domain, fields=LEAD_FIELDS,
                context=INCLUDE_ARCHIVED, order="id")


def get_new_replies(since_message_id, discussions_id):
    """Replies posted after the message watermark. Replies don't change a lead's write_date."""
    return odoo("mail.message", "search_read", domain=[
        ["model", "=", "crm.lead"], ["message_type", "=", "comment"],
        ["subtype_id", "=", discussions_id], ["id", ">", since_message_id or 0]],
        fields=["id", "res_id"], order="id")


def get_leads_by_id(ids):
    if not ids:
        return []
    return odoo("crm.lead", "search_read", domain=[["id", "in", sorted(ids)]],
                fields=LEAD_FIELDS, context=INCLUDE_ARCHIVED, order="id")


def get_all_lead_ids():
    """Ids only: cheap. Used to find leads deleted in Odoo."""
    return set(odoo("crm.lead", "search", domain=[], context=INCLUDE_ARCHIVED))


def get_stage_changes(lead_ids):
    """{lead_id: [(stage name, changed at), ...]} from Odoo's tracked stage changes."""
    if not lead_ids:
        return {}
    tracking = odoo("mail.tracking.value", "search_read", domain=[
        ["field_id.model", "=", "crm.lead"], ["field_id.name", "=", "stage_id"],
        ["mail_message_id.model", "=", "crm.lead"],
        ["mail_message_id.res_id", "in", sorted(lead_ids)]],
        fields=["mail_message_id", "new_value_char", "create_date"])
    if not tracking:
        return {}
    # Each tracking row points to a message; the message knows which lead it belongs to.
    message_ids = sorted({t["mail_message_id"][0] for t in tracking})
    messages = odoo("mail.message", "search_read", domain=[["id", "in", message_ids]],
                    fields=["id", "res_id"])
    lead_of_message = {m["id"]: m["res_id"] for m in messages}
    changes = {}
    for t in tracking:
        lead_id = lead_of_message[t["mail_message_id"][0]]
        changes.setdefault(lead_id, []).append((t["new_value_char"], parse_utc(t["create_date"])))
    return changes


def get_first_replies(lead_ids, discussions_id, staff_partners):
    """{lead_id: time of the first 'Discussions' message written by staff}."""
    if not lead_ids or not staff_partners:
        return {}
    messages = odoo("mail.message", "search_read", domain=[
        ["model", "=", "crm.lead"], ["res_id", "in", sorted(lead_ids)],
        ["message_type", "=", "comment"], ["subtype_id", "=", discussions_id],
        ["author_id", "in", sorted(staff_partners)]],
        fields=["res_id", "date"], order="date")
    first = {}
    for m in messages:
        first.setdefault(m["res_id"], parse_utc(m["date"]))   # ordered by date: first one wins
    return first


# ---------------------------------------------------------------------------
# Transform: Odoo's shape -> the analytics tables' shape
# ---------------------------------------------------------------------------

def transform_lead(rec, stages, tags, first_reply):
    tag_names = {tags.get(t) for t in rec["tag_ids"]}
    lost_reason = name_of(rec["lost_reason_id"])
    stage = stages.get(rec["stage_id"][0]) if rec["stage_id"] else None
    created = parse_utc(rec["create_date"])

    if stage and stage["is_won"]:
        outcome = "won"
    elif not rec["active"]:
        outcome = "lost"
    else:
        outcome = "open"

    closed = parse_utc(rec["date_closed"])
    if outcome == "lost" and closed is None:
        closed = parse_utc(rec["write_date"])     # n8n closes spam without date_closed
    if outcome == "open":
        closed = None

    reply = first_reply.get(rec["id"])
    if reply and reply < created:
        reply = None                              # a reply can't come before the enquiry

    source = name_of(rec["source_id"]) or "Unknown"
    customer_type = next((t for t in sorted(tag_names - {None}) if t in CUSTOMER_TYPES), "Unknown")
    revenue = rec["expected_revenue"] or None

    return {
        "lead_id": rec["id"],
        "created_at": created,
        "source": source,
        "customer_type": customer_type,
        "vehicle": None, "quantity": None, "destination_country": None,   # decision A
        "budget_aed": revenue,
        "urgent": "Urgent" in tag_names,
        "genuine": lost_reason != SPAM_REASON,
        "first_response_at": reply,
        "outcome": outcome,
        "lost_reason": lost_reason if outcome == "lost" else None,
        "closed_at": closed,
        "expected_revenue": revenue,
        "is_synthetic": False,
    }


def transform_events(rec, stage_changes):
    """Full stage history for one lead: Lead, New (on conversion), then every tracked move."""
    created = parse_utc(rec["create_date"])
    events = {("Lead", created)}
    if rec["type"] == "opportunity":
        events.add(("New", parse_utc(rec["date_conversion"]) or created))
    for stage_name, changed_at in stage_changes.get(rec["id"], []):
        events.add((stage_name, changed_at))
    return [(rec["id"], name, at) for name, at in sorted(events, key=lambda e: e[1])]


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------

def extract_and_transform(since=None, since_message_id=None):
    stages, tags, staff_partners, discussions_id = get_lookups()

    changed = get_changed_leads(since)
    replies = get_new_replies(since_message_id, discussions_id)

    # Leads with a new reply but no other change still need re-processing.
    changed_ids = {r["id"] for r in changed}
    reply_only_ids = {m["res_id"] for m in replies} - changed_ids
    records = changed + get_leads_by_id(reply_only_ids)
    ids = {r["id"] for r in records}

    stage_changes = get_stage_changes(ids)
    first_replies = get_first_replies(ids, discussions_id, staff_partners)

    leads = [transform_lead(r, stages, tags, first_replies) for r in records]
    events = [e for r in records for e in transform_events(r, stage_changes)]

    # New watermarks: the highest values actually read (not the clock), kept if nothing new.
    new_since = max((r["write_date"] for r in changed), default=since)
    new_message_id = max((m["id"] for m in replies), default=since_message_id)

    return {"leads": leads, "events": events, "odoo_ids": get_all_lead_ids(),
            "watermarks": {"leads_write_date": new_since, "message_id": new_message_id}}


# ---------------------------------------------------------------------------
# Load: everything for one run in one transaction
# ---------------------------------------------------------------------------

LEAD_COLUMNS = ["lead_id", "created_at", "source", "customer_type", "vehicle", "quantity",
                "budget_aed", "destination_country", "urgent", "genuine", "first_response_at",
                "outcome", "lost_reason", "closed_at", "expected_revenue", "is_synthetic"]

UPSERT_LEAD = f"""
    INSERT INTO leads ({", ".join(LEAD_COLUMNS)})
    VALUES ({", ".join(["%s"] * len(LEAD_COLUMNS))})
    ON CONFLICT (lead_id) DO UPDATE SET
        {", ".join(f"{c} = EXCLUDED.{c}" for c in LEAD_COLUMNS if c != "lead_id")},
        loaded_at = now()
    WHERE leads.is_synthetic = false
"""  # the WHERE guard: a real lead can never overwrite a synthetic row


def connect():
    return psycopg.connect(
        host=os.environ.get("ANALYTICS_DB_HOST", "localhost"),
        port=os.environ.get("ANALYTICS_DB_PORT", "5433"),
        dbname="analytics", user="analytics",
        password=os.environ["ANALYTICS_DB_PASSWORD"],
        autocommit=True)   # each conn.transaction() block is then one real transaction


def last_watermarks(conn):
    """Watermarks of the last successful run, as Odoo expects them; (None, None) on the first run."""
    row = conn.execute("""
        SELECT leads_write_date, message_id FROM etl_runs
        WHERE status = 'success' ORDER BY run_id DESC LIMIT 1""").fetchone()
    if not row or row[0] is None:
        return None, (row[1] if row else None)
    return row[0].astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), row[1]


def load(conn, result, started_at):
    leads, events, odoo_ids = result["leads"], result["events"], result["odoo_ids"]
    with conn.transaction():
        with conn.cursor() as cur:
            # 1. Leads: insert new ones, update changed ones.
            cur.executemany(UPSERT_LEAD, [[lead[c] for c in LEAD_COLUMNS] for lead in leads])

            # 2. Stage history: rebuild it completely for every lead in this run.
            lead_ids = [lead["lead_id"] for lead in leads]
            cur.execute("DELETE FROM stage_events WHERE lead_id = ANY(%s)", (lead_ids,))
            cur.executemany("INSERT INTO stage_events (lead_id, stage, entered_at) VALUES (%s, %s, %s)",
                            events)

            # 3. Leads deleted in Odoo: remove them here too (their events go with them).
            if not odoo_ids:
                real = cur.execute("SELECT count(*) FROM leads WHERE NOT is_synthetic").fetchone()[0]
                if real:   # an empty answer from Odoo is more likely a fault than a mass delete
                    raise RuntimeError("Odoo returned no lead ids; refusing to delete all real leads")
            cur.execute("""DELETE FROM leads WHERE NOT is_synthetic AND NOT (lead_id = ANY(%s))
                           RETURNING lead_id""", (sorted(odoo_ids),))
            deleted = [r[0] for r in cur.fetchall()]

            # 4. Run log, with the new watermarks. Saved only if everything above worked.
            wm = result["watermarks"]
            cur.execute("""
                INSERT INTO etl_runs (started_at, status, leads_write_date, message_id,
                                      leads_upserted, events_written, leads_deleted)
                VALUES (%s, 'success', %s, %s, %s, %s, %s)""",
                (started_at, parse_utc(wm["leads_write_date"]), wm["message_id"],
                 len(leads), len(events), len(deleted)))
    return len(leads), len(events), deleted


def log_failure(started_at, error):
    """Written in its own connection, because the run's transaction was rolled back."""
    try:
        with connect() as conn:
            conn.execute("INSERT INTO etl_runs (started_at, status, error) VALUES (%s, 'failed', %s)",
                         (started_at, str(error)[:2000]))
    except Exception as e:
        print(f"Could not write the failure to etl_runs: {e}", file=sys.stderr)


def print_dry_run(result):
    print(f"Leads to load: {len(result['leads'])}")
    for lead in result["leads"]:
        print("  " + json.dumps(lead, default=str))
        if lead["source"] not in KNOWN_SOURCES:
            print(f"  ! unknown source '{lead['source']}' on lead {lead['lead_id']}")
    print(f"Stage events to write: {len(result['events'])}")
    for lead_id, stage, at in result["events"]:
        print(f"  {lead_id:>6}  {at:%Y-%m-%d %H:%M:%S}Z  {stage}")
    print(f"Lead ids in Odoo: {sorted(result['odoo_ids'])}")
    print(f"New watermarks: {result['watermarks']}")


def main():
    parser = argparse.ArgumentParser(description="Sync Odoo leads into the analytics database.")
    parser.add_argument("--dry-run", action="store_true", help="print what would be loaded; write nothing")
    parser.add_argument("--full", action="store_true", help="ignore watermarks and re-read everything")
    parser.add_argument("--since", help="dry run only: lead watermark, e.g. '2026-11-26 17:00:00' (UTC)")
    parser.add_argument("--since-message-id", type=int, help="dry run only: message watermark")
    args = parser.parse_args()

    if args.dry_run:
        print_dry_run(extract_and_transform(args.since, args.since_message_id))
        return

    started_at = datetime.now(timezone.utc)
    try:
        with connect() as conn:
            since, since_message_id = (None, None) if args.full else last_watermarks(conn)
            result = extract_and_transform(since, since_message_id)
            upserted, written, deleted = load(conn, result, started_at)
        print(f"{started_at:%Y-%m-%d %H:%M:%S}Z  success  since={since}  leads={upserted}  "
              f"events={written}  deleted={deleted}  watermarks={result['watermarks']}")
    except Exception as e:
        log_failure(started_at, e)
        print(f"{started_at:%Y-%m-%d %H:%M:%S}Z  FAILED  {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
