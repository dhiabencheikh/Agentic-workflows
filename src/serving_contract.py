"""The serving contract: what M3 evaluates is exactly what M5 serves.

Plain Python (no AI libraries), so it runs on any laptop. Rules in docs/m5-serving-rules.md.

Everything that changes the tutor's replies is fixed here or points to its single source:
- base model and revision: BASE_MODEL_ID, BASE_MODEL_REVISION in src/constants.py
- system prompt: prompts/tutor_system_v<version>.txt via src/prompts.py
- decoding: GENERATION_PARAMETERS below
- precision: SERVING_TORCH_DTYPE below
A change to any of them means re-running the M3 evaluation before serving, like a new prompt version.

The serving container (handler.py) cannot import this repo. The registration script writes
build_serving_config() to SERVING_CONFIG_FILENAME and copies the prompt file next to handler.py;
the handler reads both from its model folder.
"""

from src.constants import BASE_MODEL_ID, BASE_MODEL_REVISION
from src.prompts import TUTOR_PROMPT_VERSION, tutor_prompt_path

# Decoding (Session 4 slides 18-20).
# - Greedy (do_sample False): same input -> same reply; fair, reproducible evaluation.
# - 256 new tokens (course example value): above the longest human reply (164 tokens in train,
#   78 in test, docs/results/m1_dataset_stats.md), so a leak such as pasted code is not cut off.
# - Stop tokens: Phi-3's generation_config.json ids <|endoftext|> 32000, <|assistant|> 32001,
#   <|end|> 32007. tokenizer.eos_token_id alone is 32000 and would let the model write past <|end|>.
GENERATION_PARAMETERS: dict = {"max_new_tokens": 256, "do_sample": False, "eos_token_id": [32000, 32001, 32007]}

# Precision: evaluate in the precision we serve. QLoRA trains on a 4-bit base (to fit a T4);
# M3 evaluates and M5 serves on an fp16 base without quantization (Session 4 slide 20), with the
# same LoRA adapter. The fp16 weight files total 7.64 GB and fit a T4.
SERVING_TORCH_DTYPE: str = "float16"

SERVING_CONFIG_FILENAME: str = "serving_config.json"


def build_serving_config(prompt_version: str = TUTOR_PROMPT_VERSION) -> dict:
    """Everything the handler needs, as plain JSON-serialisable values."""
    return {
        "base_model_id": BASE_MODEL_ID,
        "base_model_revision": BASE_MODEL_REVISION,
        "torch_dtype": SERVING_TORCH_DTYPE,
        "generation": GENERATION_PARAMETERS,
        "prompt_version": prompt_version,
        "prompt_file": tutor_prompt_path(prompt_version).name,
    }
