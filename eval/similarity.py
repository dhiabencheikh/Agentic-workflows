"""Best-match ROUGE-L similarity between a model reply and the human references (Session 3 slide 16).

Plain Python, no dependencies, so it runs on any laptop and in CI.
Tokenisation follows the reference `rouge-score` library without stemming:
lowercase, then sequences of letters and digits.
"""

import re

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list:
    return _TOKEN.findall(text.lower())


def lcs_length(a: list, b: list) -> int:
    """Length of the longest common subsequence: same order, not necessarily adjacent.

    Dynamic programming over two rows: previous[j] = LCS of a[:i-1] and b[:j].
    """
    if not a or not b:
        return 0
    previous = [0] * (len(b) + 1)
    for token_a in a:
        current = [0]
        for j, token_b in enumerate(b, start=1):
            current.append(previous[j - 1] + 1 if token_a == token_b else max(previous[j], current[j - 1]))
        previous = current
    return previous[-1]


def rouge_l(candidate: str, reference: str) -> dict:
    """ROUGE-L precision, recall and F1 of a candidate against one reference."""
    cand, ref = tokenize(candidate), tokenize(reference)
    lcs = lcs_length(cand, ref)
    if lcs == 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    precision, recall = lcs / len(cand), lcs / len(ref)
    return {"precision": precision, "recall": recall, "f1": 2 * precision * recall / (precision + recall)}


def best_match_rouge_l(response: str, reference: str, alternatives: list) -> dict:
    """Highest ROUGE-L F1 of the response against the reference and each alternative.

    Several tutor questions can be equally good: a reply is not penalised for
    matching an alternative instead of the reference.
    Returns the best scores and which reference matched ("reference" or "alternative_<i>").
    """
    candidates = [("reference", reference)] + [(f"alternative_{i}", alt) for i, alt in enumerate(alternatives)]
    best = None
    for name, text in candidates:
        score = rouge_l(response, text)
        if best is None or score["f1"] > best["f1"]:
            best = {**score, "matched": name}
    return best
