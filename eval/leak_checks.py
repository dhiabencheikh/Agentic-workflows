"""
Leak check evaluation module.

Detects when an assistant tutor reply leaks solutions:
1. Re-writing the student's buggy lines or defining the target function.
2. Directly revealing the fix described in bug_fixes.
3. Allows toy examples on unrelated variables or dummy functions.
"""

from __future__ import annotations

import difflib
import re
from typing import TypedDict

# Rewritten-line detection (definition (a)). Starting values from the review prototype;
# tuned on train and validation only (scripts/calibrate_leak_check.py), then frozen.
REWRITE_SIMILARITY = 0.75  # difflib ratio between a reply passage and a student line
MIN_LINE_TOKENS = 4  # shorter student lines (e.g. "else :") are too generic to compare


class LeakResult(TypedDict):
    is_leak: bool
    leak_type: str | None
    reason: str | None


def _clean_bug_code(bug_code: str) -> list[str]:
    cleaned = []
    for line in bug_code.strip().splitlines():
        line = line.strip()
        line = re.sub(r"^\d+\.\s*", "", line)
        if line:
            cleaned.append(line)
    return cleaned


def _extract_function_names(bug_code: str) -> list[str]:
    """Extract all def function_name from bug_code, stripping line numbers first."""
    names = []
    for raw_line in bug_code.splitlines():
        line = re.sub(r"^\d+\.\s*", "", raw_line.strip())
        match = re.search(r"\bdef\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", line)
        if match:
            names.append(match.group(1))
    return names


CODE_TOKEN = re.compile(r"\w+|==|<=|>=|!=|\*\*|//|[^\w\s]")


def _code_tokens(text: str) -> list[str]:
    return CODE_TOKEN.findall(text)


def _normalized_line(line: str) -> str:
    """A code line without its line number, compared token by token (spacing ignored)."""
    return " ".join(_code_tokens(re.sub(r"^\s*\d+\.\s?", "", line)))


def _extract_code_blocks(text: str) -> list[str]:
    blocks = re.findall(r"```(?:python|py)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    return [b.strip() for b in blocks if b.strip()]


def _is_toy_example(block: str, bug_code: str) -> bool:
    """Returns True if the block is a toy example, not the student's code."""
    fn_names = _extract_function_names(bug_code)
    for fn in fn_names:
        if re.search(rf"\bdef\s+{re.escape(fn)}\b", block):
            return False

    buggy_lines = _clean_bug_code(bug_code)
    match_count = 0
    for bl in buggy_lines:
        if bl in block:
            match_count += 1
    return match_count <= 1


def _replacement_snippets(bug_fixes: str) -> list[str]:
    """The NEW code in bug_fixes: what comes after "with" or "to".

    "Replace `range(n)` with `range(1, n + 1)`" gives ["range(1, n + 1)"]: the old side
    (`range(n)`) is the student's own code, and mentioning it is not a leak.
    Fenced code after "with"/"to" (e.g. "Replace line 4 with the following lines: ```py ...```")
    gives one snippet per code line.
    """
    snippets: list[str] = []
    fenced_after_keyword = r"\b(?:with|to)\b[^`]*?```(?:py|python)?\s*\n?(.*?)```"
    for match in re.finditer(fenced_after_keyword, bug_fixes, re.DOTALL | re.IGNORECASE):
        snippets += [line.strip() for line in match.group(1).splitlines() if line.strip()]
    text = re.sub(r"```.*?```", " ", bug_fixes, flags=re.DOTALL)
    for clause in re.split(r"(?<=[.;])\s+|\n", text):
        keyword = re.search(r"\b(?:with|to)\b", clause, re.IGNORECASE)
        if keyword:
            snippets += [s.strip() for s in re.findall(r"`([^`]+)`", clause[keyword.end():])]
    return list(dict.fromkeys(s for s in snippets if s))


def _new_fix_snippets(bug_fixes: str, bug_code: str) -> list[str]:
    """Replacement snippets that are not already in the student's code.

    A name that already exists in the code (e.g. a variable the fix switches to) can be
    mentioned in a question without giving the fix away.
    """
    student_code = " ".join(_clean_bug_code(bug_code))
    return [s for s in _replacement_snippets(bug_fixes) if s not in student_code]


def _directive_patterns(escaped_fix: str) -> list[str]:
    """Phrasings that state a fix outright. Every verb has a word boundary ("because" is not "use")."""
    verbs = r"\b(?:change|replace|switch|convert|rewrite)\b"
    return [
        rf"{verbs}[^\n.]*?\b(?:to|with)\s+[`'\"]?{escaped_fix}",
        rf"\b(?:should be|ought to be|needs to be|must be|should read)\s+[`'\"]?{escaped_fix}",
        rf"\b(?:use|write|add|insert|put)\s+[`'\"]?{escaped_fix}",
        rf"{escaped_fix}[`'\"]?\s+instead\s+of\b",
    ]


def _mask_exact_quotes(tokens: list[str], student_lines: list[list[str]]) -> list[str]:
    """Blank out every passage that is an exact copy of a student line: those are quotes.

    Without this, a quote of one line ('sen.replace(i, "x")') would look like a rewrite of a
    similar line ('sen.replace(i, "X")').
    """
    masked = list(tokens)
    for target in sorted(student_lines, key=len, reverse=True):
        n = len(target)
        for i in range(len(masked) - n + 1):
            if masked[i:i + n] == target:
                masked[i:i + n] = ["\x00"] * n
    return masked


def _rewritten_student_line(reply: str, bug_code: str) -> tuple[str, str] | None:
    """A passage of the reply that is a near-copy of a student line with a small change.

    Exact copies of student lines are quotes (in a question, or inside print(...) for
    debugging) and are masked first. Returns (student line, reply passage) or None.
    """
    lines = _clean_bug_code(bug_code)
    line_tokens = [_code_tokens(line) for line in lines]
    reply_tokens = _mask_exact_quotes(_code_tokens(reply), [t for t in line_tokens if len(t) >= 2])
    for line, target in zip(lines, line_tokens):
        if len(target) < MIN_LINE_TOKENS:
            continue
        n = len(target)
        for size in range(max(n - 1, 1), n + 3):
            for start in range(len(reply_tokens) - size + 1):
                window = reply_tokens[start:start + size]
                if window[0] != target[0] or "\x00" in window:
                    continue
                if difflib.SequenceMatcher(None, window, target).ratio() >= REWRITE_SIMILARITY:
                    return line, " ".join(window)
    return None


def check_leak(reply: str, bug_code: str, bug_fixes: str) -> LeakResult:
    """
    Check if the assistant reply leaks the solution.
    """
    code_blocks = _extract_code_blocks(reply)
    fn_names = _extract_function_names(bug_code)

    # 1. Function rewrite: a code block defining the student's function with at least one
    #    changed line. An identical copy of the student's code is a quote, not a leak.
    student_lines = {_normalized_line(line) for line in bug_code.splitlines() if _normalized_line(line)}
    for fn in fn_names:
        fn_pattern = rf"\bdef\s+{re.escape(fn)}\s*\("
        for block in code_blocks:
            if not re.search(fn_pattern, block):
                continue
            changed = [
                line.strip() for line in block.splitlines()
                if _normalized_line(line) and _normalized_line(line) not in student_lines
            ]
            if changed:
                return {
                    "is_leak": True,
                    "leak_type": "function_rewrite",
                    "reason": f"Assistant wrote a modified version of '{fn}' (e.g. '{changed[0]}').",
                }

    # 2. Rewritten student line (definition (a)): a near-copy of one of the student's lines
    rewrite = _rewritten_student_line(reply, bug_code)
    if rewrite:
        return {
            "is_leak": True,
            "leak_type": "line_rewrite",
            "reason": f"Assistant rewrote the student's line '{rewrite[0]}' as '{rewrite[1]}'.",
        }

    # 3. Explicit fix leak: only NEW code from the answer key counts (see _new_fix_snippets)
    for fix in _new_fix_snippets(bug_fixes, bug_code):
        escaped = re.escape(fix)
        for pat in _directive_patterns(escaped):
            if re.search(pat, reply, re.IGNORECASE):
                return {
                    "is_leak": True,
                    "leak_type": "explicit_fix",
                    "reason": f"Assistant explicitly gave the fix instruction '{fix}'.",
                }

        # Substantial code phrases (> 5 chars) copied into the reply, outside toy examples
        if len(fix) > 5 and fix in reply:
            is_in_toy = any(fix in block and _is_toy_example(block, bug_code) for block in code_blocks)
            if not is_in_toy:
                return {
                    "is_leak": True,
                    "leak_type": "explicit_fix",
                    "reason": f"Assistant included the fix snippet '{fix}'.",
                }

    return {"is_leak": False, "leak_type": None, "reason": None}
