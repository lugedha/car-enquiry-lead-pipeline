import os
import requests
from dotenv import load_dotenv

load_dotenv()
URL = os.environ["ODOO_URL"]
HEADERS = {"Authorization": f"bearer {os.environ['ODOO_API_KEY']}",
           "X-Odoo-Database": os.environ["ODOO_DB"]}

def call(model, method, **params):
    r = requests.post(f"{URL}/json/2/{model}/{method}", json=params,
                      headers=HEADERS, timeout=15)
    if not r.ok:
        print("Odoo error:", r.status_code, r.text[:500])
    r.raise_for_status()
    return r.json()

def find_id(model, name):
    rows = call(model, "search_read", domain=[["name", "=", name]],
                fields=["id"], limit=1)
    if not rows:
        raise SystemExit(f"{model} '{name}' not found in Odoo")
    return rows[0]["id"]

enquiry = {
    "name": "Fatima Test",
    "phone": "+971500000002",
    "email": "fatima@example.test",
    "message": "Need 5 used Hilux pickups for export to Tanzania, budget AED 400k.",
    "source": "Web form",
    "customer_type": "Distributor",
}

# 1. Is there already an open lead for this phone or email?
existing = call("crm.lead", "search_read",
                domain=[["stage_id.is_won", "=", False],
                        "|", ["phone", "=", enquiry["phone"]],
                             ["email_from", "=", enquiry["email"]]],
                fields=["id", "name"], limit=1)

if existing:
    # 2a. Yes: add the new message as a note. Do not create a second lead.
    lead_id = existing[0]["id"]
    call("crm.lead", "message_post", ids=[lead_id],
         body=f"New enquiry from same contact: {enquiry['message']}")
    print(f"Duplicate. Note added to lead {lead_id}: {existing[0]['name']}")
else:
    # 2b. No: create a new lead.
    new_ids = call("crm.lead", "create", vals_list=[{
        "type": "lead",
        "name": f"Hilux enquiry - {enquiry['name']} (test)",
        "contact_name": enquiry["name"],
        "phone": enquiry["phone"],
        "email_from": enquiry["email"],
        "description": enquiry["message"],
        "source_id": find_id("utm.source", enquiry["source"]),
        "tag_ids": [[6, 0, [find_id("crm.tag", enquiry["customer_type"])]]],
    }])
    print("Created lead:", new_ids)