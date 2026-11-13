# M7 monitoring with Langfuse (Session 5 practice)

## 1. Langfuse, self-hosted

- Official Docker Compose of Langfuse release v4.79.0, in `~/langfuse-selfhost` (outside the repo).
- Hardening done before the first start: random `ENCRYPTION_KEY`, `SALT`, `NEXTAUTH_SECRET` in
  `~/langfuse-selfhost/.env` (the compose defaults are placeholders marked `CHANGEME`; Langfuse encrypts the
  stored OpenAI key with `ENCRYPTION_KEY`), and every published port bound to 127.0.0.1
  (`docker-compose.override.yml`; by default 3000, 3031 and 9090 were open to the network).
- Start / stop: `cd ~/langfuse-selfhost && docker compose up -d` / `docker compose down` (data kept in volumes).
- Health: `curl http://localhost:3000/api/public/health` returned `{"status":"OK","version":"4.79.0"}` on 2026-11-12.

## 2. Project and API keys (in the browser)

1. Open http://localhost:3000, sign up (local account), create an organisation, then a project `socratic-tutor`.
2. Project settings > API keys > Create new API key.
3. Add to the repo's `.env` (git-ignored):
   ```env
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=http://localhost:3000
   ```
4. Restart the app: `uv run chainlit run src/app/main.py`. Each student message creates one trace.
   **Trap:** the Langfuse UI shows `LANGFUSE_BASE_URL`, but SDK 3.15 reads `LANGFUSE_HOST`. Without
   `LANGFUSE_HOST`, the SDK sends traces to Langfuse's cloud, not to the local server: keep both lines.
5. Checked on 2026-11-12 at 22:49 UTC: one live request produced span `tutor-turn` + generation
   `endpoint-generation` (model name, usage 200 input / 13 output tokens, 1.2 s, level DEFAULT) in the local
   Langfuse. Langfuse v4 has no trace-reading API (`events_only` mode): traces are read in the UI.

## 3. What is logged (`src/app/tracing.py`)

| Observation | Input | Output | Metadata |
|---|---|---|---|
| span `tutor-turn` | raw student message | reply shown to the student | level ERROR if the call fails |
| generation `endpoint-generation` (nested) | server-side system prompt + conversation (chat messages; the Phi-3 template is applied inside the endpoint) | raw prediction (response, token counts, latency, prompt version, model info) | model name, `model_parameters` = `GENERATION_PARAMETERS`, deployed model id and version, prompt version, region, server and round-trip latency, token usage |

Blocked OpenTelemetry scopes: `chainlit` and `fastapi` (`Langfuse(blocked_instrumentation_scopes=["chainlit", "fastapi"])`).
Each student message starts a fresh trace (`new_trace` in `src/app/tracing.py`).

**Bug found and fixed on 2026-11-12:** about 12 messages sent from Chainlit showed as 1 trace. ClickHouse showed
all 40 `tutor-turn` spans stored, but as children of the web server's long-lived `WS /ws/socket.io/{path}` span
(scope `fastapi`): a whole conversation was one trace, buried among socket.io spans. Fix: a fresh trace id per
message plus blocking the `fastapi` scope. Checked by sending a message through the app: 1 trace, 2 observations,
no web-server spans.

Turn logic (input guardrail, traced model call, output guardrail) lives in `src/app/turn.py`, shared by the
Chainlit app and `scripts/replay_traffic.py`, so the replayed traffic follows the demo path exactly. A blocked input
is logged as a `guardrail-block` trace (no model call); a blocked output adds an `output-guardrail-block` trace
(a separate trace for now, so 106 turns gave 107 traces).
SDK pinned to 3.15.0: the version whose API the practice uses (5.2.0 removed `blocked_instrumentation_scopes`
and `start_as_current_generation`).

## 4. Dashboard (Dashboards > New dashboard)

| Widget | View / measure | Breakdown | Alert threshold (draft) |
|---|---|---|---|
| Latency P50, P95, P99 | observations named `endpoint-generation`, latency percentiles | by hour | P95 > 5 s (M3 measured P95 2.7 s of generation on a T4) |
| Error rate | count of observations with level ERROR / all `endpoint-generation` | by hour | > 0 errors (M3: 0 / 212) |
| Trace count | traces | by hour | none (volume) |
| Tokens | sum of input / output tokens | by hour | none |
| Judge scores (after section 5) | mean `socratic_quality`, sum `leak` | by day | mean < 4 or any leak = 1 |

### Measured traffic (2026-11-12 23:53 to 23:55 UTC, `docs/results/m7_traffic_replay.md`)

The 106 eval cases (80 test + 26 adversarial) sent one at a time through `src/app/turn.py` to endpoint
`298550392290017280`. Stored in Langfuse (ClickHouse count): 97 `tutor-turn` + 97 `endpoint-generation`,
9 `guardrail-block`, 1 `output-guardrail-block`.

| Measure | Value |
|---|---|
| Errors | 0 / 106 |
| End-to-end latency, all 106 turns | P50 1.47 s, P95 2.68 s, P99 6.48 s, max 17.42 s |
| End-to-end latency, 97 turns that called the model | P50 1.54 s, P95 2.68 s, max 17.42 s |
| Slowest turn | `adv-off_topic-01`, 17.4 s: 256 output tokens, the generation cap |
| Outcomes | 96 answered, 9 blocked at input (prompt injections), 1 blocked at output (`adv-prompt_injection-03`) |
| Judge score distribution | see section 5 and `docs/results/m7_judge_scores.md` |

Cost per call: **not computable yet**. The endpoint is billed per hour while deployed, not per token, so cost per
call = hourly endpoint price / calls per hour; the hourly price will come from Billing > Reports (label
`team=benjosh`). Judge calls add the OpenAI cost of section 5.

## 5. LLM-as-a-judge (prompts in `eval/judge_prompts.py`)

Approved 2026-11-12: **gpt-4o-mini, on new traces only**. **Not calibrated against human labels yet**: its scores are indicative until checked on human tutor replies (should score high) and known leaks (should score low).

1. Project settings > LLM connections > add OpenAI with the school API key.
2. LLM-as-a-judge > default evaluator model: choose the approved model.
3. Create custom evaluators `socratic_quality` (score 1 to 5, few-shot) and `leak` (0 or 1), pasting the templates.
4. Map `{{input}}` to the input of observation `endpoint-generation` and `{{output}}` to its output.
5. Set it up on new traces only, filtered to `endpoint-generation` (and optionally a sampling rate).

**Cost estimate per evaluated trace** (both evaluators). Input tokens measured with the gpt-4o tokenizer
(`o200k_base`) on the 106 M3 traces of setup c: median 1,923, max 3,682. Output tokens are an **assumption**
(score + one sentence per evaluator). Prices: OpenAI standard pricing, https://developers.openai.com/api/docs/pricing,
read 2026-11-12, USD per 1M tokens (gpt-4o-mini 0.15 in / 0.60 out; gpt-4.1-mini 0.40 / 1.60; gpt-4o 2.50 / 10.00).

| Judge model | Per trace, median (60 / 120 output tokens per evaluator) | Per trace, max | 106 traces (median, 120 out) |
|---|---|---|---|
| gpt-4o-mini | $0.00036 / $0.00043 | $0.00070 | $0.046 |
| gpt-4.1-mini | $0.00096 / $0.00115 | $0.00186 | $0.122 |
| gpt-4o | $0.00601 / $0.00721 | $0.01160 | $0.764 |

**Run on 2026-11-13 (00:05 UTC) by `scripts/judge_traces.py`**, not by the Langfuse UI evaluator: the third
evaluator, `confirms_incorrect_fix`, needs the known bug (a hidden card field), which a UI evaluator cannot map. Judge
`openai/gpt-4o-mini` through OpenRouter's OpenAI-compatible API (https://openrouter.ai/api/v1), listed at the same
price as OpenAI (0.15 / 0.60 USD per 1M tokens, read from OpenRouter's models API). Scores are written to each
trace in Langfuse (ids `judge-<trace>-<evaluator>`, so a rerun overwrites). Full text was read from ClickHouse
`events_full`: `events_core` cuts input and output at 200 characters.

| Evaluator | 80 test cards | 17 adversarial replies |
|---|---|---|
| socratic_quality (1 to 5) | mean 4.46; 5: 62, 4: 5, 3: 6, 2: 2, 1: 5 | mean 3.29; 5: 7, 4: 1, 3: 4, 1: 5 |
| leak (0/1) | 7 flagged | 2 flagged |
| confirms_incorrect_fix (0/1) | 14 flagged | 1 flagged |

Cost: 285,092 input + 11,743 output tokens = $0.0498 for 97 traces x 3 evaluators ($0.00051 per trace).

**Why these scores are not trusted yet:** the deterministic leak check, calibrated on human replies, finds 0 leaks
on the same 80 test replies; the judge flags 7. Reading the flagged reasons, the judge counts targeted hints
as leaks, and some `confirms_incorrect_fix` reasons only say the tutor agreed "without verifying" the fix, not that the fix was wrong (not checked case by case). Recorded as
a limit. Next step: calibrate on human tutor replies and known leaks before using a judge score
for alerts.

Earlier status (2026-11-12): not enabled. The `OPENAI_API_KEY` in `.env` is an OpenRouter key (`sk-or-`): OpenAI rejects it
(401 in `scripts/calibrate_judge.py`). To enable: a real OpenAI key in Langfuse's LLM connection, or an OpenRouter
connection (OpenAI-compatible) after checking its gpt-4o-mini price. Existing traces are not scored (new traces only).

The judge has not been calibrated against human labels yet (to do: `scripts/calibrate_judge.py`, 20 human replies
and 10 known leaks from validation).
