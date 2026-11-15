"""Score the lead classifier against test cases with known answers.

Usage:  python llm/evaluate.py [model]
Example: python llm/evaluate.py gemma3:4b

The vehicle field is free text, so it is not scored.
On a failure, the raw facts from the LLM are printed, so you can see whether
the LLM misread the message or a business rule gave the wrong result.
"""
import json
import statistics
import sys
import time
from pathlib import Path

from classifier import DEFAULT_MODEL, classify

FIELDS = ["customer_type", "quantity", "budget_aed",
          "destination_country", "urgent", "genuine"]


def same(got, expected):
    """Compare one field. Text is compared without case or outer spaces."""
    if isinstance(expected, str):
        return str(got).strip().lower() == expected.strip().lower()
    return got == expected


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    cases = json.loads(
        (Path(__file__).parent / "test_cases.json").read_text(encoding="utf-8"))

    correct = {f: 0 for f in FIELDS}
    all_correct = 0
    seconds = []

    print(f"Model: {model} | {len(cases)} test cases\n")
    for case in cases:
        start = time.time()
        got = classify(case["message"], model)
        seconds.append(time.time() - start)

        wrong = []
        for f in FIELDS:
            if same(got.get(f), case["expected"][f]):
                correct[f] += 1
            else:
                wrong.append(f"{f}: got {got.get(f)!r}, expected {case['expected'][f]!r}")

        if wrong:
            print(f"#{case['id']:>2} FAIL  {case['message'][:60]}")
            for w in wrong:
                print(f"         {w}")
            print(f"         facts from LLM: {got.get('facts')}")
        else:
            all_correct += 1
            print(f"#{case['id']:>2} ok")

    n = len(cases)
    print("\nAccuracy per field")
    for f in FIELDS:
        print(f"  {f:<20} {correct[f]:>2}/{n}  {correct[f] / n:.0%}")
    print(f"\nAll fields correct:  {all_correct}/{n}  {all_correct / n:.0%}")
    print(f"Median time per enquiry: {statistics.median(seconds):.0f} seconds")


if __name__ == "__main__":
    main()
