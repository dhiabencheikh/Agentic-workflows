# Teammate Notes: M4 Evaluation Harness & Adversarial Cases

Author: Saumya (sjoshi-rgb)  
Date: 2026-11-12  

## 2026-11-12 . M4 . Eval harness, adversarial triples, and leak detection

**In plain words:**
Set up the light evaluation harness for M4 on plain Python without GPU dependencies. Downloaded and verified the 80 test cards from problem sets 6, 7, 15, and 24. Wrote 20 adversarial test cases targeting three vulnerability types (asking for code fix, prompt injection, and off-topic requests). Built the rule-based leak detector in `eval/leak_checks.py` to prevent giving out solutions, and added 4 unit tests in `tests/test_eval.py` (leak detection and suite validation).

**Deliverables:**
- `eval/triples_adversarial.jsonl`: 20 adversarial test cards built strictly on problems 6, 7, 15, and 24.
- `eval/leak_checks.py`: code leak detector based on regular expressions over the reply and the answer key (no AST).
- `eval/run_eval.py`: evaluation harness runner.
- `tests/test_eval.py`: 4 test cases (3 leak checks, 1 suite validation).
- `docs/results/m4_leak_calibration.md`: calibration report (first version recorded from `eval/results.json`; replaced by measured figures, see the correction below).

**Measured results:**
- 4 / 4 tests in `tests/test_eval.py` passing (`uv run --no-dev --with pytest pytest tests/test_eval.py`); the whole suite on the branch had 24 tests.
- The "0 false positives" in `eval/results.json` was not a measurement: the runner read fields that do not exist (`assistant_reply`, `target_reply`), so every reply checked was an empty string. Measured later on the real human replies, the first version of the check flagged 7 of 207 test replies (3.4%) and caught 19 of 36 known leaks.

**Problems hit & how they were solved:**
- Avoided torch and heavy ML packages during runs by strictly using `uv run --no-dev` and keeping execution to plain Python.
- Created schemas matching `eval/README.md` test case expectations so outputs plug directly into M3 inference predictions.

## Correction (2026-11-12, by Dhia, after PR #6 and PR #8)

**What changed:** four figures above were wrong and are corrected: the number of tests (4 in `tests/test_eval.py`,
not 24: 24 was the whole suite on the branch), the "0 false positives" (computed on empty replies), the "AST"
description (the check uses regular expressions, no AST), and the calibration source.

**Why:** our rule is that every figure comes from a run or a committed results file, and these notes feed the
presentation's "problems encountered" section and the oral.

**Measured figures now** (leak check after PR #8, frozen at commit `b1828bd`, `docs/results/m4_leak_calibration.md`):
false alarms on human tutor replies 0/1299 train, 0/288 validation, 3/207 test; known leaks caught 142/187 train,
27/38 validation, 29/36 test. Adversarial cases: 26 (20 original, 4 tutor turns rewritten, 6 added for bugs 6_34 and 15_45).
Tests on `main`: 67 passed, 1 skipped (`uv run --no-dev --with pytest pytest`).

Saumya: please check these corrections and add what you learned from the review in your own words.
