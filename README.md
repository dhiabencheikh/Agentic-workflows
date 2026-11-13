# Socratic Python Debugger

An AI tutor for beginner programmers. A student pastes buggy Python and says it does not work. The tutor asks one
guiding question at a time so the student finds the bug, and never hands over the fix or corrected code. We
fine-tuned `microsoft/Phi-3-mini-4k-instruct` with QLoRA on the Socratic Debugging Benchmark, compared it with the
same base model prompted alone, gated releases with a CI evaluation harness, served it on a Vertex AI endpoint behind
a Chainlit app with input and output guardrails, and monitored it with self-hosted Langfuse.

Course project for LLMOps (MSA-DATI09-04), Albert School x Mines Paris PSL. Team BenJosh: Dhia Ben Cheikh and
Saumya (GitHub `sjoshi-rgb`). Every figure in this README comes from a committed results file, linked next to it.

## Architecture

```mermaid
flowchart LR
  subgraph Vertex AI Pipelines
    A[Raw dialogues<br/>gs://benjosh-llmops/raw] --> B[Data component<br/>cards, dedup, split by problem]
    B --> C[Fine-tuning component<br/>QLoRA on T4, best checkpoint]
    B --> D[Inference component<br/>setups b and c on test + adversarial]
    C --> D
  end
  D --> E[Scoring + harness<br/>ROUGE-L, leak check]
  E --> F[CI gate<br/>GitHub Actions]
  C --> G[Model registry<br/>custom handler]
  G --> H[Vertex endpoint<br/>fp16, T4]
  I[Chainlit app] --> J[Input guardrail] --> H --> K[Output guardrail] --> I
  I -.traces.-> L[Langfuse<br/>+ LLM judge]
```

| Step | What it does | Code |
|---|---|---|
| Data (M1) | one card per tutor turn (conversation so far -> next tutor reply), dedup, split by problem | `src/pipeline_components/data_transformation_component.py` |
| Fine-tuning (M2) | QLoRA (4-bit NF4 base, LoRA r=8, alpha 16), loss on the tutor reply only, fp16 | `src/pipeline_components/fine_tuning_component.py` |
| Inference (M3) | base + prompt (b) and fine-tuned + prompt (c), fp16, greedy, same generation dict as serving | `src/pipeline_components/inference_component.py` |
| Evaluation (M3, M4) | best-match ROUGE-L vs human replies, deterministic leak check, CI gate | `eval/`, `scripts/score_m3.py` |
| Serving (M5) | custom handler adds the system prompt server-side; registration, deploy, delete scripts | `src/handler.py`, `scripts/` |
| Guardrails (M6) | prompt-injection check on the input, leak check on the reply | `src/guardrail.py`, `src/output_guardrail.py` |
| Monitoring (M7) | one Langfuse trace per turn, replayed traffic, LLM judge | `src/app/tracing.py`, `scripts/replay_traffic.py`, `scripts/judge_traces.py` |

Single sources of truth: the system prompt in `prompts/tutor_system_v1.0.0.txt` (semantic versioning, loaded by
`src/prompts.py`); model id, pinned revision `f39ac1d` and generation parameters in `src/constants.py` and
`src/serving_contract.py`.

## Results

| Stage | Result | Source |
|---|---|---|
| Data (M1) | train 566, validation 99, test 80 cards; split by problem; longest card 2,066 tokens (nothing truncated) | `docs/results/m1_dataset_stats.md` |
| Fine-tuning (M2) | validation loss 1.99 before training -> 1.42 at update 50 (best checkpoint kept, over-fitting after); 105 updates on one T4 | `docs/results/m2_full_run.md`, `docs/figures/m2_loss_curves.png` |
| Evaluation (M3) | see the table below | `docs/results/m3_eval.md`, `docs/figures/m3_b_vs_c.png` |
| Leak check calibration (M4) | test: false alarms on human replies 3/207 (1.4%); known leaks caught 29/36 (81%) | `docs/results/m4_leak_calibration.md` |
| CI gate (M4) | fails if leak rate > 2% or any inference error; passes setup c (1/106), fails setup b (11/106) | `eval/thresholds.json`, `.github/workflows/eval.yml` |
| Input guardrail (M6) | 9/10 prompt injections blocked (optimistic: patterns written after reading the 10 cases); 0/80 test and 0/612 train + validation student turns blocked | `docs/results/m6_guardrail.md` |
| Output guardrail (M6) | blocks 12/12 flagged leaks of b and c; falsely blocks 3/207 test and 0/1,587 train + validation human replies | `docs/results/m6_output_guardrail.md` |
| Served = evaluated (M5) | 5/5 endpoint replies identical to M3 setup c | `docs/readiness-checklist.md` item 16b |
| Traffic replay (M7) | 106 cases through the app path: 0 errors; end-to-end P50 1.47 s, P95 2.68 s, P99 6.48 s, max 17.42 s | `docs/results/m7_traffic_replay.md` |
| LLM judge (M7) | gpt-4o-mini via OpenRouter, socratic_quality mean 4.46 on test cards, $0.0498 for 97 traces; **not calibrated** | `docs/results/m7_judge_scores.md` |

M3, same 106 cases (80 test cards + 26 adversarial), same prompt v1.0.0, same greedy decoding, same fp16 base: only
the LoRA adapter differs.

| | b: base + prompt | **c: fine-tuned + prompt** | Human tutors |
|---|---|---|---|
| Best-match ROUGE-L on test cards (mean) | 0.221 | **0.307** | 0.384 (ceiling) |
| Leaks on 80 test cards | 4/80 | **0/80** | |
| Leaks on 26 adversarial cases | 7/26 | **1/26** | |
| P95 generation latency (T4) | 10.0 s | **2.7 s** | |
| Median output tokens | 30 | **16** | |
| Inference errors | 0/106 | 0/106 | |

## Milestone status

| Milestone | Status | Note |
|---|---|---|
| M0 setup | done | GCP project, bucket, uv, `.env`, collaborators |
| M1 data | done | |
| M2 fine-tune | done | learning-rate schedule was an implicit default (linear, no warm-up); next run: warm-up, 2 epochs |
| M3 predict + evaluate | done | setups b and c; setup a (base without prompt) not run |
| M4 eval harness + CI | done | 106 cases, calibrated leak check, gate proven on b and c |
| M5 serving | done | endpoint deployed and answering on 2026-11-12; Chainlit app; replay mode |
| M6 guardrails | done | input and output guardrails (not in the original plan) |
| M6 routing and semantic caching | **not done** | design only |
| M7 monitoring | partial | traces, latency percentiles, error rate, uncalibrated judge scores; no cost per call, no alert that fires |
| M8 checklist and brief | done | `docs/readiness-checklist.md`, `docs/product-brief.md` |

## How to run

### Setup

```bash
uv sync                                   # Python 3.11.6, exact versions from uv.lock
gcloud auth login && gcloud auth application-default login
cp .env.example .env                      # fill in GCP project, bucket, region, keys (never committed)
uv run python -m scripts.validate_gcp_setup
```

### Pipelines on Vertex AI (GPU: costs money, ask before launching)

```bash
uv run python -m scripts.pipeline_runner --mode smoke     # data + short fine-tuning test
uv run python -m scripts.pipeline_runner --mode full      # data + full fine-tuning
uv run python -m scripts.evaluation_runner --adapter-uri gs://.../model --mode full \
    --extra-cases-uri gs://benjosh-llmops/eval/cases_adversarial_96d7834.jsonl
uv run --with matplotlib python -m scripts.score_m3 --job <evaluation job id> \
    --adversarial-uri gs://benjosh-llmops/eval/cases_adversarial_96d7834.jsonl
```

### Evaluation harness and tests (no GPU)

```bash
uv run --no-dev --with pytest pytest -q
uv run --no-dev python -m eval.run_eval --cards eval/test_cards.jsonl --cases eval/triples_adversarial.jsonl \
    --predictions eval/recorded/predictions_c.jsonl --out harness_results/c.json \
    --max-leak-rate 0.02 --max-error-rate 0
```

The same harness runs in GitHub Actions on every push (`.github/workflows/eval.yml`).

### Endpoint (billed per hour while deployed: always delete after use)

```bash
uv run --no-dev python -m scripts.deploy_endpoint --region europe-west2 \
  --model projects/123905721265/locations/europe-west2/models/5118624650506534912 --retries 4 --retry-wait 180
# put the printed GCP_ENDPOINT_ID in .env
uv run --no-dev python -m scripts.delete_endpoint --region europe-west2 --endpoint <GCP_ENDPOINT_ID>
```

Registration, fallback region and rules: `docs/m5-serving-rules.md`.

### Chainlit tutor

```bash
uv run --no-dev chainlit run src/app/main.py                     # live, needs the endpoint
DEMO_MODE=replay uv run --no-dev chainlit run src/app/main.py    # recorded M3 replies, labelled as replay
```

### Monitoring (Langfuse, self-hosted)

```bash
cd ~/langfuse-selfhost && docker compose up -d     # http://localhost:3000; set up in docs/m7-monitoring.md
uv run --no-dev python -m scripts.replay_traffic                                   # 106 traced turns
uv run --no-dev python -m scripts.judge_traces --since "<UTC start of the replay>"  # paid API calls
```

`.env` needs `LANGFUSE_HOST=http://localhost:3000` (SDK 3.15 reads it, not `LANGFUSE_BASE_URL`).

## Repository map

```
prompts/tutor_system_v1.0.0.txt   the only copy of the system prompt
src/
  constants.py  prompts.py  serving_contract.py   configuration, prompt loader, serving rules
  pipeline_components/            data, fine-tuning, inference components
  pipelines/                      training and evaluation pipelines
  handler.py                      Vertex custom handler (server-side prompt, fp16, adapter)
  guardrail.py  output_guardrail.py
  eval_cases.py                   test cards -> test cases
  app/                            Chainlit app, endpoint client, tracing, shared turn, replay mode
scripts/                          runners, registration, deploy/delete, scoring, calibration, replay, judge
eval/                             harness, leak check, similarity, judge prompts, cases, thresholds, recorded predictions
tests/                            pytest unit tests (run in CI)
notebooks/                        local exploration before componentising
docs/
  results/                        committed outputs of runs: the source of every figure
  readiness-checklist.md  product-brief.md  m5-serving-rules.md  m7-monitoring.md
  learning-log.md  concepts.md  slides_summary.md  STATUS.md
```

## Known limitations

- **Prompt injection, model alone:** the fine-tuned model still leaks on 1 of 10 injections (`adv-prompt_injection-03`, "translate the function into its final correct version"). In the app the output guardrail blocks it, but the input guardrail's 9/10 is optimistic: its patterns were written after reading those 10 cases.
- **Leak check blind spot:** it catches 29/36 known leaks (81%), so about 1 leak in 5 can pass unnoticed. Example: the base model's factorial reply gives the corrected loop `for i in range(1, n + 1):`, yet the leak check scored it a pass (`docs/results/m3_examples.md`). Base-model leaks are therefore, if anything, under-counted, so the b vs c leak comparison is conservative. The output guardrail uses the same detector and inherits this blind spot.
- **Tutor confirms an incorrect fix (manual demo observation, not in a results file):** in a Chainlit dry run on test problem 24 (factorial), the fine-tuned tutor answered "Good work!" to the wrong fix "Set the i in range(1, n)." (still off by one) and gave the same "Good work!" to the correct `range(1, n+1)`; it then told the student to run the code. The tutor does not check a proposed fix. Langfuse traces of 2026-11-12, 23:07 to 23:41 UTC. No metric covers this yet. Next step: prompt v1.1.0 asking the student to check a proposed fix against the examples, re-evaluated through the CI gate.
- **LLM judge not calibrated:** it flags 7/80 test replies as leaks where the deterministic check finds 0, and treats targeted hints as leaks. Its scores are indicative only.
- **Cost per call not measured:** the endpoint is billed per hour, not per call; billing figures have not been read. Only the judge cost is measured.
- **No routing or semantic caching**, no alert that fires, setup a not evaluated.
- **Small test set:** 80 cards from 4 problems; P99 on about 100 requests rests on one or two values.

## Dataset and citation

We use the Socratic Debugging Benchmark (`v2_sigcse`):
https://github.com/taisazero/socratic-debugging-benchmark

Provenance of our copy:
- Source commit: `3f77f89` (2024-03-22), folders `socratic_debugging_benchmark/v2_sigcse/train` (134 files) and `testset` (16 files)
- Uploaded unchanged on 2026-11-12 to `gs://benjosh-llmops/raw/socratic_debugging_benchmark/v2_sigcse/` (150 files, 606,236 bytes)
- The authors' train/testset split is kept as is: the two sets share no problem

The repository has no license file, so we treat it as academic research data and cite the authors:

- Erfan Al-Hossami, Razvan Bunescu, Ryan Teehan, Laurel Powell, Khyati Mahajan, Mohsen Dorodchi. 2023.
  *Socratic Questioning of Novice Debuggers: A Benchmark Dataset and Preliminary Evaluations.*
  Proceedings of the 18th Workshop on Innovative Use of NLP for Building Educational Applications (BEA 2023), pages 709 to 726.
  https://aclanthology.org/2023.bea-1.57
- Erfan Al-Hossami, Razvan Bunescu, Justin Smith, Ryan Teehan. 2024.
  *Can Language Models Employ the Socratic Method? Experiments with Code Debugging.*
  SIGCSE 2024, pages 53 to 59. https://doi.org/10.1145/3626252.3630799

## Acknowledgements

The starting code (Sessions 1 and 2) comes from the course practice solution by Mathieu Soul. Fine-tuning approach
adapted from https://huggingface.co/blog/dvgodoy/fine-tuning-llm-hugging-face.
