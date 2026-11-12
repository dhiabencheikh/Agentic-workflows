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

## 3. What is logged (`src/app/tracing.py`)

| Observation | Input | Output | Metadata |
|---|---|---|---|
| span `tutor-turn` | raw student message | reply shown to the student | level ERROR if the call fails |
| generation `endpoint-generation` (nested) | server-side system prompt + conversation (chat messages; the Phi-3 template is applied inside the endpoint) | raw prediction (response, token counts, latency, prompt version, model info) | model name, `model_parameters` = `GENERATION_PARAMETERS`, deployed model id and version, prompt version, region, server and round-trip latency, token usage |

Chainlit's own OpenTelemetry scope is blocked (`Langfuse(blocked_instrumentation_scopes=["chainlit"])`).
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

Cost per call: **not computable yet**. The endpoint is billed per hour while deployed, not per token, so cost per
call = hourly endpoint price / calls per hour; the hourly price will come from Billing > Reports (label
`team=benjosh`). Judge calls add the OpenAI cost of section 5.

## 5. LLM-as-a-judge (prompts in `eval/judge_prompts.py`) - NOT enabled yet, awaiting approval

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

The judge has not been calibrated against human labels yet (to do: run it on the human replies and the known leaks
of `eval/fixtures/`, as for the deterministic leak check).
