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
        prompt_version="0.0.0-test",
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


def test_every_example_records_the_prompt_version(splits):
    for example in splits["train"] + splits["validation"] + splits["test"]:
        assert example["prompt_version"] == "0.0.0-test"


def test_bug_description_and_fixes_never_appear_in_the_input(splits):
    for example in splits["train"] + splits["validation"] + splits["test"]:
        text = json.dumps(example["messages"])
        assert "SECRET_DESC" not in text and "SECRET_FIX" not in text
        assert example["bug_fixes"].startswith("SECRET_FIX")


def test_bug_code_and_unit_tests_are_background_fields_only(splits):
    """Both are stored for evaluation. Unit tests never reach the model.
    The buggy code is the student's own code: the student pastes it in the
    first message, and the field is a separate copy for the leak metric."""
    for example in splits["train"] + splits["validation"] + splits["test"]:
        problem = example["problem_id"]
        assert example["unit_tests"] == f"assert f{problem}(1) == {1 + int(problem)}"
        assert example["unit_tests"] not in json.dumps(example["messages"])
        assert example["bug_code"] == f"1. def f{problem}(n):\n2.   return n - {problem}"
        assert example["bug_code"] in example["messages"][1]["content"]
        assert all(example["bug_code"] not in m["content"] for m in example["messages"] if m["role"] == "assistant")


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


def test_code_block_after_a_tutor_line_goes_to_the_next_student_turn(tmp_path):
    """In the dataset, a student's code edit can sit right after a tutor line
    (e.g. train/66_69_last_index_of). It must never become part of a tutor target."""
    outputs = {split: tmp_path / f"{split}.jsonl" for split in ("train", "validation", "test")}
    data_transformation_component.python_func(
        raw_dataset_uri=str(Path(__file__).parent / "fixtures" / "code_after_tutor"),
        system_prompt=SYSTEM_PROMPT,
        prompt_version="0.0.0-test",
        num_validation_problems=1,
        seed=0,
        train_dataset=str(outputs["train"]),
        validation_dataset=str(outputs["validation"]),
        test_dataset=str(outputs["test"]),
    )
    examples = [json.loads(line) for path in outputs.values() for line in path.read_text().splitlines()]
    for example in examples:
        assert "```" not in example["messages"][-1]["content"]
    last = max(examples, key=lambda e: len(e["messages"]))
    student_turn = last["messages"][-2]["content"]
    assert student_turn.startswith("I need to add a -1 step!")
    assert "range(len(array)-1, -1, -1)" in student_turn
    assert last["messages"][-3]["content"] == "What would you need to do in the code to fix that?"


@pytest.mark.parametrize(
    ("problem_id", "should_merge"),
    [("1", True), ("2", False), ("3", False), ("4", False)],
    ids=["backticks-and-comma-merge", "operator-kept", "case-kept", "decimal-point-kept"],
)
def test_near_copies_merge_only_on_formatting_differences(tmp_path, problem_id, should_merge):
    """Each fixture problem has a dialogue and a thread whose student lines differ
    in one way. Their first tutor card is an exact copy; the second card is
    merged only if the difference is formatting (backticks, spacing, end-of-word
    punctuation), never case, operators or a decimal point."""
    outputs = {split: tmp_path / f"{split}.jsonl" for split in ("train", "validation", "test")}
    data_transformation_component.python_func(
        raw_dataset_uri=str(Path(__file__).parent / "fixtures" / "near_copies"),
        system_prompt=SYSTEM_PROMPT,
        prompt_version="0.0.0-test",
        num_validation_problems=0,
        seed=0,
        train_dataset=str(outputs["train"]),
        validation_dataset=str(outputs["validation"]),
        test_dataset=str(outputs["test"]),
    )
    train = [json.loads(line) for line in outputs["train"].read_text().splitlines()]
    cards = [e for e in train if e["problem_id"] == problem_id]
    assert len(cards) == (2 if should_merge else 3)
