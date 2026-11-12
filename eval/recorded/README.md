# Recorded predictions for CI (option A)

Copied from M3 run `benjosh-socratic-eval-20261112215631` (2026-11-12), artifacts of the inference steps.

| File | Setup | Gated in CI | Measured with `eval/run_eval.py` |
|---|---|---|---|
| `predictions_c.jsonl` | c: fine-tuned + prompt v1.0.0 (the served model) | yes (`.github/workflows/eval.yml`, thresholds in `eval/thresholds.json`) | 1 leak, 0 errors in 106 cases |
| `baseline_predictions_b.jsonl` | b: base + prompt v1.0.0 | no: kept to prove the gate fails on a regression | 11 leaks, 0 errors in 106 cases |

Replace `predictions_c.jsonl` when a new model, prompt version or decoding is evaluated, and re-justify the thresholds.
