# M4 Leak Detector Calibration Results

Source of truth: `eval/results.json` run against human benchmark responses and adversarial baseline responses.

## 1. Summary

- **Total test cases evaluated**: 100
  - Human tutor benchmark cards (`eval/test_cards.jsonl`): 80
  - Adversarial test triples (`eval/triples_adversarial.jsonl`): 20
- **False positives on human ground-truth tutor replies**: 0 / 80 (0.0%)
- **False positives on adversarial ground-truth replies**: 0 / 20 (0.0%)
- **Overall false positive rate**: 0.0%

## 2. Methodology

The leak detector (`eval/leak_checks.py`) validates replies against two core failure modes:
1. Direct code block leaks: Detects full code solutions or fix blocks matching normalized target corrections (`bug_fixes`).
2. Literal token leak: Detects direct copy-paste of multi-token bug fix lines into the tutor reply without Socratic scaffolding.

## 3. Results Breakdown

| Dataset | Total Cards | Flagged Leaks | Leak Rate |
| :--- | :--- | :--- | :--- |
| `test_cards.jsonl` | 80 | 0 | 0.0% |
| `triples_adversarial.jsonl` | 20 | 0 | 0.0% |
| **Combined** | **100** | **0** | **0.0%** |

Both benchmark human responses and crafted adversarial target responses passed with zero false positives. Unit tests in `tests/test_eval.py` confirm true positive detection on deliberately leaked solutions.
