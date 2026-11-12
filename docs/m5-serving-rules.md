# M5 serving rules (read before writing M5 code)

**Principle: what M3 evaluates is exactly what M5 serves.** Every evaluation score describes one system:
base model + revision + LoRA adapter + system prompt + decoding + precision. If the served system differs
in any of these, the M3 scores no longer describe it, and M3 must be re-run before serving.

Single source in code: [`src/serving_contract.py`](../src/serving_contract.py).

## The rules

| # | Rule | Where it is defined | Why |
|---|---|---|---|
| 1 | **The system prompt is added server-side only**, by the handler. Chainlit (and any client) sends the conversation **without** a system message. | `prompts/tutor_system_v1.0.0.txt`, loaded by `src/prompts.py` | A client cannot remove or change the tutor's rules; no double prompt; the served prompt is the evaluated one (eval/README.md: inference adds the prompt, cases never contain it). |
| 2 | **One decoding definition**: greedy, 256 new tokens, stop tokens 32000, 32001, 32007. The handler ignores client attempts to change them. | `GENERATION_PARAMETERS` in `src/serving_contract.py` | Decoding is part of the evaluated system. A change means re-running M3, like a new prompt version. |
| 3 | **Serve in fp16**, base model without quantization, with the same LoRA adapter. | `SERVING_TORCH_DTYPE` in `src/serving_contract.py` | Evaluate in the precision we serve. Training used a 4-bit base (QLoRA), M3 evaluates in fp16, so M5 serves in fp16. No bitsandbytes needed in the serving container. |
| 4 | **Pinned model revision** for weights and tokenizer. | `BASE_MODEL_ID`, `BASE_MODEL_REVISION` in `src/constants.py` | An upstream change to the weights or chat template must not change our tutor silently. |
| 5 | **Deploy well before the demo, check it answers, delete after every test session.** | This page | The endpoint needs a T4 in europe-west2, which can run out (the first M2 smoke run waited about an hour). Deployment takes 15 to 30 min when a GPU is free. `n1-standard-8` + T4, min = max = 1 node, billed per hour while up, **no scale to zero**. Keep a fallback (recorded demo or the M6 OpenAI route). |

## How the handler receives the rules

`handler.py` runs inside Google's serving container and **cannot import this repo** (same constraint as Kubeflow components).
So the registration script puts the contract **next to `handler.py`** in the model artifacts folder:

```
gs://benjosh-llmops/.../model/          (the fine-tuning output: adapter + tokenizer)
  handler.py                            (uploaded by the registration script)
  serving_config.json                   (= build_serving_config(), written by the registration script)
  tutor_system_v1.0.0.txt               (copied from prompts/ by the registration script)
```

The handler reads `serving_config.json` and the prompt file from its model folder at start-up, and returns
`prompt_version` with every prediction (it feeds the M7 Langfuse metadata).

## Checks before calling M5 done

- [ ] A request whose `instances` contain a system message is refused or has it removed (rule 1).
- [ ] Two identical requests return identical replies (greedy, rule 2).
- [ ] The handler logs the dtype, model revision and prompt version it loaded (rules 3 and 4).
- [ ] On 5 M3 test cases, the endpoint's replies equal the M3 setup c predictions (same system end to end).
- [ ] The endpoint is deleted at the end of every session; record start and delete times for the cost model.

## Commands (registered model, 2026-11-12)

The model is registered once: `projects/123905721265/locations/europe-west2/models/5118624650506534912`
(version 1, adapter from run `benjosh-socratic-tutor-20261112182647`, prompt v1.0.0). Do not re-register to redeploy.

| Step | Command |
|---|---|
| Redeploy (new endpoint, 15 to 30 min when a T4 is free) | `uv run --no-dev python -m scripts.deploy_endpoint --model projects/123905721265/locations/europe-west2/models/5118624650506534912` |
| Point the app to it | put the printed `GCP_ENDPOINT_ID=...` in `.env` |
| Quick test | `uv run --no-dev python -c "from src.app.endpoint_client import TutorEndpoint; print(TutorEndpoint().reply([{'role': 'user', 'content': 'My factorial returns 0 for every n.'}]))"` |
| Demo app | `uv run --no-dev chainlit run src/app/main.py` |
| **Delete after use** (stops the hourly billing) | `uv run --no-dev python -m scripts.delete_endpoint --endpoint <GCP_ENDPOINT_ID>` |

## Morning redeploy (presentation day)

Deploy as early as possible: a T4 can be unavailable for a while (`503 Machine type temporarily unavailable`,
seen on 2026-11-12 at 21:34 UTC in europe-west2). The deploy script retries on that error only.
Delete the endpoint right after the demo.

**Plan A: europe-west2** (model already registered there, no re-registration)

```bash
uv run --no-dev python -m scripts.deploy_endpoint --region europe-west2 \
  --model projects/123905721265/locations/europe-west2/models/5118624650506534912 --retries 4 --retry-wait 180
# then in .env: GCP_REGION=europe-west2 and GCP_ENDPOINT_ID=<printed id>
```

**Plan B: europe-west4** (T4 serving quota 8; the model registry is regional, so register there once)

```bash
uv run --no-dev python -m scripts.register_model_with_custom_handler --region europe-west4 \
  --model-uri gs://benjosh-llmops/vertexai-pipeline-root/123905721265/benjosh-socratic-tutor-20261112182647/fine-tuning-component_-4632991117799849984/model
uv run --no-dev python -m scripts.deploy_endpoint --region europe-west4 \
  --model <model resource name printed by the registration> --retries 4 --retry-wait 180
# then in .env: GCP_REGION=europe-west4 and GCP_ENDPOINT_ID=<printed id>
```

Both plans use n1-standard-8 + 1 T4, fp16, the same adapter and decoding as the M3 evaluation.
If no endpoint is up in time: demo in replay mode (`DEMO_MODE=replay`, recorded M3 replies, see the app).

**After the demo, always:**

```bash
uv run --no-dev python -m scripts.delete_endpoint --region <GCP_REGION> --endpoint <GCP_ENDPOINT_ID>
```

## Access needed (check with Dhia)

`roles/aiplatform.user` (register model, create, deploy, undeploy, delete endpoint, predict),
write access to `gs://benjosh-llmops` (upload handler and config), `roles/logging.viewer` (container logs).
Serving has **its own GPU quota**, separate from training: "Custom model serving Nvidia T4 GPUs per region" must be above 0 in europe-west2.
