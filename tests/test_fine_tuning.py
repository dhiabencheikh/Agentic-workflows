"""Local tests of the fine-tuning component, on CPU, without any GPU or download of Phi-3 weights.

A tiny randomly initialised Phi-3 (same architecture and module names, 2 layers)
is built from a config and saved with the real Phi-3 tokenizer, so the whole code
path (data loading, compression, LoRA, completion-only loss, evaluation, saving)
runs in seconds. Quantization is switched off: bitsandbytes needs a GPU.
"""

import json
from pathlib import Path

import pytest
from kfp.dsl import Dataset, Metrics, Model
from transformers import AutoTokenizer, Phi3Config, Phi3ForCausalLM

from src.constants import BASE_MODEL_ID, BASE_MODEL_REVISION, FINE_TUNING_HYPERPARAMETERS
from src.pipeline_components.fine_tuning_component import fine_tuning_component

SYSTEM = {"role": "system", "content": "You are a test tutor."}


def card(card_id: str, middle_turns: int = 0) -> dict:
    """A card: system, first student message, optional middle exchanges, last student turn, target."""
    messages = [SYSTEM, {"role": "user", "content": "Problem statement: add two numbers.\nMy code:\n1. return a - b"}]
    for i in range(middle_turns):
        messages += [
            {"role": "assistant", "content": f"Middle tutor question number {i} about line 1 and its operator?"},
            {"role": "user", "content": f"Middle student answer number {i}, I am still not sure what is wrong."},
        ]
    messages += [
        {"role": "assistant", "content": "What does line 1 return for 1 and 2?"},
        {"role": "user", "content": "It returns -1."},
        {"role": "assistant", "content": "What should it return instead?"},
    ]
    return {"example_id": card_id, "problem_id": "1", "messages": messages, "prompt_version": "0.0.0-test"}


@pytest.fixture(scope="module")
def tiny_model_dir(tmp_path_factory) -> Path:
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


def run(tmp_path: Path, model_dir: Path, train_cards: list, max_seq_length: int = 2304, max_steps: int = 2) -> dict:
    for name, cards in (("train.jsonl", train_cards), ("validation.jsonl", [card("v1"), card("v2")])):
        (tmp_path / name).write_text("\n".join(json.dumps(c) for c in cards))
    hp = {
        **FINE_TUNING_HYPERPARAMETERS,
        "per_device_train_batch_size": 1,
        "per_device_eval_batch_size": 1,
        "gradient_accumulation_steps": 1,
        "eval_steps": 1,
        "logging_steps": 1,
        "max_seq_length": max_seq_length,
    }
    model = Model(uri=str(tmp_path / "model"))
    metrics = Metrics(uri=str(tmp_path / "metrics"))
    fine_tuning_component.python_func(
        train_dataset=Dataset(uri=str(tmp_path / "train.jsonl")),
        validation_dataset=Dataset(uri=str(tmp_path / "validation.jsonl")),
        base_model_id=str(model_dir),
        base_model_revision=BASE_MODEL_REVISION,
        hyperparameters=hp,
        use_quantization=False,
        max_steps=max_steps,
        max_train_cards=0,
        model=model,
        metrics=metrics,
    )
    return {
        "model_dir": Path(model.path),
        "metrics_dir": Path(metrics.path),
        "info": json.loads((Path(model.path) / "training_info.json").read_text()),
        "metrics": metrics.metadata,
    }


def test_training_runs_and_saves_adapter_tokenizer_and_record(tmp_path, tiny_model_dir):
    out = run(tmp_path, tiny_model_dir, [card("t1"), card("t2"), card("t3")])
    files = {p.name for p in out["model_dir"].iterdir()}
    assert {"adapter_config.json", "adapter_model.safetensors", "tokenizer_config.json", "training_info.json"} <= files
    adapter = json.loads((out["model_dir"] / "adapter_config.json").read_text())
    assert adapter["r"] == FINE_TUNING_HYPERPARAMETERS["lora_r"]
    assert set(adapter["target_modules"]) == set(FINE_TUNING_HYPERPARAMETERS["lora_target_modules"])
    info = out["info"]
    assert info["global_steps"] == 2
    assert info["train_cards"] == 3 and info["validation_cards"] == 2
    assert info["prompt_versions"] == ["0.0.0-test"]
    assert info["hyperparameters"]["learning_rate"] == FINE_TUNING_HYPERPARAMETERS["learning_rate"]
    assert len(info["eval_history"]) >= 1


def test_only_lora_parameters_are_trained(tmp_path, tiny_model_dir):
    info = run(tmp_path, tiny_model_dir, [card("t1")], max_steps=1)["info"]
    # LoRA adds r x (in + out) per targeted matrix: far fewer than the model's parameters.
    assert 0 < info["trainable_parameters"] < 0.2 * 32064 * 32


def test_metrics_and_tensorboard_logs_are_written(tmp_path, tiny_model_dir):
    out = run(tmp_path, tiny_model_dir, [card("t1"), card("t2")])
    assert "best_eval_loss" in out["metrics"] and "lora_r" in out["metrics"]
    assert list(out["metrics_dir"].rglob("events.out.tfevents.*")), "no TensorBoard event file"


def test_long_cards_are_compressed_in_the_middle_never_at_the_ends(tmp_path, tiny_model_dir):
    tokenizer = AutoTokenizer.from_pretrained(tiny_model_dir)
    long_card = card("long", middle_turns=6)
    full = len(tokenizer.apply_chat_template(long_card["messages"], tokenize=True))
    shortest = len(tokenizer.apply_chat_template(card("short")["messages"], tokenize=True))
    limit = (full + shortest) // 2  # forces dropping some, not all, middle exchanges
    info = run(tmp_path, tiny_model_dir, [long_card, card("short")], max_seq_length=limit, max_steps=1)["info"]
    assert info["cards_compressed"] == 1
    assert info["cards_dropped"] == 0


def test_a_card_that_cannot_fit_even_compressed_is_dropped_and_counted(tmp_path, tiny_model_dir):
    tokenizer = AutoTokenizer.from_pretrained(tiny_model_dir)
    normal = card("normal")
    limit = len(tokenizer.apply_chat_template(normal["messages"], tokenize=True)) + 5
    huge = card("huge")
    huge["messages"][1] = {"role": "user", "content": huge["messages"][1]["content"] * 50}  # problem too long
    info = run(tmp_path, tiny_model_dir, [normal, huge], max_seq_length=limit, max_steps=1)["info"]
    assert info["cards_dropped"] == 1
    assert info["train_cards"] == 1


def test_clear_error_when_no_card_fits(tmp_path, tiny_model_dir):
    with pytest.raises(ValueError, match="No cards left after fitting"):
        run(tmp_path, tiny_model_dir, [card("t1")], max_seq_length=20, max_steps=1)
