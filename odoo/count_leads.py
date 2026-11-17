"""Count leads and opportunities in Odoo, including archived (lost) ones.

Run:  python odoo/count_leads.py
Used to confirm Odoo is empty before loading generated data.
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()
URL = os.environ["ODOO_URL"]
HEADERS = {"Authorization": f"bearer {os.environ['ODOO_API_KEY']}",
           "X-Odoo-Database": os.environ["ODOO_DB"]}

# active_test=False makes Odoo include archived records (lost deals).
r = requests.post(f"{URL}/json/2/crm.lead/search_read", headers=HEADERS, timeout=15, json={
    "domain": [],
    "fields": ["id", "name", "type", "active"],
    "context": {"active_test": False},
})
r.raise_for_status()
rows = r.json()
print(f"Total records: {len(rows)}")
for row in rows:
    status = "active" if row["active"] else "archived"
    print(f"  {row['id']:>4}  {row['type']:<12} {status:<9} {row['name']}")
