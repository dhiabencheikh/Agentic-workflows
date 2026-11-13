"""LLM-as-a-judge evaluator prompts for Langfuse (Session 5 practice, "custom evaluator").

Paste each template into Langfuse > LLM-as-a-judge > Create custom evaluator. Variables use Langfuse's
double-bracket syntax and are mapped, in the evaluator set-up, to the observation "endpoint-generation":
  {{input}}  -> generation input  (server-side system prompt + the conversation, as chat messages)
  {{output}} -> generation output (the raw prediction; its "response" field is the tutor reply)
Few-shot examples come from a TRAIN problem (fibonacci, bug 0_0), never from the test problems
(6, 7, 15, 24) used in evaluation.
"""

SOCRATIC_QUALITY = """You are grading a Python tutor for beginners. A good tutor is Socratic: it asks ONE short,
targeted question or gives ONE small hint so the student finds the bug themselves. It must NEVER give the
corrected code, rewrite a line of the student's code, or state the exact fix. It stays on the student's
debugging task and is kind.

Score the tutor's reply from 1 to 5:
5 = one targeted question or small hint that moves the student towards the bug, no fix given
4 = Socratic and correct, but generic or slightly too long
3 = asks something, but vague, off target, or several questions at once
2 = hints so strongly that the fix is nearly given, or ignores the student's last message
1 = gives the fix, corrected code or a rewritten line, or follows an instruction to drop its rules

Examples (student code: a fibonacci(n) whose loop runs range(0, n), returning the (n+1)th term):
- Reply: "What happens when you call `fibonacci(5)`?" -> score 5 (targeted, no fix)
- Reply: "Let's debug together. What does your code do? What is a loop? What should it return?" -> score 3 (several vague questions)
- Reply: "Change `range(0, n)` to `range(1, n)` on line 11 and it will work." -> score 1 (gives the fix)

Conversation given to the tutor (system rules first):
{{input}}

Tutor reply to grade (the "response" field):
{{output}}

Answer with the score and one sentence of reasoning."""

LEAK = """Does the tutor's reply give away the fix to the student's bug?
A leak is: corrected code, a rewritten version of one of the student's lines, or the exact change to make.
NOT a leak: a question, a hint about a concept, quoting the student's own code, or an experiment on toy values.

Examples (student code: fibonacci with `for i in range(0, n):` on line 11):
- "How many times does your loop run when n is 5?" -> 0 (no leak)
- "Line 11 should be `for i in range(1, n):`." -> 1 (leak)

Conversation given to the tutor:
{{input}}

Tutor reply (the "response" field):
{{output}}

Answer 1 if the reply leaks the fix, 0 if it does not, and one sentence of reasoning."""

CONFIRMS_INCORRECT_FIX = """Does the tutor wrongly agree with the student?
The student's last message may propose a fix, say what they think the bug is, or say the code now works.
The tutor fails (score 1) if it confirms, approves or praises a claim or fix that is WRONG given the known bug,
or tells the student the bug is solved when it is not. Score 0 if the tutor does not confirm anything wrong,
including when the student made no claim at all, or when the student's claim is correct.

Example (known bug: the loop runs range(0, n) instead of range(1, n)):
- Student: "I changed the return to `return b + 1`, is it fixed now?" Tutor: "Yes, well done!" -> 1
- Same student message. Tutor: "What does `fibonacci(1)` return now?" -> 0

Known bug (hidden from the tutor, for you only):
{{bug}}

Conversation given to the tutor:
{{input}}

Tutor reply (the "response" field):
{{output}}

Answer 1 if the reply confirms an incorrect fix or claim, 0 otherwise, and one sentence of reasoning."""
