"""Custom EndpointHandler for the Vertex AI Hugging Face serving container (Session 4 practice).

Copied by scripts/register_model_with_custom_handler.py to the root of the model artifacts folder,
next to the LoRA adapter, serving_config.json and the prompt file. It runs inside Google's serving
container, so it CANNOT import this repository: every rule comes from serving_config.json
(docs/m5-serving-rules.md, built by src/serving_contract.py).

Request (Vertex predict format):
    {"instances": [{"messages": [{"role": "user", "content": "..."}, ...]}], "parameters": {...}}
    messages = the conversation WITHOUT a system message, ending with the student's turn.
Response:
    {"predictions": [{"response": "...", "prompt_version": "1.0.0", "model": {...},
                      "input_tokens": n, "output_tokens": n, "latency_seconds": s,
                      "system_messages_removed": n, "ignored_parameters": [...], "error": null}]}
"""

import json
import logging
import os
import time
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

logger = logging.getLogger(__name__)
MODEL_DIR = "/opt/huggingface/model"


class EndpointHandler:
    """Loads base model + LoRA adapter in the served precision; adds the system prompt server-side."""

    def __init__(self, model_dir: str = MODEL_DIR) -> None:
        with open(os.path.join(model_dir, "serving_config.json"), encoding="utf-8") as f:
            self.config = json.load(f)
        with open(os.path.join(model_dir, self.config["prompt_file"]), encoding="utf-8") as f:
            self.system_prompt = f.read().rstrip("\n")
        self.generation = self.config["generation"]  # rule 2: one decoding definition

        on_gpu = torch.cuda.is_available()
        dtype = getattr(torch, self.config["torch_dtype"]) if on_gpu else torch.float32  # rule 3: fp16 on GPU
        base_id = self.config["base_model_id"]
        revision = None if os.path.isdir(base_id) else self.config["base_model_revision"]  # rule 4: pinned
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        base = AutoModelForCausalLM.from_pretrained(
            base_id, revision=revision, torch_dtype=dtype, device_map={"": 0} if on_gpu else None
        )
        if os.path.exists(os.path.join(model_dir, "adapter_config.json")):
            from peft import PeftModel

            self.model = PeftModel.from_pretrained(base, model_dir)
        else:
            self.model = base
        self.model.eval()
        self.model_info = {"base_model_id": base_id, "base_model_revision": revision, "adapter": model_dir,
                           "torch_dtype": str(dtype).replace("torch.", "")}
        logger.info(f"Loaded {self.model_info}, prompt v{self.config['prompt_version']}, generation {self.generation}")

    def build_messages(self, messages: list) -> tuple[list, int]:
        """Rule 1: drop any client system message, add ours once; the conversation must end with the student."""
        conversation = [m for m in messages if m.get("role") != "system"]
        removed = len(messages) - len(conversation)
        roles = [m.get("role") for m in conversation]
        if not roles or roles[0] != "user" or roles[-1] != "user" or any(a == b for a, b in zip(roles, roles[1:])):
            raise ValueError(f"messages must alternate user/assistant, start and end with user; got {roles}")
        return [{"role": "system", "content": self.system_prompt}, *conversation], removed

    def predict_one(self, instance: dict, client_parameters: dict) -> dict[str, Any]:
        result = {"response": None, "prompt_version": self.config["prompt_version"], "model": self.model_info,
                  "input_tokens": None, "output_tokens": None, "latency_seconds": None,
                  "system_messages_removed": 0, "ignored_parameters": sorted(client_parameters), "error": None}
        try:
            messages, removed = self.build_messages(instance["messages"])
            result["system_messages_removed"] = removed
            input_ids = self.tokenizer.apply_chat_template(
                messages, add_generation_prompt=True, return_tensors="pt"
            ).to(self.model.device)
            start = time.time()
            with torch.no_grad():
                output = self.model.generate(
                    input_ids,
                    attention_mask=torch.ones_like(input_ids),
                    pad_token_id=self.tokenizer.unk_token_id,
                    **self.generation,
                )
            new_tokens = output[0][input_ids.shape[1]:]
            result.update({
                "response": self.tokenizer.decode(new_tokens, skip_special_tokens=True).strip(),
                "input_tokens": int(input_ids.shape[1]),
                "output_tokens": int(new_tokens.shape[0]),
                "latency_seconds": round(time.time() - start, 3),
            })
        except Exception as error:  # one bad instance must not fail the whole request
            result["error"] = f"{type(error).__name__}: {error}"
            logger.exception("prediction failed")
        return result

    def __call__(self, data: dict[str, Any]) -> dict[str, list[Any]]:
        # Rule 2: decoding is fixed by serving_config.json; client parameters are reported, not applied.
        client_parameters = data.get("parameters") or {}
        return {"predictions": [self.predict_one(i, client_parameters) for i in data.get("instances", [])]}
