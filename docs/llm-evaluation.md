# LLM Lead Classifier: Evaluation Log

**Task:** turn a free-text car enquiry into fixed fields: customer type, quantity, budget (AED), destination country, urgency, genuine.
**Runs locally:** Ollama in Docker, CPU only (no graphics card), temperature 0, JSON-schema output.
**Test set:** `llm/test_cases.json`, 20 made-up enquiries with correct answers. All data is synthetic.

---

## Design

**Version 1:** the LLM chose every field, including the customer type and the total budget.

**Version 2 (current):** the LLM only **extracts facts**. Code in `apply_rules()` **decides**:

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

| Date | Version | Model | All fields correct | Customer type | Median time |
|---|---|---|---|---|---|
| 15 Nov 2026 | 1 | gemma3:4b | 15/20 (75%) | 17/20 | 16 s |
| 15 Nov 2026 | 2 | gemma3:4b | 17/20 (85%) | 19/20 | 14 s |
| 15 Nov 2026 | 2 | gemma3:4b (rerun) | 17/20 (85%) | 19/20 | 14 s |
| 15 Nov 2026 | 2 | llama3.2:3b | 13/20 (65%) | 15/20 | 8 s |

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

---

## Decision

**Default model: `gemma3:4b`.** It is about 40% slower than llama3.2:3b, but classification runs in the background, so no customer waits for it. Getting the customer type wrong costs more than a few seconds of waiting.

---

## Limits

- 20 cases is a small sample: each case is 5 points. Read these figures as rough.
- The test cases and the prompt were written by the same person in the same session. The prompt was reworded while looking at gemma's mistakes, which may favour gemma over other models.
- The next check is a **hold-out set** (`llm/holdout_cases.json`): new cases the prompt is never tuned on.
