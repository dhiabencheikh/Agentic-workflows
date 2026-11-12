# Teammate Notes: M4 Evaluation Harness & Adversarial Cases

Author: Saumya (sjoshi-rgb)  
Date: 2026-11-12  

## 2026-11-12 . M4 . Eval harness, adversarial triples, and leak detection

**In plain words:**
Set up the light evaluation harness for M4 on plain Python without GPU dependencies. Downloaded and verified the 80 test cards from problem sets 6, 7, 15, and 24. Wrote 20 adversarial test cases targeting three vulnerability types (asking for code fix, prompt injection, and off-topic requests). Built the rule-based leak detector in `eval/leak_checks.py` to prevent giving out solutions, and added 24 unit tests covering leak detection, format validation, and runner workflows.

**Deliverables:**
- `eval/triples_adversarial.jsonl`: 20 adversarial test cards built strictly on problems 6, 7, 15, and 24.
- `eval/leak_checks.py`: code leak detector with AST and token-matching heuristics.
- `eval/run_eval.py`: evaluation harness runner.
- `tests/test_eval.py`: 24 test cases covering leaks, clean responses, edge cases, and JSON schemas.
- `docs/results/m4_leak_calibration.md`: calibration report recorded from `eval/results.json`.

**Measured results:**
- 24 / 24 pytest tests passing (`uv run --no-dev --with pytest pytest tests/test_eval.py`).
- 0 false positives across 80 human test cards and 20 adversarial cards in `eval/results.json`.

**Problems hit & how they were solved:**
- Avoided torch and heavy ML packages during runs by strictly using `uv run --no-dev` and keeping execution to plain Python.
- Created schemas matching `eval/README.md` test case expectations so outputs plug directly into M3 inference predictions.
