"""Replay mode shows the recorded M3 replies verbatim and says so."""

import csv
from pathlib import Path

from src.app.replay import banner, load_replay, menu, render

ROOT = Path(__file__).resolve().parents[1]


def test_four_scenarios_including_one_adversarial():
    data = load_replay()
    assert len(data["scenarios"]) == 4
    assert [s["category"] for s in data["scenarios"]].count("ask_for_answer") == 1


def test_replies_are_the_recorded_ones_verbatim():
    data = load_replay()
    rows = {(r["setup"], r["case_id"]): r["response"] for r in csv.DictReader(open(ROOT / "docs/results/m3_eval_cases.csv", encoding="utf-8"))}
    for s in data["scenarios"]:
        for setup in ("c", "b"):
            assert s["replies"][setup]["response"] == rows[(setup, s["case_id"])]


def test_the_ui_states_it_is_replaying_recorded_outputs():
    data = load_replay()
    assert "REPLAY MODE" in banner(data) and "not live" in banner(data)
    text = render(data, "4")
    assert "recorded, not live" in text and data["scenarios"][3]["replies"]["c"]["response"] in text


def test_no_system_prompt_is_shown_and_bad_input_shows_the_menu():
    data = load_replay()
    assert all(m["role"] != "system" for s in data["scenarios"] for m in s["messages"])
    assert render(data, "9").startswith("Please type a number") and menu(data) in render(data, "x")


def test_replay_module_never_imports_the_live_client():
    source = (ROOT / "src/app/replay.py").read_text()
    assert "endpoint_client" not in source and "aiplatform" not in source
