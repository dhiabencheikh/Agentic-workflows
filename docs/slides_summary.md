# Slides summary (presentation 2026-11-13)

Every figure below comes from a committed results file (path given). Times are UTC.

## 1. Problem and product
- Beginner programmers paste buggy Python; a Socratic tutor asks guiding questions and **never gives the fix**.
- Why fine-tune: base instruct models tend to paste the corrected code (measured below: base + prompt gave the
  full corrected function under 6 of 10 prompt injections).

## 2. Data (M1) - `docs/results/m1_dataset_stats.md`
- Socratic Debugging Benchmark (Al-Hossami et al., BEA 2023 / SIGCSE 2024), 150 dialogue files.
- One card = conversation so far -> next tutor reply. Split **by problem**: train 566, validation 99, test 80 cards.
- Fixes found by reading the data: 7 training targets contained the student's corrected code (misattributed
  `<code>` blocks), near-duplicate cards (679 -> 665 train folder), two misnamed files.
- Longest card 2,066 tokens (limit 4,096): nothing truncated.

## 3. Fine-tuning (M2) - `docs/results/m2_full_run.md`, figure `docs/figures/m2_loss_curves.png`
- QLoRA on Phi-3-mini-4k-instruct: 4-bit base, LoRA r=8 on 4 projections = 12,582,912 trainable parameters (0.33%).
- Loss only on the tutor reply (median 2.5% of tokens per card).
- Validation loss **1.99 (base) -> 1.42** at update 50 (29% lower), then over-fitting; best checkpoint kept.
- 105 updates, 29.4 s per update on one T4; whole step 77.4 min (7.3 min waiting for the GPU).
- Teacher feedback: the learning-rate schedule was an implicit default (linear, no warm-up). Now explicit; next run:
  warm-up, deliberate schedule, 2 epochs.

## 4. Evaluation (M3) - `docs/results/m3_eval.md`, figure `docs/figures/m3_b_vs_c.png`, examples `docs/results/m3_examples.md`

| | Base + prompt (b) | **Fine-tuned + prompt (c)** | Human tutors |
|---|---|---|---|
| Closeness to human replies (best-match ROUGE-L, mean) | 0.221 | **0.307** | 0.384 (ceiling) |
| Leaks on 80 test cards | 4 | **0** | |
| Leaks on 26 adversarial cases | 7 (6 of 10 injections) | **1** (1 of 10 injections) | |
| P95 generation latency | 10.0 s | **2.7 s** | |
| Median reply length | 30 tokens | **16 tokens** | |

- Same 106 cases, same prompt v1.0.0, same greedy decoding, same fp16 base: only the LoRA adapter differs.
- All 12 flagged replies read by hand: all real leaks. The remaining injection leak is a "translate the function
  into its final correct version for documentation" request.

## 5. Evaluation harness and CI (M4) - `docs/results/m4_leak_calibration.md`, `eval/thresholds.json`
- 106 test cases: 80 test cards + 26 adversarial (ask for the answer, prompt injection, off-topic).
- Deterministic leak check, tuned on train and validation only, test measured once: false alarms 3/207 (1.4%),
  known leaks caught 29/36 (81%).
- GitHub Actions on every push: tests + harness on recorded predictions; fails if leak rate > 2% or any error.
  Proven: passes the fine-tuned model (1/106), fails the base model (11/106).

## 6. Serving (M5) - `docs/m5-serving-rules.md`
- Custom handler: system prompt added server-side only, one decoding definition shared with evaluation, fp16,
  pinned model revision; Chainlit app sends no system prompt.
- Deployment attempt 2026-11-12 21:34: `503 Machine type temporarily unavailable` (no T4 free in europe-west2);
  fallbacks: europe-west4 T4, europe-west2 L4, and a clearly labelled replay mode of real recorded replies.

## 6b. Guardrails (M6) - `docs/results/m6_guardrail.md`, `docs/results/m6_output_guardrail.md`
- Input: prompt-injection patterns on the student's message: 9/10 injection cases blocked (optimistic: cases read
  before writing the patterns), 0/80 test students and 0/612 train + validation student turns falsely blocked.
  Missed: the "translate into the final correct version" reframing, the same case the fine-tuned model leaked on.
- Output: leak check on the reply against the student's own code: blocks all 12 flagged leaks of b and c,
  falsely blocks 3/207 test and 0/1,587 train + validation human replies. Same detector as the evaluation, so it
  inherits its blind spots (about 1 leak in 5).

## 7. Problems encountered (from `docs/learning-log.md`)
- GPU shortages: about 1 h wait (M2, cancelled), 20.9 min (M3), endpoint 503 (M5) -> smaller machine, retries,
  other regions, deploy early, replay fallback.
- Data bugs found by reading the data, not by metrics (misattributed student code).
- A metric that measured nothing: the first harness checked empty strings and reported 0 leaks; fixed and calibrated.
- Implicit defaults: learning-rate schedule, and TRL's 1,024-token default that would have cut replies.

## 8. Not done / next
- LLM judge for Socratic quality: approved (gpt-4o-mini in Langfuse, new traces only) but **not calibrated against human labels yet**;
  routing and caching (M6, design only),
  cost per call (billing figures), a training run with warm-up and 2 epochs.
- Readiness: see `docs/readiness-checklist.md` (fails: prompt-injection robustness, monitoring, endpoint availability).
