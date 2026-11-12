"""Unit tests for the data transformation component, run locally on small fixture files.

`python_func` is the plain Python function behind the Kubeflow component,
so it can be called directly without Vertex AI.
"""

import json
from pathlib import Path

import pytest

from src.pipeline_components.data_transformation_component import data_transformation_component

FIXTURES = Path(__file__).parent / "fixtures" / "raw"
SYSTEM_PROMPT = "You are a test tutor."


def run_component(tmp_path: Path, seed: int = 0, num_validation_problems: int = 2) -> dict:
    """Run the component on the fixtures and return the examples of each split."""
    outputs = {split: tmp_path / f"{split}.jsonl" for split in ("train", "validation", "test")}
    data_transformation_component.python_func(
        raw_dataset_uri=str(FIXTURES),
        system_prompt=SYSTEM_PROMPT,
        num_validation_problems=num_validation_problems,
        seed=seed,
        train_dataset=str(outputs["train"]),
        validation_dataset=str(outputs["validation"]),
        test_dataset=str(outputs["test"]),
    )
    return {
        split: [json.loads(line) for line in path.read_text().splitlines()]
        for split, path in outputs.items()
    }


@pytest.fixture
def splits(tmp_path: Path) -> dict:
    return run_component(tmp_path)


def problems(examples: list) -> set:
    return {e["problem_id"] for e in examples}


def test_no_problem_is_shared_between_splits(splits):
    assert problems(splits["train"]).isdisjoint(problems(splits["validation"]))
    assert problems(splits["train"]).isdisjoint(problems(splits["test"]))
    assert problems(splits["validation"]).isdisjoint(problems(splits["test"]))


def test_test_split_is_the_authors_testset_and_validation_has_requested_size(splits):
    assert problems(splits["test"]) == {"9"}
    assert len(problems(splits["validation"])) == 2
    assert problems(splits["train"]) | problems(splits["validation"]) == {"1", "2", "3", "4", "5", "6"}


def test_same_seed_gives_same_split_and_other_seed_can_differ(tmp_path):
    first = run_component(tmp_path / "a", seed=0)
    again = run_component(tmp_path / "b", seed=0)
    assert problems(first["validation"]) == problems(again["validation"])
    seen = {frozenset(problems(run_component(tmp_path / f"s{s}", seed=s)["validation"])) for s in range(10)}
    assert len(seen) > 1


def test_files_with_typos_in_their_type_are_parsed(splits):
    sources = {e["source_file"] for split in splits.values() for e in split}
    assert "3_3_func3_socratic_thread_1.txt" in sources
    assert "9_9_func9_conversational_thead_1.txt" in sources


def test_each_example_is_system_then_alternating_turns_ending_with_tutor(splits):
    for example in splits["train"] + splits["validation"] + splits["test"]:
        roles = [m["role"] for m in example["messages"]]
        assert roles[0] == "system"
        assert example["messages"][0]["content"] == SYSTEM_PROMPT
        assert roles[-1] == "assistant"
        assert all(a != b for a, b in zip(roles[1:], roles[2:])), roles


def test_first_user_message_contains_problem_and_buggy_code(splits):
    example = splits["test"][0]
    first_user = example["messages"][1]["content"]
    assert "Problem statement:" in first_user
    assert "return n - 9" in first_user


def test_bug_description_and_fixes_never_appear_in_the_input(splits):
    for example in splits["train"] + splits["validation"] + splits["test"]:
        text = json.dumps(example["messages"])
        assert "SECRET_DESC" not in text and "SECRET_FIX" not in text
        assert example["bug_fixes"].startswith("SECRET_FIX")


def test_duplicate_openings_from_threads_are_removed(splits):
    # Fixtures: 6 dialogues x 3 tutor turns + 2 threads x 4 tutor turns, 2 duplicated openings.
    assert len(splits["train"]) + len(splits["validation"]) == 6 * 3 + 2 * 4 - 2
    # Testset: 1 dialogue x 3 + 1 thread x 4, 1 duplicated opening.
    assert len(splits["test"]) == 3 + 4 - 1


def test_alternative_replies_are_kept_as_references_not_in_messages(splits):
    first_turn = next(e for e in splits["test"] if e["turn_index"] == 1)
    assert first_turn["reference_alternatives"] == ["Which operator is on line 2?"]
    assert "Which operator" not in json.dumps(first_turn["messages"])


def test_student_code_edits_become_markdown_code_blocks(splits):
    last = max(splits["test"], key=lambda e: len(e["messages"]))
    student_turn = last["messages"][-2]["content"]
    assert "```python" in student_turn and "return n + 9" in student_turn
    assert "<code>" not in student_turn
