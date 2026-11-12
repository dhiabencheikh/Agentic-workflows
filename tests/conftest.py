"""Shared test fixtures.

tiny_model_dir: a tiny randomly initialised Phi-3 (same architecture and module
names as Phi-3-mini, 2 layers, hidden size 32) saved with the real Phi-3 tokenizer.
Lets fine-tuning and inference code run on CPU in seconds, without downloading
the 7.64 GB of Phi-3 weights. Its outputs are random text: tests check the code
path and the formats, never quality.
"""

from pathlib import Path

import pytest

from src.constants import BASE_MODEL_ID, BASE_MODEL_REVISION


@pytest.fixture(scope="module")
def tiny_model_dir(tmp_path_factory) -> Path:
    from transformers import AutoTokenizer, Phi3Config, Phi3ForCausalLM

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID, revision=BASE_MODEL_REVISION)
    config = Phi3Config(
        vocab_size=32064,
        hidden_size=32,
        intermediate_size=64,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=4,
        max_position_embeddings=4096,
        pad_token_id=tokenizer.pad_token_id,
    )
    folder = tmp_path_factory.mktemp("tiny-phi3")
    Phi3ForCausalLM(config).save_pretrained(folder)
    tokenizer.save_pretrained(folder)
    return folder
