"""Inference component for Vertex AI pipeline: tutor replies for one M3 setup.

Setups (eval/README.md section 3), one variable changed at a time:
  a: base Phi-3, no system prompt
  b: base Phi-3 + system prompt
  c: base Phi-3 + our LoRA adapter + system prompt
Writes one prediction per case in the predictions format of eval/README.md.
"""

from kfp.dsl import Dataset, Input, Model, Output, component


@component(
    base_image="pytorch/pytorch:2.8.0-cuda12.9-cudnn9-devel",
    packages_to_install=[
        "transformers==4.46.3",
        "peft==0.13.2",
        "accelerate==1.15.0",
        "gcsfs==2025.9.0",
    ],
)
def inference_component(
    test_dataset: Input[Dataset],
    setup: str,
    base_model_id: str,
    base_model_revision: str,
    system_prompt: str,
    prompt_version: str,
    generation: dict,
    extra_cases_uri: str,
    max_cases: int,
    predictions: Output[Dataset],
    adapter: Input[Model] = None,
) -> None:
    """Generate one reply per test case for the given setup.

    Args:
        test_dataset: M1 test cards (system prompt first, human reply last).
        setup: "a", "b" or "c".
        base_model_id, base_model_revision: pinned base model (a local folder works for tests).
        system_prompt, prompt_version: from prompts/ via the runner; ignored in setup a.
        generation: GENERATION_PARAMETERS from constants.py.
        extra_cases_uri: "" or a JSONL file of hand-written cases (eval/README.md format).
        max_cases: 0 for all cases; N for a smoke run on the first N.
        predictions: output JSONL, one prediction per case.
        adapter: the fine-tuning output (LoRA adapter); required for setup c only.
    """
    import json
    import logging
    import os
    import statistics
    import time

    import fsspec
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # --- Copy of src/eval_cases.py (a component cannot import repo code). ---
    # tests/test_inference.py checks that both give the same model input.
    def validate_case_messages(messages: list) -> None:
        roles = [m["role"] for m in messages]
        if not roles or "system" in roles or roles[0] != "user" or roles[-1] != "user":
            raise ValueError(f"invalid case messages (no system message, start and end with user): {roles}")
        if any(a == b for a, b in zip(roles, roles[1:])):
            raise ValueError(f"roles must alternate: {roles}")

    def card_to_case(card: dict) -> dict:
        messages = card["messages"]
        if messages[0]["role"] != "system" or messages[-1]["role"] != "assistant":
            raise ValueError(f"{card['example_id']}: expected [system, ..., assistant]")
        return {"id": card["example_id"], "messages": messages[1:-1]}

    def build_messages(case_messages: list) -> list:
        validate_case_messages(case_messages)
        if setup == "a":
            return list(case_messages)
        return [{"role": "system", "content": system_prompt}, *case_messages]
    # --- End of copy. ---

    if setup not in ("a", "b", "c"):
        raise ValueError(f"unknown setup {setup!r}")
    if setup == "c" and adapter is None:
        raise ValueError("setup c needs the fine-tuned adapter")
    if setup in ("b", "c") and not system_prompt:
        raise ValueError(f"setup {setup} needs a system prompt")

    with open(test_dataset.path, encoding="utf-8") as file:
        cases = [card_to_case(json.loads(line)) for line in file]
    if extra_cases_uri:
        with fsspec.open(extra_cases_uri, "r", encoding="utf-8") as file:
            extra = [json.loads(line) for line in file if line.strip()]
        for case in extra:
            validate_case_messages(case["messages"])
        cases += [{"id": c["id"], "messages": c["messages"]} for c in extra]
    if max_cases:
        cases = cases[:max_cases]
    logger.info(f"Setup {setup}: {len(cases)} cases")

    # Model: fp16 on GPU without quantization (Session 4 slide 20), the same base for all setups.
    is_local_model = os.path.isdir(base_model_id)
    revision = None if is_local_model else base_model_revision
    on_gpu = torch.cuda.is_available()
    tokenizer = AutoTokenizer.from_pretrained(base_model_id, revision=revision)
    model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        revision=revision,
        torch_dtype=torch.float16 if on_gpu else torch.float32,
        device_map={"": 0} if on_gpu else None,
    )
    adapter_uri = None
    if setup == "c":
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, adapter.path)
        adapter_uri = adapter.uri
    model.eval()

    # Stop at the end of the tutor's turn. Phi-3's generation_config lists these three ids
    # (32000, 32001, 32007); tokenizer.eos_token_id alone is <|endoftext|> and would let the
    # model write past <|end|>.
    stop_ids = [tokenizer.convert_tokens_to_ids(t) for t in ("<|endoftext|>", "<|assistant|>", "<|end|>")]

    records, latencies = [], []
    for case in cases:
        record = {
            "case_id": case["id"],
            "setup": setup,
            "model": {"base_model_id": base_model_id, "base_model_revision": revision, "adapter_uri": adapter_uri},
            "prompt_version": None if setup == "a" else prompt_version,
            "generation": generation,
            "response": None,
            "input_tokens": None,
            "output_tokens": None,
            "latency_seconds": None,
            "error": None,
        }
        try:
            input_ids = tokenizer.apply_chat_template(
                build_messages(case["messages"]), add_generation_prompt=True, return_tensors="pt"
            ).to(model.device)
            start = time.time()
            with torch.no_grad():
                output = model.generate(
                    input_ids,
                    attention_mask=torch.ones_like(input_ids),
                    eos_token_id=stop_ids,
                    pad_token_id=tokenizer.unk_token_id,
                    **generation,
                )
            latency = time.time() - start
            new_tokens = output[0][input_ids.shape[1]:]
            record.update(
                {
                    "response": tokenizer.decode(new_tokens, skip_special_tokens=True).strip(),
                    "input_tokens": int(input_ids.shape[1]),
                    "output_tokens": int(new_tokens.shape[0]),
                    "latency_seconds": round(latency, 3),
                }
            )
            latencies.append(latency)
        except Exception as error:  # one failed case must not lose the others
            record["error"] = f"{type(error).__name__}: {error}"
            logger.exception(f"Case {case['id']} failed")
        records.append(record)

    os.makedirs(os.path.dirname(predictions.path) or ".", exist_ok=True)
    with open(predictions.path, "w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    errors = sum(r["error"] is not None for r in records)
    predictions.metadata.update({"setup": setup, "cases": len(records), "errors": errors,
                                 "prompt_version": None if setup == "a" else prompt_version})
    logger.info(
        f"Setup {setup}: {len(records)} predictions, {errors} errors, "
        f"median latency {statistics.median(latencies) if latencies else 0:.2f} s -> {predictions.path}"
    )
