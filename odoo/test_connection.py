import os
import requests
from dotenv import load_dotenv

load_dotenv()
URL = os.environ["ODOO_URL"]
DB = os.environ["ODOO_DB"]
KEY = os.environ["ODOO_API_KEY"]

HEADERS = {"Authorization": f"bearer {KEY}", "X-Odoo-Database": DB}

def call(model, method, **params):
    """Call one Odoo method through the JSON-2 API."""
    r = requests.post(f"{URL}/json/2/{model}/{method}", json=params,
                      headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()

print("Pipeline stages:")
for s in call("crm.stage", "search_read",
              domain=[], fields=["name", "sequence", "is_won"], order="sequence"):
    print(f"  {s['sequence']:>3}  {s['name']}{'  (WON)' if s['is_won'] else ''}")

print("\nLost deals:")
for d in call("crm.lead", "search_read",
              domain=[["active", "=", False]],
              fields=["name", "expected_revenue", "lost_reason_id", "source_id"]):
    print(f"  {d['name']} | AED {d['expected_revenue']:,.0f} | "
          f"{d['lost_reason_id']} | source: {d['source_id']}")