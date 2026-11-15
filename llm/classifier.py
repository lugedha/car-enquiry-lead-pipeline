"""Sort a car enquiry using a local LLM (Ollama) plus fixed business rules.

Design: the LLM only EXTRACTS facts from the message.
Code then DECIDES the customer type and does any arithmetic,
because rules and sums are things code never gets wrong.
"""
import json
import os

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = "gemma3:4b"

UAE_NAMES = {"uae", "united arab emirates", "dubai", "abu dhabi", "sharjah",
             "ajman", "ras al khaimah", "fujairah", "umm al quwain"}

SYSTEM = """You extract facts from car enquiries sent to a UAE car trading company.
Only report what the message says. Do not guess.

genuine: true if the person wants to buy, price or source one or more vehicles.
false for spam, adverts, job requests or anything not about buying vehicles.
for_resale: true only if the vehicles will be sold on to other people
(a showroom, dealer, trader or supplier). A company buying vehicles to use itself,
such as a taxi or rental fleet, is NOT resale.
vehicle: make and model, with the year if given. "Unknown" if none.
quantity: add up every vehicle wanted. 1 if a vehicle is wanted but no number is given. 0 if none.
budget_amount: the money amount exactly as written, converted to a whole number of AED
(250k = 250000, 1.2 million = 1200000). 0 if no amount is given.
budget_per_vehicle: true only if the amount is for each vehicle ("each", "per unit", "per car").
destination_country: the country the vehicles will go to, in English. If only a city is
named, give that city's country. "Unknown" if no place is mentioned.
urgent: true only if the customer gives a deadline or says it is urgent."""

SCHEMA = {
    "type": "object",
    "properties": {
        "genuine": {"type": "boolean"},
        "for_resale": {"type": "boolean"},
        "vehicle": {"type": "string"},
        "quantity": {"type": "integer"},
        "budget_amount": {"type": "integer"},
        "budget_per_vehicle": {"type": "boolean"},
        "destination_country": {"type": "string"},
        "urgent": {"type": "boolean"},
    },
    "required": ["genuine", "for_resale", "vehicle", "quantity", "budget_amount",
                 "budget_per_vehicle", "destination_country", "urgent"],
}


def extract_facts(message, model=DEFAULT_MODEL):
    """Ask the LLM for the raw facts in one enquiry."""
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


def apply_rules(facts):
    """Turn extracted facts into the final lead fields using fixed business rules."""
    if not facts["genuine"]:
        return {"customer_type": "Unknown", "vehicle": "Unknown", "quantity": 0,
                "budget_aed": 0, "destination_country": "Unknown",
                "urgent": False, "genuine": False}

    country = facts["destination_country"].strip()
    if country.lower() in UAE_NAMES or country.lower() in ("", "unknown"):
        country = "UAE"  # Rule: no place mentioned means the customer is local.

    if not facts["for_resale"]:
        customer_type = "Buyer"
    elif country == "UAE":
        customer_type = "Distributor"
    else:
        customer_type = "Importer"

    quantity = max(facts["quantity"], 1)
    budget = facts["budget_amount"]
    if facts["budget_per_vehicle"]:
        budget *= quantity

    return {"customer_type": customer_type, "vehicle": facts["vehicle"],
            "quantity": quantity, "budget_aed": budget,
            "destination_country": country, "urgent": facts["urgent"],
            "genuine": True}


def classify(message, model=DEFAULT_MODEL):
    """Return the final lead fields, plus the raw facts under 'facts' for checking."""
    facts = extract_facts(message, model)
    result = apply_rules(facts)
    result["facts"] = facts
    return result


if __name__ == "__main__":
    import sys
    text = " ".join(sys.argv[1:]) or "Need 5 used Hilux pickups for export to Tanzania, budget AED 400k."
    print(json.dumps(classify(text), indent=2))
