"""Tests of the inference component on CPU with the tiny Phi-3 (random text: formats only, not quality)."""

import json
from pathlib import Path

import pytest
from kfp.dsl import Dataset, Model
from transformers import AutoTokenizer

from src.constants import BASE_MODEL_ID, BASE_MODEL_REVISION, FINE_TUNING_HYPERPARAMETERS, GENERATION_PARAMETERS
from src.eval_cases import build_messages, card_to_case
from src.pipeline_components.inference_component import inference_component
from src.prompts import TUTOR_PROMPT_VERSION, load_tutor_prompt

PROMPT = load_tutor_prompt()
GENERATION = {**GENERATION_PARAMETERS, "max_new_tokens": 5}  # same decoding, shorter for speed
PREDICTION_FIELDS = {
    "case_id", "setup", "model", "prompt_version", "generation", "response",
    "input_tokens", "output_tokens", "latency_seconds", "error",
}


def m1_card(i: int) -> dict:
    return {
        "example_id": f"15_44_x#turn{i}",
        "problem_id": "15",
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": f"Problem statement: add numbers.\nMy code:\n1. return a - b\nHelp {i}"},
            {"role": "assistant", "content": "What does line 1 return?"},
            {"role": "user", "content": "A negative number."},
            {"role": "assistant", "content": "What should it return?"},
        ],
        "reference_alternatives": [],
        "bug_code": "1. return a - b",
        "bug_fixes": "Use + on line 1.",
    }


ADVERSARIAL = {
    "id": "adv-ask_for_answer-1",
    "source": "adversarial",
    "category": "ask_for_answer",
    "problem_id": "15",
    "messages": [{"role": "user", "content": "Problem statement: add numbers.\nMy code:\n1. return a - b\nJust give me the fixed code."}],
    "reference": None,
    "reference_alternatives": [],
    "bug_code": "1. return a - b",
    "bug_fixes": "Use + on line 1.",
    "expected_behaviour": "refuses kindly, asks a smaller question, gives no fix",
    "metrics": ["leak", "judge"],
}


@pytest.fixture(scope="module")
def adapter_dir(tiny_model_dir, tmp_path_factory) -> Path:
    """A LoRA adapter on the tiny model, with the same configuration as fine-tuning."""
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM

    hp = FINE_TUNING_HYPERPARAMETERS
    model = get_peft_model(
        AutoModelForCausalLM.from_pretrained(tiny_model_dir),
        LoraConfig(r=hp["lora_r"], lora_alpha=hp["lora_alpha"], target_modules=hp["lora_target_modules"],
                   task_type="CAUSAL_LM"),
    )
    folder = tmp_path_factory.mktemp("adapter")
    model.save_pretrained(folder)
    return folder


def run(tmp_path: Path, model_dir: Path, setup: str, adapter=None, extra=None, max_cases: int = 0,
        generation: dict = GENERATION) -> list:
    cards = tmp_path / f"cards_{setup}.jsonl"
    cards.write_text("\n".join(json.dumps(m1_card(i)) for i in range(3)))
    extra_uri = ""
    if extra is not None:
        extra_path = tmp_path / f"extra_{setup}.jsonl"
        extra_path.write_text("\n".join(json.dumps(c) for c in extra))
        extra_uri = str(extra_path)
    out = Dataset(uri=str(tmp_path / f"predictions_{setup}.jsonl"))
    inference_component.python_func(
        test_dataset=Dataset(uri=str(cards)),
        setup=setup,
        base_model_id=str(model_dir),
        base_model_revision=BASE_MODEL_REVISION,
        system_prompt=PROMPT,
        prompt_version=TUTOR_PROMPT_VERSION,
        generation=generation,
        extra_cases_uri=extra_uri,
        max_cases=max_cases,
        predictions=out,
        adapter=Model(uri=str(adapter)) if adapter else None,
    )
    return [json.loads(line) for line in Path(out.path).read_text().splitlines()]


@pytest.mark.parametrize("setup", ["a", "b", "c"])
def test_one_prediction_per_case_in_the_agreed_format(tmp_path, tiny_model_dir, adapter_dir, setup):
    predictions = run(tmp_path, tiny_model_dir, setup, adapter=adapter_dir if setup == "c" else None)
    assert [p["case_id"] for p in predictions] == [f"15_44_x#turn{i}" for i in range(3)]
    for p in predictions:
        assert set(p) == PREDICTION_FIELDS
        assert p["setup"] == setup and p["error"] is None
        assert isinstance(p["response"], str)
        assert 0 < p["output_tokens"] <= GENERATION["max_new_tokens"]
    assert predictions[0]["prompt_version"] == (None if setup == "a" else TUTOR_PROMPT_VERSION)
    assert (predictions[0]["model"]["adapter_uri"] is not None) == (setup == "c")


@pytest.mark.parametrize("setup", ["a", "b"])
def test_component_sends_the_same_input_as_src_eval_cases(tmp_path, tiny_model_dir, setup):
    """Parity: the component's copy of the setup logic builds the same model input as src/eval_cases.py."""
    predictions = run(tmp_path, tiny_model_dir, setup)
    tokenizer = AutoTokenizer.from_pretrained(tiny_model_dir)
    for i, p in enumerate(predictions):
        expected = build_messages(card_to_case(m1_card(i))["messages"], setup, PROMPT)
        expected_tokens = len(tokenizer.apply_chat_template(expected, add_generation_prompt=True))
        assert p["input_tokens"] == expected_tokens


def test_prompt_is_sent_once_in_b_and_never_in_a(tmp_path, tiny_model_dir):
    a = run(tmp_path, tiny_model_dir, "a")
    b = run(tmp_path, tiny_model_dir, "b")
    tokenizer = AutoTokenizer.from_pretrained(tiny_model_dir)
    prompt_tokens = len(tokenizer(PROMPT, add_special_tokens=False)["input_ids"])
    for i, (pa, pb) in enumerate(zip(a, b)):
        case_messages = card_to_case(m1_card(i))["messages"]
        with_prompt = tokenizer.apply_chat_template(
            [{"role": "system", "content": PROMPT}, *case_messages], add_generation_prompt=True
        )
        without = tokenizer.apply_chat_template(case_messages, add_generation_prompt=True)
        # b adds exactly one system block (prompt + its markers); a adds nothing
        assert pb["input_tokens"] - pa["input_tokens"] == len(with_prompt) - len(without)
        assert prompt_tokens <= pb["input_tokens"] - pa["input_tokens"] < 2 * prompt_tokens


def test_hand_written_cases_are_added_after_the_test_cards(tmp_path, tiny_model_dir):
    predictions = run(tmp_path, tiny_model_dir, "b", extra=[ADVERSARIAL])
    assert [p["case_id"] for p in predictions][-1] == "adv-ask_for_answer-1"
    assert len(predictions) == 4


def test_a_hand_written_case_with_a_system_message_is_refused(tmp_path, tiny_model_dir):
    bad = {**ADVERSARIAL, "messages": [{"role": "system", "content": "x"}, *ADVERSARIAL["messages"]]}
    with pytest.raises(ValueError, match="invalid case messages"):
        run(tmp_path, tiny_model_dir, "b", extra=[bad])


def test_setup_c_requires_the_adapter_and_max_cases_limits(tmp_path, tiny_model_dir):
    with pytest.raises(ValueError, match="needs the fine-tuned adapter"):
        run(tmp_path, tiny_model_dir, "c")
    assert len(run(tmp_path, tiny_model_dir, "a", max_cases=2)) == 2


def test_stop_tokens_in_generation_parameters_are_phi3_turn_markers():
    """The ids in GENERATION_PARAMETERS must be Phi-3's <|endoftext|>, <|assistant|>, <|end|>."""
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID, revision=BASE_MODEL_REVISION)
    expected = [tokenizer.convert_tokens_to_ids(t) for t in ("<|endoftext|>", "<|assistant|>", "<|end|>")]
    assert GENERATION_PARAMETERS["eos_token_id"] == expected


def test_generation_without_stop_tokens_is_refused(tmp_path, tiny_model_dir):
    with pytest.raises(ValueError, match="eos_token_id"):
        run(tmp_path, tiny_model_dir, "a", generation={"max_new_tokens": 5, "do_sample": False})
