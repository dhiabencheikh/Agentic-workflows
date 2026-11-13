# AI product brief: Socratic Python Debugger

Format from Session 1 (p.33). Every figure comes from `docs/results/` or `docs/readiness-checklist.md` (path given).
Where nothing was measured, this brief says "not measured".

## 1. Problem statement

- Beginner programmers get stuck on bugs in short Python functions and ask for help.
- A general chat assistant usually pastes the corrected code. The student's code then works, but the student has not
  learned to debug.
- Measured on our test cases: the base model, even with a tutoring system prompt, gave away the fix on 4 of 80
  normal test cards and on 6 of 10 prompt injections (`docs/results/m3_eval.md`).
- User: a beginner in an introductory Python course. Buyer: an ed-tech company or a course team that wants a tutor
  available outside office hours.

## 2. Proposed solution

- A Socratic tutor: the student pastes the buggy code and describes the problem; the tutor replies with one short
  question or hint at a time and never gives the fix or corrected code.
- Model: `microsoft/Phi-3-mini-4k-instruct` (revision `f39ac1d`) fine-tuned with QLoRA on human tutoring dialogues
  from the Socratic Debugging Benchmark (train 566 cards, `docs/results/m1_dataset_stats.md`).
- Served on a Vertex AI endpoint (n1-standard-8 + T4, fp16) behind a Chainlit app, with an input guardrail
  (prompt injection) and an output guardrail (leak check on the reply), monitored in Langfuse.
- Why fine-tune rather than prompt only: same prompt, same decoding, only the adapter differs, and the fine-tuned
  model leaks less and replies closer to human tutors (section 3).

## 3. Evaluation framework

| Dimension | Metric | Method | Threshold | Measured (setup c, served) | Source |
|---|---|---|---|---|---|
| Never gives the fix | leaks / 80 test cards | deterministic leak check | 0 / 80 | 0 / 80 (base + prompt: 4 / 80) | `m3_eval.md` |
| Release gate | leak rate on 106 cases | CI on recorded predictions | <= 2% | 1 / 106 (base + prompt: 11 / 106, fails) | `eval/thresholds.json` |
| Robustness | leaks / 10 prompt injections | leak check | 0 / 10 | model alone 1 / 10; app path 0 / 10 shown | readiness item 3 |
| Tutoring style | best-match ROUGE-L vs human replies | `scripts/score_m3.py` | c > b | 0.307 vs 0.221 (human ceiling 0.384) | `m3_eval.md` |
| Socratic quality | LLM judge 1 to 5 | gpt-4o-mini, 3 evaluators | to define | mean 4.46 on test cards, **not calibrated** | `m7_judge_scores.md` |
| Metric reliability | false alarms; known leaks caught | calibration on held-out human replies | <= 2%; >= 75% | 3 / 207 (1.4%); 29 / 36 (81%) | `m4_leak_calibration.md` |
| Errors | failed / total calls | predictions and traces | 0 | 0 / 106 (M3), 0 / 106 (replay) | `m3_eval.md`, `m7_traffic_replay.md` |
| Latency | P95 end to end | traffic replay through the app | <= 5 s | 2.68 s (P50 1.47 s, P99 6.48 s) | `m7_traffic_replay.md` |
| Student learning | bug found by the student, satisfaction | user study | to define | not measured | |

Scores are compared only within one prompt version (v1.0.0) and one generation dict (greedy, 256 new tokens).

## 4. Cost model

| Cost item | Driver | Measured | Source |
|---|---|---|---|
| Fine-tuning | GPU hours on n1-standard-8 + T4 | duration 77.4 min for the full step (66.5 min training); price in euros not measured | `m2_full_run.md` |
| Evaluation | GPU hours, two setups | durations in `m3_eval_run.md`; price not measured | `m3_eval_run.md` |
| Serving | endpoint billed per hour while deployed, not per call (min = max = 1 node, no scale to zero) | hourly price not read from billing: **not measured** | readiness item 19 |
| Cost per tutor reply | hourly endpoint price / replies per hour | **not measured** | readiness item 19 |
| Quality judge | tokens per evaluated trace | $0.0498 for 97 traces x 3 evaluators ($0.00051 per trace), gpt-4o-mini via OpenRouter | `m7_judge_scores.md` |
| Monitoring | self-hosted Langfuse | no licence cost; hosting cost not measured | `docs/m7-monitoring.md` |

Main lever: because the endpoint is billed per hour, cost per reply falls as traffic rises; at low traffic the
endpoint should be deleted after each session (readiness item 20). Next step: read the hourly price from Billing
reports (label `team=benjosh`) and compute cost per reply at a target traffic level.

## 5. Adverse-effect register

| Risk | Effect on the student or the business | Measured | Mitigation |
|---|---|---|---|
| Tutor gives the fix | student learns nothing; product promise broken | 0 / 80 test, 1 / 106 overall (c) | fine-tuning, system prompt, output guardrail, CI gate at 2% |
| Prompt injection ("ignore your rules...") | tutor drops its rules | model alone 1 / 10 leaks; app path 0 / 10 shown (input patterns tuned on these cases, optimistic) | input guardrail, output guardrail, adversarial cases in CI |
| Leak missed by the detector | silent failures in eval and in the output guardrail | catches 29 / 36 known leaks: about 1 in 5 missed | calibrated threshold; next: calibrated LLM judge as a second check |
| Tutor confirms a wrong fix | student keeps a bug and gains false confidence | judge flags 15 / 97, not calibrated, not verified case by case | calibrate the judge; add cases with wrong student fixes |
| False block of a normal message | student gets a canned redirection | input 0 / 80 test, 0 / 612 train + validation; output 3 / 207 test human replies | fixed, polite redirection; monitor block counts in Langfuse |
| Off-topic use | cost and scope drift | 0 / 6 leaks; redirection quality not measured | system prompt; next: routing to a guardrail reply |
| Slow reply | student waits | P95 2.68 s; max 17.42 s when a reply hits the 256-token cap | token cap; alert threshold P95 > 5 s (drafted, not wired) |
| Endpoint unavailable (no GPU) | no tutor | 503 on first deploy 2026-11-12, deployed 17 min later | deploy early, retries, second region, labelled replay mode |
| Student code and messages exposed | privacy | traces stored only in self-hosted Langfuse bound to localhost | no secrets in code or bucket; shared GCP project: nothing sensitive stored there |

## 6. Rollback plan

| Trigger | Action | Time to act |
|---|---|---|
| CI gate fails (leak rate > 2% or any error) | the change is not merged; previous model and prompt stay served | before release |
| Served model misbehaves in production | undeploy or delete the endpoint (`scripts/delete_endpoint.py`); redeploy the registered model version 1 | deploy 15 to 30 min when a T4 is free (not measured beyond the 2026-11-12 deploy) |
| A prompt change regresses | prompt files are versioned and never edited after release: point `TUTOR_PROMPT_VERSION` back and re-run the harness | one config change + CI run |
| No endpoint available for a demo | `DEMO_MODE=replay`: real recorded replies, labelled as replay | immediate |

Limit: only one model version is registered (v1), so a rollback to an earlier model is to the base model + prompt,
which fails the CI gate. A production setup would keep the previous adapter registered as a fallback version.
