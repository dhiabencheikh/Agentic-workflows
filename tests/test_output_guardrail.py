"""Output guardrail: a reply that rewrites the student's code is replaced; normal tutoring passes."""

from src.output_guardrail import SAFE_REPLY, check_reply, student_code

FENCE = "```"
FIRST = {"role": "user", "content": f"Problem statement: factorial.\nMy code:\n{FENCE}python\n1. def factorial(n):\n"
                                    f"2.     fact = 1\n3.     for i in range(n):\n4.         fact = fact * i\n5.     return fact\n{FENCE}\nIt returns 0."}
HISTORY = [FIRST]


def test_student_code_comes_from_the_first_message():
    assert "for i in range(n):" in student_code(HISTORY)
    assert student_code([{"role": "user", "content": "no code here"}]) == ""


def test_a_corrected_function_is_blocked():
    reply = f"Here:\n{FENCE}python\ndef factorial(n):\n    fact = 1\n    for i in range(1, n + 1):\n        fact = fact * i\n    return fact\n{FENCE}"
    assert check_reply(reply, HISTORY)["blocked"]


def test_a_rewritten_line_is_blocked():
    assert check_reply("Line 3 should be `for i in range(1, n + 1):`.", HISTORY)["blocked"]


def test_socratic_questions_and_quotes_pass():
    assert not check_reply("What is the first value of i in your loop?", HISTORY)["blocked"]
    assert not check_reply("What does `for i in range(n):` produce when n is 3?", HISTORY)["blocked"]


def test_no_code_in_the_conversation_means_no_block():
    assert not check_reply("Anything", [{"role": "user", "content": "hello"}])["blocked"]
    assert SAFE_REPLY.endswith("?") and FENCE not in SAFE_REPLY
