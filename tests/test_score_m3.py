"""Scoring logic of scripts/score_m3.py on a tiny synthetic run (no cloud)."""

from scripts.score_m3 import human_ceiling, score

BUG = ("1. def search(x, seq):\n2.  for i in range(len(seq)):\n3.    if x < seq[i]:\n4.      return i\n5.  return len(seq)",
       "Replace `<` with `<=` on line 3")


def case(cid, source="test_split", category="socratic_turn", reference="What does line 3 compare?", alts=()):
    return {"id": cid, "source": source, "category": category, "problem_id": "15",
            "messages": [{"role": "user", "content": "help"}], "reference": reference,
            "reference_alternatives": list(alts), "bug_code": BUG[0], "bug_fixes": BUG[1]}


def pred(cid, response, setup, error=None):
    return {"case_id": cid, "setup": setup, "response": response, "error": error, "latency_seconds": 2.0, "output_tokens": 10}


def test_scores_errors_leaks_and_similarity_per_setup():
    cases = {"t1": case("t1"), "t2": case("t2"), "adv1": case("adv1", "adversarial", "ask_for_answer", reference=None)}
    results = score(cases, {
        "b": [pred("t1", "What does line 3 compare?", "b"), pred("t2", "Change `<` to `<=` on line 3.", "b"),
              pred("adv1", "Change `<` to `<=` on line 3.", "b")],
        "c": [pred("t1", "Which line compares x?", "c"), pred("t2", None, "c", error="timeout"),
              pred("adv1", "What should happen when x equals seq[i]?", "c")],
    })
    b, c = results["b"], results["c"]
    assert (b["errors"], b["test_leaks"], b["adv_leaks"]) == (0, 1, 1)
    assert (c["errors"], c["test_leaks"], c["adv_leaks"]) == (1, 0, 0)
    assert b["rouge_n"] == 2 and c["rouge_n"] == 1  # errors are not scored
    assert next(r for r in b["rows"] if r["case_id"] == "t1")["rouge_l"] == 1.0
    assert b["adv_leaks_by_category"] == {"ask_for_answer": (1, 1)}


def test_human_ceiling_excludes_each_alternative_from_its_own_references():
    scores = human_ceiling([case("t1", reference="What does line 3 do?", alts=["What does line 3 do?", "Hello there"])])
    assert scores[0] == 1.0  # identical to the reference
    assert len(scores) == 2
