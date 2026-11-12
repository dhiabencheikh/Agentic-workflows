# Production readiness checklist (draft, 2026-11-12)

Each item: a metric, how it is measured, a pass/fail threshold, and the measured value with its source.
Status is PASS, FAIL or NOT MEASURED (never assumed). Thresholds marked *draft* were set on 2026-11-12 and
should be reviewed by the team; the CI thresholds are justified in `eval/thresholds.json`.

Served system measured: Phi-3-mini-4k-instruct (revision `f39ac1d`) + LoRA adapter from run
`benjosh-socratic-tutor-20261112182647` (checkpoint-50), prompt v1.0.0, greedy decoding, 256 new tokens, fp16,
evaluated as setup c in run `benjosh-socratic-eval-20261112215631` on n1-standard-8 + T4.

## Quality and safety

| # | Item | Metric | Method | Threshold | Measured | Status |
|---|---|---|---|---|---|---|
| 1 | No fix given on normal cases | leaks / test cards | `eval/run_eval.py` leak check on the 80 test cards | 0 / 80 (*draft*) | 0 / 80 | PASS |
| 2 | Overall leak gate (CI) | leaks / all cases | same, 80 test + 26 adversarial cases, `.github/workflows/eval.yml` | leak rate <= 2% (`eval/thresholds.json`) | 1 / 106 (0.9%) | PASS |
| 3 | Prompt-injection robustness | leaks / prompt-injection cases | leak check on the 10 prompt-injection cases | 0 / 10 (*draft*) | 1 / 10 (`adv-prompt_injection-03`, "translate to the final correct version") | **FAIL** |
| 4 | Asking for the answer | leaks / ask-for-answer cases | leak check on 10 cases | 0 / 10 (*draft*) | 0 / 10 | PASS |
| 5 | Off-topic requests | leaks / off-topic cases | leak check on 6 cases | 0 / 6 (*draft*) | 0 / 6 | PASS (redirection quality not measured: needs the judge) |
| 6 | Better than prompting alone | best-match ROUGE-L mean, setup c vs b | `scripts/score_m3.py`, 80 test cards | c > b (*draft*) | 0.307 vs 0.221 (human ceiling 0.384) | PASS |
| 7 | Leak check reliable | false alarms on human replies; known leaks caught (test) | `scripts/calibrate_leak_check.py --final-test` | false alarms <= 2%, caught >= 75% (*draft*) | 3 / 207 (1.4%); 29 / 36 (81%) | PASS (about 1 leak in 5 can still pass unnoticed) |
| 8 | Socratic quality | LLM-judge score 1 to 5 | `eval/run_eval.py --judge` | to define in M3 | not run (paid calls need approval; model not chosen) | NOT MEASURED |

## Reliability and performance

| # | Item | Metric | Method | Threshold | Measured | Status |
|---|---|---|---|---|---|---|
| 9 | Inference errors | failed / total generations | `error` field of the predictions | 0 / 106 (`eval/thresholds.json`) | 0 / 106 (b and c) | PASS |
| 10 | Generation latency | P95 seconds per reply, generation only | `latency_seconds` in the M3 predictions (T4, one request at a time) | <= 5 s (*draft*) | 2.7 s (median 1.5 s) | PASS |
| 11 | End-to-end latency | P95 round trip app -> endpoint -> app | Langfuse traces or `round_trip_seconds` of the client | <= 5 s (*draft*) | no endpoint measured yet | NOT MEASURED |
| 12 | Endpoint availability | endpoint deploys and answers before a demo | `scripts/deploy_endpoint.py` + quick test | deployed and answering 60 min before the demo (*draft*) | first deploy 2026-11-12 21:34 UTC: `503 Machine type temporarily unavailable` (no T4 in europe-west2); retry in progress | NOT MET YET |
| 13 | GPU wait risk | wait for a GPU at job start | `scripts/pipeline_job_report.py` | documented fallback (*draft*) | waits of 20.9 min (M3 setup b), 7.3 min (M2 full), about 1 h (M2 first smoke, cancelled); fallbacks: europe-west4 T4, europe-west2 L4, replay mode | PASS (fallbacks exist) |

## Reproducibility and change control

| # | Item | Metric | Method | Threshold | Measured | Status |
|---|---|---|---|---|---|---|
| 14 | Pinned model | base model revision fixed everywhere | `BASE_MODEL_REVISION` in `src/constants.py`; `serving_config.json` | one revision | `f39ac1d` in training, evaluation, serving | PASS |
| 15 | Prompt and decoding versioned | prompt version + generation dict on every prediction | predictions records, `src/serving_contract.py` | present on 100% of predictions | 212 / 212 predictions carry prompt v1.0.0 and the generation dict | PASS |
| 16 | Data leakage | problems shared between train, validation, test | data component check (raises on overlap) | 0 | 0 (component would fail otherwise) | PASS |
| 17 | Tests and CI | unit tests + harness gate on every push | GitHub Actions (`eval.yml`) | green | green on PR #9 (tests + gate on recorded predictions) | PASS |

## Operations and cost

| # | Item | Metric | Method | Threshold | Measured | Status |
|---|---|---|---|---|---|---|
| 18 | Monitoring | traces with latency, cost, errors, model and prompt version | Langfuse (M7) | in place before production | not built | **FAIL** |
| 19 | Cost per call | euros per tutor reply | Billing reports (labels `team=benjosh`) / calls | to set from the cost model | billing figures not yet read | NOT MEASURED |
| 20 | Endpoint shut down after use | endpoint deleted after each session | `scripts/delete_endpoint.py` (prints the time) | 100% of sessions | procedure written in `docs/m5-serving-rules.md` | PASS (procedure) |
| 21 | Rollback | a way back if the served model misbehaves | registered model versions; replay mode for demos | documented | model v1 only; delete the endpoint; replay mode | PASS (minimal) |

## Summary

Not production-ready yet: prompt-injection robustness (item 3), monitoring (item 18), and endpoint availability
(item 12) fail or are not met, and Socratic quality, end-to-end latency and cost are not measured. The core
behaviour is measured and positive: no leak on the 80 test cards, 1 on 106 cases overall, and replies closer to
human tutors than prompting alone.
