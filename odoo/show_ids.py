"""Print the Odoo ids that the n8n "Build Odoo lead" node needs.

Run:  python odoo/show_ids.py
Then copy the three printed lines into the top of that n8n Code node.
Run it again if tags, sources or lost reasons are ever recreated in Odoo.
"""
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
    r.raise_for_status()
    return r.json()


def ids_by_name(model, names):
    rows = call(model, "search_read", domain=[["name", "in", list(names)]],
                fields=["id", "name"])
    found = {row["name"]: row["id"] for row in rows}
    missing = [n for n in names if n not in found]
    if missing:
        raise SystemExit(f"Not found in {model}: {missing}")
    return found


tags = ids_by_name("crm.tag", ["Buyer", "Distributor", "Importer", "Urgent"])
sources = ids_by_name("utm.source", ["Web form", "WhatsApp", "Email", "Referral"])
reasons = ids_by_name("crm.lost.reason", ["Not genuine / spam"])

# The keys on the left are the "source" values the web form sends.
source_keys = {"web_form": "Web form", "whatsapp": "WhatsApp",
               "email": "Email", "referral": "Referral"}

print("Copy these three lines into the n8n 'Build Odoo lead' node:\n")
print("const TAG_IDS = { " + ", ".join(f"{k}: {v}" for k, v in tags.items()) + " };")
print("const SOURCE_IDS = { " + ", ".join(f"{k}: {sources[n]}" for k, n in source_keys.items()) + " };")
print(f"const SPAM_REASON_ID = {reasons['Not genuine / spam']};")
