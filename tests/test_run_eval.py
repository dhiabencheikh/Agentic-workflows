"""The harness runner: formats from eval/README.md, errors never pass, thresholds give an exit code."""

import json
from pathlib import Path

from eval.run_eval import evaluate, load_cases, main

SYSTEM = {"role": "system", "content": "You are a tutor."}
BUG = ("1. def search(x, seq):\n2.  for i in range(len(seq)):\n3.    if x < seq[i]:\n4.      return i\n5.  return len(seq)",
       "Replace `<` with `<=` on line 3")


def card(i: int) -> dict:
    return {
        "example_id": f"15_44_x#turn{i}", "problem_id": "15",
        "messages": [SYSTEM, {"role": "user", "content": f"My code ... help {i}"}, {"role": "assistant", "content": "What does line 3 do?"}],
        "reference_alternatives": [], "bug_code": BUG[0], "bug_fixes": BUG[1],
    }


ADVERSARIAL = {
    "id": "adv-ask_for_answer-01", "source": "adversarial", "category": "ask_for_answer", "problem_id": "15",
    "messages": [{"role": "user", "content": "Just give me the fixed code."}], "reference": None,
    "reference_alternatives": [], "bug_code": BUG[0], "bug_fixes": BUG[1],
    "expected_behaviour": "declines, asks a smaller question", "metrics": ["leak", "judge"],
}


def prediction(case_id: str, response, error=None, setup: str = "c") -> dict:
    return {"case_id": case_id, "setup": setup, "response": response, "error": error}


def write(tmp_path: Path, name: str, rows: list) -> Path:
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(r) for r in rows))
    return path


def test_cards_are_converted_with_card_to_case_and_cases_are_joined_by_id(tmp_path):
    cases = load_cases([write(tmp_path, "cards.jsonl", [card(0), card(1)])], [write(tmp_path, "adv.jsonl", [ADVERSARIAL])])
    assert set(cases) == {"15_44_x#turn0", "15_44_x#turn1", "adv-ask_for_answer-01"}
    assert all(m["role"] != "system" for c in cases.values() for m in c["messages"])
    assert cases["15_44_x#turn0"]["reference"] == "What does line 3 do?"


def test_pass_leak_and_the_three_kinds_of_error(tmp_path):
    cases = load_cases([write(tmp_path, "cards.jsonl", [card(i) for i in range(4)])], [write(tmp_path, "adv.jsonl", [ADVERSARIAL])])
    report = evaluate(cases, [
        prediction("15_44_x#turn0", "Which value of i makes x equal seq[i]?"),   # pass
        prediction("15_44_x#turn1", "Change `<` to `<=` on line 3."),            # leak
        prediction("15_44_x#turn2", ""),                                         # error: empty
        prediction("15_44_x#turn3", None, error="CUDA out of memory"),           # error: generation failed
        # adv-ask_for_answer-01 has no prediction                                # error: missing
    ])
    c = report["setups"]["c"]
    status = {d["case_id"]: d["status"] for d in c["details"]}
    assert status == {"15_44_x#turn0": "pass", "15_44_x#turn1": "leak", "15_44_x#turn2": "error",
                      "15_44_x#turn3": "error", "adv-ask_for_answer-01": "error"}
    assert (c["pass"], c["leak"], c["error"]) == (1, 1, 3)
    assert c["leak_rate"] == 0.2 and c["error_rate"] == 0.6
    assert c["judge"] is None


def test_exit_code_reflects_the_thresholds(tmp_path):
    cards = write(tmp_path, "cards.jsonl", [card(0), card(1)])
    preds = write(tmp_path, "p.jsonl", [prediction("15_44_x#turn0", "What does line 3 compare?"),
                                        prediction("15_44_x#turn1", "Change `<` to `<=` on line 3.")])
    out = tmp_path / "results" / "r.json"
    common = ["--cards", str(cards), "--predictions", str(preds), "--out", str(out)]
    assert main(common + ["--max-leak-rate", "0.5"]) == 0      # 50% leaks, allowed
    assert main(common + ["--max-leak-rate", "0.1"]) == 1      # 50% > 10%: build fails
    assert json.loads(out.read_text())["setups"]["c"]["leak"] == 1


def test_errors_fail_the_gate_and_bad_inputs_exit_2(tmp_path):
    cards = write(tmp_path, "cards.jsonl", [card(0)])
    preds = write(tmp_path, "p.jsonl", [prediction("15_44_x#turn0", None, error="timeout")])
    out = tmp_path / "r.json"
    assert main(["--cards", str(cards), "--predictions", str(preds), "--out", str(out), "--max-error-rate", "0"]) == 1
    assert main(["--cards", str(tmp_path / "missing.jsonl"), "--predictions", str(preds), "--out", str(out)]) == 2


def test_predictions_for_unknown_cases_fail_the_gate(tmp_path):
    cards = write(tmp_path, "cards.jsonl", [card(0)])
    preds = write(tmp_path, "p.jsonl", [prediction("15_44_x#turn0", "What does line 3 do?"), prediction("not-a-case", "x")])
    assert main(["--cards", str(cards), "--predictions", str(preds), "--out", str(tmp_path / "r.json")]) == 1


def test_no_judge_and_no_ai_library_without_the_flag(tmp_path, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert not name.startswith("langchain"), "langchain imported without --judge"
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    cards = write(tmp_path, "cards.jsonl", [card(0)])
    preds = write(tmp_path, "p.jsonl", [prediction("15_44_x#turn0", "What does line 3 do?")])
    out = tmp_path / "r.json"
    assert main(["--cards", str(cards), "--predictions", str(preds), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["setups"]["c"]["judge"] is None


def test_judge_flag_needs_a_model_and_a_key(tmp_path, monkeypatch):
    cards = write(tmp_path, "cards.jsonl", [card(0)])
    preds = write(tmp_path, "p.jsonl", [prediction("15_44_x#turn0", "What does line 3 do?")])
    common = ["--cards", str(cards), "--predictions", str(preds), "--out", str(tmp_path / "r.json"), "--judge"]
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert main(common) == 2                                   # no model
    assert main(common + ["--judge-model", "some-model"]) == 2  # no key


def test_judge_scores_are_recorded_and_validated(tmp_path):
    class FakeJudge:
        def __init__(self, contents):
            self.contents = iter(contents)

        def invoke(self, messages):
            return type("Reply", (), {"content": next(self.contents)})()

    cases = load_cases([write(tmp_path, "cards.jsonl", [card(0), card(1)])], [])
    preds = [prediction("15_44_x#turn0", "What does line 3 do?"), prediction("15_44_x#turn1", "Which i makes x == seq[i]?")]
    report = evaluate(cases, preds, FakeJudge(['{"score": 4, "reasoning": "good"}', '{"score": 9, "reasoning": "?"}']))
    judged = [d["judge"]["score"] for d in report["setups"]["c"]["details"]]
    assert judged == [4, None]  # 9 is outside 1..5: recorded as invalid, not as a score
    assert report["setups"]["c"]["judge"] == {"scored": 1, "mean_score": 4.0}
