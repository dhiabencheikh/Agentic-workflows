"""Leak check: what counts as a leak (definition agreed in CLAUDE.md, M3) and what does not.

Leak = (a) rewriting the student's own line, or (b) giving the corrected function or the fix.
Allowed = quoting the student's code, asking about it, demonstrating a concept on a toy example.
Bug code and fixes below are copied from the benchmark's test bugs (problem_bug).
"""

from eval.leak_checks import _replacement_snippets, check_leak

SEARCH_15_44 = (
    "1. def search(x, seq):\n2.  for i in range(len(seq)):\n3.    if x < seq[i]:\n4.      return i\n5.  return len(seq)",
    "Replace `<` with `<=` on line 3",
)
FACTORIAL_24_29 = (
    "1. def factorial(n):\n2.        if n < 0:\n3.                return 0\n4.        fact = 1\n"
    "5.        for i in range(n):\n6.                fact = fact * i\n7.        return fact",
    "Replace `i` with `(i + 1)` in line 6.\nReplace `range(n)` with `range(1, n + 1)` in line 5.",
)
CLOCKWISE_6_33 = (
    '1. def turn_clockwise(compass_point):\n2.    if compass_point == "N":\n3.        print ("E")\n'
    '4.    elif compass_point == "E":\n5.        print ("S")\n6.    elif compass_point == "S":\n7.        print ("W")\n'
    '8.    elif compass_point == "W":\n9.        print ("N")\n10.    else:\n11.        print ("None")',
    'Replace all the print statements `print ("E")`, `print ("S")`, `print ("W")`, `print ("N")`, `print("None")` '
    'with the return statements `return "E"`, `return "S"`, `return "W"`, `return "N"`, `return "None"` '
    "on lines 3, 5, 7, 9, and 11 respectively.",
)
CLOCKWISE_6_34 = (
    '1. def turn_clockwise(compass_point):\n2.    if compass_point = "N":\n3.        return "E"\n'
    '4.    elif compass_point = "E":\n5.        return "S"\n6.    elif compass_point = "S":\n7.        return "W"\n'
    '8.    elif compass_point = "W":\n9.        return "N"\n10.    else:\n11.        return None',
    "Replace `=` with `==` on lines 2, 4, 6, and 8.",
)
GRADES = (  # shape of 1_10_calculating_a_grade: the fix switches to a name already in the code
    "1. def grade(score):\n2.    rounded = round(score)\n3.    if score >= 90:\n4.        return 'A'",
    "Replace `score` with `rounded` on line 3.",
)


def leak(reply: str, case: tuple) -> bool:
    return check_leak(reply, *case)["is_leak"]


# --- Answer key parsing: only the replacement side is the fix ---

def test_only_the_replacement_side_of_bug_fixes_is_a_fix():
    assert _replacement_snippets(FACTORIAL_24_29[1]) == ["(i + 1)", "range(1, n + 1)"]
    assert _replacement_snippets(SEARCH_15_44[1]) == ["<="]


def test_no_stray_words_become_fix_snippets():
    snippets = _replacement_snippets(CLOCKWISE_6_33[1])
    assert "the" not in snippets and not any(s.startswith("print") for s in snippets)
    assert 'return "E"' in snippets


# --- False alarms found in the review (all on real human tutor replies or their shape) ---

def test_mentioning_the_students_own_code_is_not_a_leak():
    assert not leak("Let's see what happens when `n` is 1. What does `range(n)` do when `n` is 1?", FACTORIAL_24_29)


def test_verbs_need_a_word_boundary():
    assert not leak("Is it because < is strict?", SEARCH_15_44)  # "because" contains "use"
    assert not leak("Can you use the Python shell to check?", CLOCKWISE_6_33)  # "the" is not a fix


def test_a_name_already_in_the_students_code_can_be_mentioned():
    assert not leak("Can you explain the difference between `score` and `rounded`?", GRADES)


# --- Leaks that must still be caught ---

def test_replacement_stated_outright_is_a_leak():
    assert leak("Change `<` to `<=` on line 3.", SEARCH_15_44)
    assert leak("On line 3 you should use <= instead of <.", SEARCH_15_44)
    assert leak("Replace `i` with `(i + 1)` on line 6.", FACTORIAL_24_29)
    assert leak("You need == instead of = in your if conditions.", CLOCKWISE_6_34)
