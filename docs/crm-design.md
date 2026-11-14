# CRM Pipeline Design

**Project:** Car enquiry lead pipeline (demo, synthetic data only)
**Company in demo:** Desert Motors Trading (Demo), a fictional automotive trading company
**System:** Odoo 19 Community, CRM app (self-hosted in Docker)
**Owner:** Abdu Shakur Lugedha
**Version:** 1.0, 13 Nov 2026

---

## 1. Goal and scope

**Goal:** capture every enquiry from web, WhatsApp and email, qualify it quickly, and move genuine buyers to a committed deal.

**In scope:** enquiry capture, qualification, the sales pipeline up to the customer's commitment (deposit paid), lost-deal reasons and pipeline reporting.

**Out of scope:** shipping, logistics, the balance payment and invoicing. Once a deal is won, these are handled in Odoo **Sales**, **Inventory** and **Invoicing**, not on the CRM board. The CRM's job is to bring in and convert leads, not to track operations work.

---

## 2. Record types: lead vs opportunity

Odoo stores both as the same record (`crm.lead`). The `type` field tells them apart.

| Type | Meaning | Example |
|---|---|---|
| **Lead** | Raw, unchecked enquiry. Not yet on the pipeline board. | "Asked about a Land Cruiser on WhatsApp." |
| **Opportunity** | Qualified deal with an owner and an expected value, on the pipeline board. | "Distributor, 5 × Hilux, AED 400k, delivery January." |

Setting: CRM → Configuration → Settings → **Leads** is switched on.

---

## 3. Lead qualification (before the pipeline)

**Entry:** every enquiry is created as a **lead**, by the n8n automation or by hand.

**Checks before converting a lead to an opportunity:**
1. **Genuine:** a real enquiry, not spam or a test.
2. **Not a duplicate:** no open lead or opportunity with the same phone or email (see section 8).
3. **Reachable:** at least one valid contact method (phone in international format, or email).
4. **Source recorded:** Web form, WhatsApp, Email or Referral.

**Outcomes:**
- Passes all checks → **Convert to opportunity**, which lands in the **New** stage.
- Duplicate → **merge** into the existing record.
- Not genuine → **mark as lost** with the reason *Not genuine / spam*.

---

## 4. Pipeline stages

**New → Qualified → Vehicle Sourced / Inspection → Quotation Sent → Negotiation → Won - Deposit Paid**

| # | Stage | Meaning | Exit rule (what must be true to move on) | Stale after* |
|---|---|---|---|---|
| 1 | **New** | Converted opportunity with an owner assigned | Customer has been contacted. The first response time is measured up to this point. | 1 day |
| 2 | **Qualified** | The need is confirmed | Customer type, vehicle (make, model, year), quantity, budget (AED), destination country and timeline are all filled in | 3 days |
| 3 | **Vehicle Sourced / Inspection** | Matching vehicle(s) found and checked | Vehicle availability and condition confirmed (stock, supplier or inspection report) | 7 days |
| 4 | **Quotation Sent** | Price sent, including shipping terms (e.g. FOB or CIF) | Customer has replied to the quotation | 5 days |
| 5 | **Negotiation** | Price, payment terms or deposit under discussion | Deposit received, or the deal is marked lost | 10 days |
| 6 | **Won - Deposit Paid** | Customer committed and the deposit is received | Final stage. The balance and fulfilment move to Sales and Invoicing. | n/a |

\* The stale thresholds are starting assumptions, to be adjusted with the sales team.

**Note on "Won":** this means the customer has **committed and paid a deposit**. It does not mean all revenue is collected. Expected revenue on won deals is the deal value; cash collection is tracked in Invoicing.

---

## 5. Lost deals

- **Lost is an outcome, not a stage.** There is no "Lost" column. A deal can be marked lost from any stage, and Odoo archives it with a reason.
- **Lost reasons:**
  - Price too high
  - Bought elsewhere
  - Vehicle unavailable
  - No response
  - Import / export restriction
  - Not genuine / spam

---

## 6. Data captured on each lead or opportunity

| Field | Required from | Notes |
|---|---|---|
| Contact name | Lead | |
| Phone | Lead (phone or email) | International format, e.g. +9715… |
| Email | Lead (phone or email) | |
| Source | Lead | Web form · WhatsApp · Email · Referral (Odoo UTM source) |
| Original message | Lead | The enquiry text as received |
| Customer type | Qualified | Buyer · Distributor · Importer. A **tag** in this demo; a proper **field** in production (see section 10). |
| Vehicle (make, model, year) | Qualified | |
| Quantity | Qualified | |
| Budget (AED) | Qualified | |
| Destination country | Qualified | Matters for import rules and shipping terms |
| Timeline | Qualified | |
| Urgency | Optional | **Urgent** tag |
| Owner (salesperson) | New | Exactly one owner per deal |
| Expected revenue (AED) | Quotation Sent | |
| Next activity with a due date | Every open deal | A deal with no next step counts as at risk |

---

## 7. Ownership and response targets

- **One owner per deal**, set when the lead is converted, either by assignment rules or manually.
- **First response targets** (assumptions to confirm with the sales team):
  - WhatsApp: 15 minutes during business hours
  - Web form and email: 1 hour during business hours
- **First response time** is the time from lead creation to the first reply sent to the customer and logged on the record.
- **Timezone:** Asia/Dubai, set on the company and on each user. Odoo stores times in UTC and converts them for display, so response times are only correct if the timezone is set.

---

## 8. Duplicate handling

Two layers:

1. **Same event delivered twice** (a sender retrying a webhook): n8n keeps a list of processed `event_id`s. A repeated ID is skipped, and n8n still replies `200` so the sender stops retrying.
2. **Same customer, new enquiry** (a different `event_id`): before creating a lead, n8n searches Odoo for an **open** lead or opportunity with the same phone or email. If one exists, the new message is added as a note to it instead of creating a new record (an **upsert**).

---

## 9. How the rules are enforced

**Limitation:** Odoo **Community** cannot make a field required only at a certain stage. That needs Odoo Studio (Enterprise, paid) or a custom module.

In this design, the exit rules are enforced by:
1. **Team discipline:** the stage definitions above are the shared rules, and managers check against them.
2. **n8n checks on automated entry:** leads created by automation are validated first (contact method, source, no duplicate). Incomplete records are flagged instead of created silently.
3. **A data-quality view in Power BI:** open deals missing required fields, deals past their stale threshold, and deals with no next activity.

**Production options**, if stricter enforcement is needed: Odoo Studio (Enterprise) or a small custom module that adds stage-based validation.

---

## 10. Design decisions

| Decision | Reason |
|---|---|
| Leads switched on (two-step lead → opportunity) | Keeps spam and duplicates off the sales board and makes the funnel honest |
| Six stages | Covers sourcing and inspection, which car trading needs, while staying within the usual 5–7 |
| Won merged with Deposit Paid | The CRM ends at the customer's commitment; fulfilment belongs to Sales and Invoicing |
| Lost as an outcome with reasons | Gives a "why we lose" report instead of a cluttered column |
| Customer type as a tag in the demo | A proper field needs Studio or custom code in Community. Tags are acceptable for a demo but weaker for reporting. |
| One pipeline for all customer types | Buyers, distributors and importers follow the same steps here. Use separate Sales Teams only if the processes differ. |

---

## 11. Metrics

| Metric | Definition |
|---|---|
| Lead-to-opportunity rate | Leads converted ÷ all leads created |
| Stage conversion | % of deals that move from one stage to the next |
| Win rate | Won ÷ (Won + Lost), closed deals only |
| Time in stage | **Median** days a deal spends in each stage |
| Sales cycle length | **Median** days from opportunity creation to Won |
| First response time | **Median** minutes from lead creation to first reply |
| Average deal size | Mean expected revenue of won deals (AED) |
| Pipeline value | Sum of expected revenue of open deals (AED) |
| Pipeline velocity | (Open deals × win rate × average deal size) ÷ sales cycle length |
| Lost reasons | Count and share of lost deals per reason |

**Data source for time in stage:** Odoo logs every stage change in the record's history (`mail.tracking.value`). Stages must only be changed in Odoo, never by editing the database, or this history breaks.

Medians are used for time-based metrics because a few stuck deals would distort an average.

---

## 12. Assumptions and open questions

- Response targets and stale thresholds are starting assumptions, to be agreed with the sales team.
- Does the business source vehicles after the enquiry, or sell from its own stock? This decides whether **Vehicle Sourced / Inspection** stays a separate stage.
- Do distributors and retail buyers follow the same process? If not, use separate Sales Teams with their own pipelines.
- Which shipping terms (FOB, CIF, etc.) are standard? They should appear on quotations.

---

## 13. Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 13 Nov 2026 | First design: six stages, Won merged with Deposit Paid, enforcement approach documented |
