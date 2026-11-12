"""The serving contract is complete, JSON-serialisable and points to real files."""

import json

import pytest

from src.constants import BASE_MODEL_ID, BASE_MODEL_REVISION
from src.prompts import TUTOR_PROMPT_VERSION, tutor_prompt_path
from src.serving_contract import GENERATION_PARAMETERS, SERVING_TORCH_DTYPE, build_serving_config


def test_serving_config_has_every_value_the_handler_needs():
    config = build_serving_config()
    assert config == json.loads(json.dumps(config)), "must survive a JSON round trip"
    assert config["base_model_id"] == BASE_MODEL_ID
    assert config["base_model_revision"] == BASE_MODEL_REVISION
    assert config["torch_dtype"] == SERVING_TORCH_DTYPE == "float16"
    assert config["generation"] == GENERATION_PARAMETERS
    assert config["prompt_version"] == TUTOR_PROMPT_VERSION
    assert (tutor_prompt_path().parent / config["prompt_file"]).exists()


def test_decoding_is_greedy_with_a_length_limit_and_stop_tokens():
    assert GENERATION_PARAMETERS["do_sample"] is False
    assert GENERATION_PARAMETERS["max_new_tokens"] == 256
    assert GENERATION_PARAMETERS["eos_token_id"] == [32000, 32001, 32007]


def test_stop_tokens_are_phi3_turn_markers():
    """Needs the tokenizer (transformers, dev dependency): skipped with --no-dev."""
    transformers = pytest.importorskip("transformers")
    tokenizer = transformers.AutoTokenizer.from_pretrained(BASE_MODEL_ID, revision=BASE_MODEL_REVISION)
    expected = [tokenizer.convert_tokens_to_ids(t) for t in ("<|endoftext|>", "<|assistant|>", "<|end|>")]
    assert GENERATION_PARAMETERS["eos_token_id"] == expected
