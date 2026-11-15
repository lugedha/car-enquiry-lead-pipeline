import json
import time
import requests

SYSTEM = """You sort car enquiries for a UAE car trading company.
customer_type: decide in this order.
Buyer = buying for own use, not to resell.
Importer = buying to resell, and the vehicles go to a country outside the UAE.
Distributor = buying to resell inside the UAE.
Unknown = not clear.
destination_country: "Unknown" if not stated.
urgent: true only if the customer gives a deadline or says it is urgent.
true if the person wants to buy, price or source one or more vehicles.
false only for spam, adverts or messages that are not about vehicles."""

SCHEMA = {
    "type": "object",
    "properties": {
        "customer_type": {"type": "string",
                          "enum": ["Buyer", "Distributor", "Importer", "Unknown"]},
        "vehicle": {"type": "string"},
        "quantity": {"type": "integer"},
        "budget_aed": {"type": "integer"},
        "destination_country": {"type": "string"},
        "urgent": {"type": "boolean"},
        "genuine": {"type": "boolean"},
    },
    "required": ["customer_type", "vehicle", "quantity", "budget_aed",
                 "destination_country", "urgent", "genuine"],
}

def classify(message):
    r = requests.post("http://localhost:11434/api/chat", timeout=300, json={
        "model": "gemma3:4b",
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": message}],
        "format": SCHEMA,
        "stream": False,
        "options": {"temperature": 0},
    })
    r.raise_for_status()
    return json.loads(r.json()["message"]["content"])

tests = [
    "Hi, I want a 2022 Land Cruiser GXR for my family. Budget 250k AED. Need it before Eid.",
    "Need 5 used Hilux pickups for export to Tanzania, budget AED 400k.",
    "Congratulations! You won a free iPhone. Click here to claim your prize.",
]
for msg in tests:
    start = time.time()
    result = classify(msg)
    print(f"\n{msg}\n  -> {result}\n  ({time.time() - start:.0f} seconds)")