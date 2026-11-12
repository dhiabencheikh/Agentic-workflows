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

## Access needed (check with Dhia)

`roles/aiplatform.user` (register model, create, deploy, undeploy, delete endpoint, predict),
write access to `gs://benjosh-llmops` (upload handler and config), `roles/logging.viewer` (container logs).
Serving has **its own GPU quota**, separate from training: "Custom model serving Nvidia T4 GPUs per region" must be above 0 in europe-west2.
