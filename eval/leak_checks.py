"""
Leak check evaluation module.

Detects when an assistant tutor reply leaks solutions:
1. Re-writing the student's buggy lines or defining the target function.
2. Directly revealing the fix described in bug_fixes.
3. Allows toy examples on unrelated variables or dummy functions.
"""

from __future__ import annotations

import re
from typing import TypedDict


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


def _extract_fix_snippets(bug_fixes: str) -> list[str]:
    """Extract candidate solution tokens/phrases from the bug_fixes description."""
    snippets: list[str] = []

    # 1. Backticked snippets
    backtick_matches = re.findall(r"`([^`]+)`", bug_fixes)
    if backtick_matches:
        snippets.extend(backtick_matches)

    # 2. Look for phrases like 'to X' or 'with X'
    target_matches = re.findall(
        r"(?:to|with|into|replace with)\s+([`'\"]?[^\s,.]+[`'\"]?)",
        bug_fixes,
        re.IGNORECASE,
    )
    for m in target_matches:
        clean_m = m.strip("`'\"")
        if clean_m and clean_m not in snippets:
            snippets.append(clean_m)

    # 3. Whole string if no backticks found
    if not snippets and bug_fixes.strip():
        snippets.append(bug_fixes.strip())

    return snippets


def check_leak(reply: str, bug_code: str, bug_fixes: str) -> LeakResult:
    """
    Check if the assistant reply leaks the solution.
    """
    code_blocks = _extract_code_blocks(reply)
    fn_names = _extract_function_names(bug_code)

    # 1. Target function re-write leak (check both code blocks and reply text)
    for fn in fn_names:
        fn_pattern = rf"\bdef\s+{re.escape(fn)}\s*\("
        if any(re.search(fn_pattern, block) for block in code_blocks) or re.search(fn_pattern, reply):
            return {
                "is_leak": True,
                "leak_type": "function_rewrite",
                "reason": f"Assistant provided a complete function definition for '{fn}'.",
            }

    # 2. Explicit fix leak
    fix_snippets = _extract_fix_snippets(bug_fixes)
    for fix in fix_snippets:
        fix_clean = fix.strip()
        if not fix_clean:
            continue

        # Short operators/expressions (e.g., '==', 'i + 1', '<=')
        escaped = re.escape(fix_clean)
        directive_patterns = [
            rf"(?:change|replace|switch|convert)\b[^\n.]*?\bto\s+[`'\"]?{escaped}[`'\"]?",
            rf"(?:change|replace|switch|convert)\b[^\n.]*?\bwith\s+[`'\"]?{escaped}[`'\"]?",
            rf"(?:should be|ought to be|needs to be|must be)\s+[`'\"]?{escaped}[`'\"]?",
            rf"(?:use|write)\s+[`'\"]?{escaped}[`'\"]?",
        ]
        for pat in directive_patterns:
            if re.search(pat, reply, re.IGNORECASE):
                return {
                    "is_leak": True,
                    "leak_type": "explicit_fix",
                    "reason": f"Assistant explicitly gave the fix instruction '{fix_clean}'.",
                }

        # Substantial code phrases/snippets (> 5 chars, e.g. multi-word fixes)
        if len(fix_clean) > 5 and fix_clean in reply:
            is_in_toy = any(
                fix_clean in block and _is_toy_example(block, bug_code)
                for block in code_blocks
            )
            if not is_in_toy:
                return {
                    "is_leak": True,
                    "leak_type": "explicit_fix",
                    "reason": f"Assistant included the fix snippet '{fix_clean}'.",
                }

    return {"is_leak": False, "leak_type": None, "reason": None}