# LLM Lead Classifier: Evaluation Log

**Task:** turn a free-text car enquiry into fixed fields: customer type, quantity, budget (AED), destination country, urgency, genuine.
**Runs locally:** Ollama in Docker, CPU only (no graphics card), temperature 0, JSON-schema output.
**Test sets** (all data is synthetic):
- `llm/test_cases.json`: 20 enquiries used while developing the prompt.
- `llm/holdout_cases.json`: 10 new enquiries the prompt was never tuned on.

---

## Design

**Version 1:** the LLM chose every field, including the customer type and the total budget.

**Version 2 (current, on `main`):** the LLM only **extracts facts**. Code in `apply_rules()` **decides**:

| Facts from the LLM | Rule in code | Result |
|---|---|---|
| not genuine | everything blank | customer type `Unknown` |
| no country, or a UAE city | treat as local | destination `UAE` |
| not for resale | own use | `Buyer` |
| for resale, destination UAE | sells on locally | `Distributor` |
| for resale, destination abroad | sells on in another country | `Importer` |
| amount is per vehicle | multiply by quantity | total budget |

Why: the model was reading the facts correctly but still applying the label or the arithmetic wrongly. Code never gets a fixed rule or a sum wrong, and the rules can be read and audited.

---

## Results

| Date | Version | Model | Test set | All fields correct | Customer type | Median time |
|---|---|---|---|---|---|---|
| 15 Nov 2026 | 1 | gemma3:4b | main (20) | 15/20 (75%) | 17/20 | 16 s |
| 15 Nov 2026 | 2 | gemma3:4b | main (20) | 17/20 (85%) | 19/20 | 14 s |
| 15 Nov 2026 | 2 | gemma3:4b (rerun) | main (20) | 17/20 (85%) | 19/20 | 14 s |
| 15 Nov 2026 | 2 | llama3.2:3b | main (20) | 13/20 (65%) | 15/20 | 8 s |
| 16 Nov 2026 | 2 | gemma3:4b | hold-out (10) | 8/10 (80%) | 10/10 | 15 s |

`genuine` was correct on every case in every run, so no real customer was marked as spam.

**Change to the test between versions 1 and 2:** four expected destinations (#1, #7, #14, #17) were changed from `Unknown` to `UAE`, to match the business decision that an enquiry with no country is local. Part of the 75% → 85% gain comes from this test change, not from the model.

---

## What the failures show

**Fail on both models**, so they are hard for small models in general:
- **#8** "90,000 AED each" for 3 vehicles: the amount was not flagged as per vehicle.
- **#11** taxi fleet: marked as resale, even though the prompt says a fleet for own use is not resale.
- **#19** "2 Harrier and 3 Prado": counted only the first vehicle.

**Fail on llama3.2:3b only:** #2, #4, #6 and #12, all marked as not for resale. The model misses resale when it is implied by the business ("imports vehicles", "supply vehicles to dealers", "showroom") rather than stated outright.

**The code layer helped the weaker model:** llama returned "Dubai", "Ajman" and "Unknown" as destinations. The UAE rule in code turned all of them into `UAE`, so destination scored 20/20 on both models.

**The hold-out confirmed the design generalises:** customer type was 10/10 on new messages, including implied resale (#107), a company buying for its own use (#104), an agent sourcing for a client (#110), and Dubai areas instead of city names (#104, #105). Both hold-out failures repeat the weaknesses above:
- **#104** "85k per vehicle": per-vehicle budget missed again, even with the words "per vehicle".
- **#108** "3 Prado TXL and 2 Land Cruiser GX": only the first model counted again.

---

## Known limitations (version 2, gemma3:4b)

1. **Per-vehicle budgets:** the model often misses "each" or "per vehicle", so the total budget is understated.
2. **Several models in one message:** only the first model's quantity is counted.
3. **Fleets for own use:** a company buying vehicles for its own fleet can be marked as resale (Distributor instead of Buyer).
4. **Currencies:** only AED amounts are handled. Other currencies are not converted.
5. **UAE place names:** only the seven emirates and main city names are recognised in code. The model usually maps areas such as Al Quoz to UAE itself, but this is not guaranteed.

---

## Recommended fixes (not yet tested)

Kept on the branch **`classifier-v3`**, not on `main`, so the code that runs always matches the scores above.

| Limitation | Fix in v3 | Principle |
|---|---|---|
| 1. Per-vehicle budgets | Code also checks the message for "each", "per vehicle", "per unit", "per car" and multiplies | Code does what code is reliable at |
| 2. Several models | The LLM lists each model with its own quantity; code adds them up | Listing is easier for a small model than adding |

Known risk of v3: the keyword check could misfire on a message such as "each car must be white" when a budget is also given.

Not yet addressed: limitation 3 (fleets) needs a clearer field design, for example asking who will use the vehicles. Limitations 4 and 5 need a currency rule and a fuller UAE place list.

**How v3 will be accepted:** run both test sets. Merge into `main` only if it improves the main and hold-out scores without breaking any case that passed before.

---

## Decision

**Default model: `gemma3:4b`.** It is about 40% slower than llama3.2:3b, but classification runs in the background, so no customer waits for it. Getting the customer type wrong costs more than a few seconds of waiting.

**Classifier work is paused at version 2** so the rest of the pipeline can be built. The classifier is isolated in `llm/classifier.py` with its own tests, so it can be improved or swapped later without changing the workflow.

**When to revisit:**
- In the OpenAI demo: run the same 30 cases on an OpenAI model and compare against this log.
- Before any real use: write a fresh hold-out from real enquiries, then test v3.

---

## Limits of this evaluation

- 30 cases is a small sample: in the main set each case is 5 points, in the hold-out 10 points. Read these figures as rough.
- All test cases and the prompt were written by the same author. The prompt was reworded while looking at gemma's mistakes, which may favour gemma over other models.
- The hold-out has now been used to confirm which weaknesses to fix, so it is no longer fully unseen. A future hold-out should be written from real customer enquiries.
