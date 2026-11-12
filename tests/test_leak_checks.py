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


# --- Function rewrite: a modified copy is a leak, an identical copy is a quote ---

FENCE = "```"


def test_corrected_function_in_a_code_block_is_a_leak():
    reply = (f"Here you go:\n{FENCE}python\ndef search(x, seq):\n    for i in range(len(seq)):\n"
             f"        if x <= seq[i]:\n            return i\n    return len(seq)\n{FENCE}")
    assert check_leak(reply, *SEARCH_15_44)["leak_type"] == "function_rewrite"


def test_quoting_the_students_unchanged_function_is_not_a_leak():
    reply = (f"Look at your code again:\n{FENCE}python\n1. def search(x, seq):\n2.  for i in range(len(seq)):\n"
             f"3.    if x < seq[i]:\n4.      return i\n5.  return len(seq)\n{FENCE}\nWhich line runs when x == seq[i]?")
    assert not leak(reply, SEARCH_15_44)


def test_mentioning_the_function_header_in_prose_is_not_a_leak():
    assert not leak("Your def search(x, seq): header looks fine. What does line 3 compare?", SEARCH_15_44)


# --- Definition (a): rewriting the student's own line ---

TOXIC_10_39 = (  # train bug 10_39_xnglxsh
    '1. def toxNGLXSH(sen):\n2.  vowels = ["a", "e", "i", "o", "u", "A", "E", "I", "O", "U"]\n3.  for i in vowels:\n'
    '4.      if i.islower():\n5.           sen.replace(i, "x")\n6.      else:\n7.           sen.replace(i, "X")\n'
    "8.  sen.swapcase()\n9.  return sen",
    "Replace `sen.swapcase()` with `sen = sen.swapcase()` on line 8 and on lines 5 and 7 change `sen.replace` to `sen = sen.replace`.",
)


def test_rewritten_line_in_a_code_block_is_a_leak():
    reply = f"Line 3 should read:\n{FENCE}python\nif x <= seq[i]:\n{FENCE}"
    assert check_leak(reply, *SEARCH_15_44)["is_leak"]


def test_rewritten_line_in_plain_prose_is_a_leak():
    assert check_leak("Just write if x <= seq[i]: on line 3.", *SEARCH_15_44)["leak_type"] == "line_rewrite"
    assert check_leak("Rewrite line 5 as `for i in range(1, n + 1):`.", *FACTORIAL_24_29)["is_leak"]


def test_quoting_the_students_line_in_a_question_is_not_a_leak():
    assert not leak("Why does `if x < seq[i]:` skip the index where x equals seq[i]?", SEARCH_15_44)


def test_wrapping_the_students_line_in_print_for_debugging_is_not_a_leak():
    reply = 'Have you considered printing the output, for example, `print(sen.replace(i, "x"))`?'
    assert not leak(reply, TOXIC_10_39)


# --- Toy examples (allowed): the 10_39_xnglxsh replies agreed in CLAUDE.md must not be flagged ---

TOY_10_39_REPLIES = [  # real human tutor replies from train bug 10_39_xnglxsh
    'Let\'s open up the Python terminal and try running `sen = "To"` and then `sen.replace("o", "X")`. What do you observe?',
    'Let\'s open up the Python terminal and try running `sen = "English"` and then `sen.swapcase()`. What do you observe?',
    'Good. Now let\'s try running `sen = sen.replace("o", "X")` and then `print(sen)`. What do you observe?',
    "Good. Now let's try running `sen = sen.swapcase()` and then `print(sen)`. What do you observe?",
    'Have you considered printing the output of the method calls to see if they are changing the string, '
    'for example, `print(sen.replace(i, "x"))`?',
]


def test_toy_example_10_39_is_not_a_leak():
    for reply in TOY_10_39_REPLIES:
        assert not leak(reply, TOXIC_10_39), reply


def test_an_experiment_in_the_shell_is_not_a_leak():
    assert not leak("Open the Python shell and type `list(range(1, 4))`. What do you see?", FACTORIAL_24_29)


def test_the_same_fix_given_as_an_instruction_is_still_a_leak():
    assert leak("Change line 8 to `sen = sen.swapcase()` and run your tests again.", TOXIC_10_39)
    assert leak("Replace line 8 with sen = sen.swapcase().", TOXIC_10_39)


def test_a_rewritten_function_is_a_leak_even_inside_an_experiment():
    reply = (f"Try running this in the terminal:\n{FENCE}python\ndef search(x, seq):\n    for i in range(len(seq)):\n"
             f"        if x <= seq[i]:\n            return i\n    return len(seq)\n{FENCE}")
    assert check_leak(reply, *SEARCH_15_44)["leak_type"] == "function_rewrite"


# --- Rules added while tuning on train and validation (each from a real train false alarm or miss) ---

def test_prose_about_a_line_is_not_a_rewrite():
    index_case = ("1. def last(value, array):\n2.    index = -1\n3.    return index", "Replace `-1` with `0` on line 2.")
    assert not leak("Why do we start index at -1?", index_case)  # 66_69 shape: English words, no "="
    assert not leak("What would distinguish that from finding a match at index 0?", index_case)


def test_a_single_keyword_in_a_question_is_the_concept_not_the_fix():
    product = ("1. def Product(a, b):\n2.    a * b", "Add `return` before `a * b`.")
    assert not leak("Do you know where to put `return` in your code?", product)  # 59_60, human reply
    assert leak("Put `return` before `a * b` on line 2.", product)


def test_insert_and_add_phrasings_are_parsed_as_fixes():
    pizza = ("1. def pizza(pizzas, weekend):\n2.    if pizzas <= 20 and not(weekend):\n3.        return True",
             "Insert `pizzas >= 10 and` before `pizzas <= 20 and not(weekend)` in the condition on line 2.")
    assert leak("Insert `pizzas >= 10 and` before the condition on line 2.", pizza)
    assert not leak("What does `pizzas <= 20 and not(weekend)` check?", pizza)
