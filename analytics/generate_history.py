"""Generate six months of made-up pipeline history into the analytics database.

Run:  python analytics/generate_history.py
      python analytics/generate_history.py --leads 800 --days 240 --seed 7

Why this exists: Odoo stamps creation and stage-change times itself, so history
can't be backdated through its API. For a dashboard with real-looking response
times and time in stage, the history is generated here instead.

Every row written by this script has is_synthetic = true. Rerunning the script
first deletes its own earlier rows, so it always gives a clean, repeatable result.
Rows copied from Odoo (is_synthetic = false) are never touched.
"""
import argparse
import os
import random
from datetime import datetime, timedelta, timezone

import psycopg
from dotenv import load_dotenv

DUBAI = timezone(timedelta(hours=4))  # The UAE has no daylight saving, so a fixed offset is exact.
FIRST_ID = 1_000_000                  # Generated ids start here, far above any real Odoo id.

# ---------------------------------------------------------------------------
# Business assumptions. Change these to tell a different story in the dashboard.
# ---------------------------------------------------------------------------

SOURCES = {"Web form": 0.40, "WhatsApp": 0.35, "Email": 0.15, "Referral": 0.10}
SPAM_RATE = {"Web form": 0.20, "WhatsApp": 0.06, "Email": 0.12, "Referral": 0.0}
CUSTOMER_TYPES = {"Buyer": 0.55, "Distributor": 0.20, "Importer": 0.25}
EXPORT_COUNTRIES = {"Kenya": 0.22, "Tanzania": 0.16, "Uganda": 0.14, "Nigeria": 0.12,
                    "Iraq": 0.12, "Ethiopia": 0.10, "Ghana": 0.08, "Oman": 0.06}

# (vehicle, typical price per unit in AED)
VEHICLES = [("Toyota Land Cruiser 300", 320_000), ("Toyota Land Cruiser 79", 140_000),
            ("Toyota Hilux", 95_000), ("Toyota Prado", 180_000), ("Toyota Hiace", 110_000),
            ("Nissan Patrol", 260_000), ("Nissan Sunny", 55_000), ("Mitsubishi Pajero", 120_000),
            ("Kia Sportage", 85_000), ("Hyundai Tucson", 90_000), ("Lexus LX 600", 520_000),
            ("Toyota Corolla", 70_000)]

# Median minutes to first reply, by channel. WhatsApp is answered fastest.
RESPONSE_MEDIAN_MIN = {"WhatsApp": 12, "Web form": 45, "Email": 180, "Referral": 30}
NEVER_ANSWERED = 0.03

# Chance of moving on from each stage to the next, before adjustments.
NEXT_STAGE_CHANCE = {"Lead": 0.72, "New": 0.78, "Qualified": 0.72,
                     "Vehicle Sourced / Inspection": 0.82, "Quotation Sent": 0.62,
                     "Negotiation": 0.55}
# Median days spent in each stage before moving on.
STAGE_MEDIAN_DAYS = {"Lead": 0.2, "New": 1.0, "Qualified": 2.5,
                     "Vehicle Sourced / Inspection": 5.0, "Quotation Sent": 3.0,
                     "Negotiation": 6.0}
STAGES = ["Lead", "New", "Qualified", "Vehicle Sourced / Inspection",
          "Quotation Sent", "Negotiation", "Won - Deposit Paid"]

# Why deals are lost, depending on how far they got.
LOST_REASONS = {
    "early": {"No response": 0.55, "Price too high": 0.15, "Bought elsewhere": 0.30},
    "middle": {"Vehicle unavailable": 0.45, "No response": 0.25, "Bought elsewhere": 0.30},
    "late": {"Price too high": 0.45, "Bought elsewhere": 0.35, "No response": 0.20},
}
IMPORT_RESTRICTION_CHANCE = 0.15  # extra lost reason for importers, at any stage


def pick(rng, weights):
    """Pick one key from a {value: weight} dictionary."""
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def lognormal(rng, median, spread=0.8):
    """A positive random number around `median`, with a long tail of slow cases."""
    return median * rng.lognormvariate(0, spread)


def business_time(rng, day):
    """A random arrival time on `day`, mostly in working hours, Dubai time."""
    hour = rng.choices(range(24), weights=[1, 1, 1, 1, 1, 1, 2, 4, 8, 10, 11, 11,
                                           9, 9, 10, 10, 9, 8, 7, 6, 5, 3, 2, 1])[0]
    return datetime(day.year, day.month, day.day, hour, rng.randrange(60),
                    rng.randrange(60), tzinfo=DUBAI)


def reply_time(rng, created, source):
    """When the first reply was sent. Replies wait for working hours (08:00-20:00)."""
    reply = created + timedelta(minutes=lognormal(rng, RESPONSE_MEDIAN_MIN[source], 1.0))
    local = reply.astimezone(DUBAI)
    if local.hour >= 20:
        local = (local + timedelta(days=1)).replace(hour=8, minute=rng.randrange(45))
    elif local.hour < 8:
        local = local.replace(hour=8, minute=rng.randrange(45))
    return local


def make_lead(rng, lead_id, day, now):
    created = business_time(rng, day)
    if created > now:
        created = now - timedelta(minutes=rng.randrange(5, 120))
    source = pick(rng, SOURCES)
    lead = {"lead_id": lead_id, "created_at": created, "source": source,
            "is_synthetic": True, "first_response_at": None, "closed_at": None,
            "lost_reason": None, "outcome": "open"}
    events = [("Lead", created)]

    # Spam: archived as lost within minutes, as the live pipeline does.
    if rng.random() < SPAM_RATE[source]:
        lead.update(customer_type="Unknown", vehicle=None, quantity=0, budget_aed=None,
                    destination_country=None, urgent=False, genuine=False,
                    outcome="lost", lost_reason="Not genuine / spam",
                    closed_at=created + timedelta(minutes=rng.randrange(1, 5)),
                    expected_revenue=None)
        return lead, events

    customer_type = pick(rng, CUSTOMER_TYPES)
    vehicle, unit_price = rng.choice(VEHICLES)
    if customer_type == "Buyer":
        quantity = 1 if rng.random() < 0.85 else rng.randint(2, 15)  # some company fleets
        country = "UAE" if rng.random() < 0.8 else pick(rng, EXPORT_COUNTRIES)
    elif customer_type == "Distributor":
        quantity, country = rng.randint(3, 12), "UAE"
    else:
        quantity, country = rng.randint(2, 15), pick(rng, EXPORT_COUNTRIES)
    deal_value = round(unit_price * quantity * rng.uniform(0.85, 1.15), -3)
    budget = deal_value if rng.random() < 0.7 else None  # 30% don't state a budget
    urgent = rng.random() < 0.15
    lead.update(customer_type=customer_type, vehicle=vehicle, quantity=quantity,
                budget_aed=budget, destination_country=country, urgent=urgent,
                genuine=True, expected_revenue=deal_value)

    if rng.random() >= NEVER_ANSWERED:
        lead["first_response_at"] = reply_time(rng, created, source)

    # Walk the lead through the stages until it is lost, won, or reaches today.
    t = created
    for i, stage in enumerate(STAGES[:-1]):
        chance = NEXT_STAGE_CHANCE[stage]
        if stage == "Lead":
            reply = lead["first_response_at"]
            if reply is None:
                chance = 0.0
            else:
                minutes = (reply - created).total_seconds() / 60
                # Fast replies win more deals; slow ones lose them.
                chance *= 1.15 if minutes <= 15 else 1.0 if minutes <= 60 else 0.75 if minutes <= 240 else 0.5
        if source == "Referral":
            chance *= 1.12
        if urgent:
            chance *= 1.08
        chance = min(chance, 0.97)

        t_next = t + timedelta(days=lognormal(rng, STAGE_MEDIAN_DAYS[stage]))
        if stage == "Lead" and lead["first_response_at"]:
            t_next = max(t_next, lead["first_response_at"])
        if t_next > now:
            return lead, events  # still open: not enough time has passed

        if rng.random() < chance:
            next_stage = STAGES[i + 1]
            events.append((next_stage, t_next))
            t = t_next
            # Occasionally a negotiation goes back to a revised quotation.
            if next_stage == "Negotiation" and rng.random() < 0.08:
                t_back = t + timedelta(days=lognormal(rng, 2))
                t_again = t_back + timedelta(days=lognormal(rng, 2))
                if t_again < now:
                    events += [("Quotation Sent", t_back), ("Negotiation", t_again)]
                    t = t_again
            if next_stage == STAGES[-1]:
                lead.update(outcome="won", closed_at=t)
                return lead, events
        else:
            phase = "early" if i <= 1 else "middle" if i <= 3 else "late"
            reason = pick(rng, LOST_REASONS[phase])
            if customer_type == "Importer" and rng.random() < IMPORT_RESTRICTION_CHANCE:
                reason = "Import / export restriction"
            lead.update(outcome="lost", lost_reason=reason, closed_at=t_next)
            return lead, events
    return lead, events


def generate(n_leads, days, seed):
    rng = random.Random(seed)  # fixed seed: the same command always gives the same data
    now = datetime.now(DUBAI)
    start = (now - timedelta(days=days)).date()
    all_days = [start + timedelta(days=d) for d in range(days + 1)]
    # Volume grows over time, with a marketing campaign in the middle month.
    day_weights = []
    for d, day in enumerate(all_days):
        w = 0.7 + 0.6 * d / days
        if days * 0.45 <= d <= days * 0.55:
            w *= 1.8
        if day.weekday() in (5, 6):  # Saturday, Sunday: the UAE weekend
            w *= 0.6
        day_weights.append(w)
    chosen = sorted(rng.choices(all_days, weights=day_weights, k=n_leads))
    return [make_lead(rng, FIRST_ID + i, day, now) for i, day in enumerate(chosen)]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--leads", type=int, default=600)
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    load_dotenv()
    conninfo = (f"host={os.environ.get('ANALYTICS_DB_HOST', 'localhost')} "
                f"port={os.environ.get('ANALYTICS_DB_PORT', '5433')} "
                f"dbname=analytics user=analytics "
                f"password={os.environ['ANALYTICS_DB_PASSWORD']}")

    rows = generate(args.leads, args.days, args.seed)
    lead_cols = ["lead_id", "created_at", "source", "customer_type", "vehicle", "quantity",
                 "budget_aed", "destination_country", "urgent", "genuine",
                 "first_response_at", "outcome", "lost_reason", "closed_at",
                 "expected_revenue", "is_synthetic"]

    # One transaction: either everything is replaced, or nothing changes.
    with psycopg.connect(conninfo) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM leads WHERE is_synthetic")  # stage_events go with them (CASCADE)
        with cur.copy(f"COPY leads ({', '.join(lead_cols)}) FROM STDIN") as copy:
            for lead, _ in rows:
                copy.write_row([lead[c] for c in lead_cols])
        with cur.copy("COPY stage_events (lead_id, stage, entered_at) FROM STDIN") as copy:
            for lead, events in rows:
                for stage, at in events:
                    copy.write_row([lead["lead_id"], stage, at])
        cur.execute("""
            SELECT outcome, count(*), round(100.0 * count(*) / sum(count(*)) OVER (), 1)
            FROM leads WHERE is_synthetic GROUP BY outcome ORDER BY outcome""")
        summary = cur.fetchall()
        cur.execute("SELECT count(*) FROM stage_events e JOIN leads l USING (lead_id) WHERE l.is_synthetic")
        n_events = cur.fetchone()[0]

    print(f"Generated {len(rows)} leads and {n_events} stage events over {args.days} days (seed {args.seed}).")
    for outcome, count, pct in summary:
        print(f"  {outcome:<5} {count:>4}  ({pct}%)")


if __name__ == "__main__":
    main()
