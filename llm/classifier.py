"""Sort a car enquiry into fixed fields using a local LLM (Ollama).

The prompt and the schema live here so every script uses the same ones.
"""
import json
import os

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = "gemma3:4b"

SYSTEM = """You sort car enquiries for a UAE car trading company.

customer_type: decide in this order.
Buyer = buying for own use, not to resell. A company buying for its own fleet is a Buyer.
Importer = buying to resell, and the vehicles go to a country outside the UAE.
Distributor = buying to resell inside the UAE.
If it is one vehicle and nothing suggests resale, choose Buyer.
Unknown = not a vehicle enquiry, or really not clear.

vehicle: make and model, with the year if given. "Unknown" if none.
quantity: total number of vehicles wanted. 1 if a vehicle is wanted but no number is given. 0 if none.
budget_aed: total budget in AED as a whole number. 0 if no budget is stated.
destination_country: the country the vehicles will go to, in English. "UAE" if they stay in the UAE. "Unknown" if not stated.
urgent: true only if the customer gives a deadline or says it is urgent.
genuine: true if the person wants to buy, price or source one or more vehicles. false only for spam, adverts or messages that are not about buying vehicles."""

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


def classify(message, model=DEFAULT_MODEL):
    """Return the sorted fields for one enquiry as a dictionary."""
    r = requests.post(f"{OLLAMA_URL}/api/chat", timeout=300, json={
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": message}],
        "format": SCHEMA,
        "stream": False,
        "options": {"temperature": 0},
    })
    r.raise_for_status()
    return json.loads(r.json()["message"]["content"])


if __name__ == "__main__":
    import sys
    text = " ".join(sys.argv[1:]) or "Need 5 used Hilux pickups for export to Tanzania, budget AED 400k."
    print(json.dumps(classify(text), indent=2))
