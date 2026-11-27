"""Look at what Odoo stores for leads, before designing the ETL.

Run:  python odoo/explore_for_etl.py
Read-only: it only calls search_read.
"""
import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()
URL = os.environ["ODOO_URL"]
HEADERS = {"Authorization": f"bearer {os.environ['ODOO_API_KEY']}",
           "X-Odoo-Database": os.environ["ODOO_DB"]}
ALL = {"active_test": False}  # include archived (lost) records


def search_read(model, domain, fields, **extra):
    r = requests.post(f"{URL}/json/2/{model}/search_read", headers=HEADERS, timeout=30,
                      json={"domain": domain, "fields": fields, **extra})
    if not r.ok:
        print(f"!! {model}: {r.status_code} {r.text[:300]}")
        return []
    return r.json()


def show(title, rows):
    print(f"\n=== {title} ({len(rows)}) ===")
    for row in rows:
        print(json.dumps(row, ensure_ascii=False, default=str))


# 1. Pipeline stages: names, order, which one counts as won
show("Stages", search_read("crm.stage", [], ["id", "name", "sequence", "is_won"], order="sequence"))

# 2. Leads: the fields the analytics tables need
show("Leads", search_read("crm.lead", [], [
    "id", "type", "create_date", "write_date", "date_conversion", "date_closed",
    "stage_id", "active", "probability", "lost_reason_id", "source_id", "tag_ids",
    "expected_revenue", "phone",
], context=ALL))

# 3. Stage history: every stage change Odoo tracked
show("Stage changes", search_read("mail.tracking.value",
    [["field_id.name", "=", "stage_id"], ["mail_message_id.model", "=", "crm.lead"]],
    ["mail_message_id", "old_value_char", "new_value_char", "create_date"]))

# 4. Messages on leads: to find the first reply to the customer
show("Messages", search_read("mail.message",
    [["model", "=", "crm.lead"], ["message_type", "in", ["comment", "email"]]],
    ["res_id", "date", "message_type", "subtype_id", "author_id"], order="date"))