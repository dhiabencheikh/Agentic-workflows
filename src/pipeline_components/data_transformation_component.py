"""Data transformation component for Vertex AI pipeline.

Turns the Socratic Debugging Benchmark text files into chat examples
for Phi-3 fine-tuning, split by problem into train, validation and test.

One example = the conversation so far (input) + the next tutor turn (target).
"""

from kfp.dsl import OutputPath, component


@component(
    base_image="python:3.11-slim",
    packages_to_install=["gcsfs==2025.9.0"],
)
def data_transformation_component(
    raw_dataset_uri: str,
    system_prompt: str,
    prompt_version: str,
    num_validation_problems: int,
    seed: int,
    train_dataset: OutputPath("Dataset"),  # type: ignore
    validation_dataset: OutputPath("Dataset"),  # type: ignore
    test_dataset: OutputPath("Dataset"),  # type: ignore
) -> None:
    """Parse, format, deduplicate and split the dataset into JSONL files.

    Args:
        raw_dataset_uri: folder (gs:// or local) holding the authors'
            `train/` and `testset/` sub-folders of `.txt` files.
        system_prompt: tutor instructions put first in every example.
        prompt_version: semantic version of system_prompt, stored in every example.
        num_validation_problems: how many train problems go to validation.
        seed: makes the random choice of validation problems reproducible.
        train_dataset, validation_dataset, test_dataset: output JSONL paths.
    """
    # Imports live inside the function: it runs in its own container on Vertex.
    import json
    import logging
    import os
    import random
    import re

    import fsspec

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    section_tags = (
        "problem",
        "bug_code",
        "bug_desc",
        "bug_fixes",
        "unit_tests",
        "stu_desc",
        "dialogue",
    )

    def parse_sections(text: str) -> dict:
        """Return the content of each <tag>...</tag> section of a file."""
        sections = {}
        for tag in section_tags:
            match = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
            sections[tag] = match.group(1).strip("\n") if match else ""
        return sections

    def parse_dialogue(dialogue: str) -> list:
        """Split a dialogue into turns: role, content and <alt> replies.

        <code> blocks are student code edits. They are always given to the
        student, as a Markdown code block like a student would paste it:
        - after a student line: added to that student turn
        - after a tutor line: the student edited the code before answering,
          so the block is added to the NEXT student turn, never to the tutor
        """
        turns = []
        in_code = False
        code_lines = []
        pending_code = []  # code blocks waiting for the next student turn

        def code_block(lines: list) -> str:
            while lines and not lines[-1].strip():
                lines = lines[:-1]
            return "```python\n" + "\n".join(lines) + "\n```"

        for line in dialogue.split("\n"):
            stripped = line.strip()
            if in_code:
                if stripped == "</code>":
                    block = code_block(code_lines)
                    if turns and turns[-1]["role"] == "user":
                        turns[-1]["content"] += "\n" + block
                    else:
                        pending_code.append(block)
                    in_code = False
                else:
                    code_lines.append(line.rstrip())
                continue
            if stripped == "<code>":
                in_code = True
                code_lines = []
                continue
            speaker = re.match(r"^(User|Assistant):\s?(.*)$", line)
            if speaker:
                role = "user" if speaker.group(1) == "User" else "assistant"
                content = speaker.group(2).strip()
                if role == "user" and pending_code:
                    content = "\n".join([content, *pending_code])
                    pending_code = []
                turns.append({"role": role, "content": content, "alts": []})
                continue
            alt = re.match(r"^\s*<alt>(.*)$", line)
            if alt and turns:
                turns[-1]["alts"].append(alt.group(1).strip())
                continue
            if stripped and turns:
                turns[-1]["content"] += "\n" + line.rstrip()
        if pending_code:
            logger.warning("A <code> block after the last tutor turn had no student turn: dropped")
        return turns

    def merge_same_role(turns: list) -> list:
        """Join consecutive turns by the same speaker (chat roles must alternate)."""
        merged = []
        for turn in turns:
            if merged and merged[-1]["role"] == turn["role"]:
                merged[-1]["content"] += "\n" + turn["content"]
                merged[-1]["alts"] = turn["alts"]
            else:
                merged.append(dict(turn))
        return merged

    def file_metadata(path: str) -> dict:
        """Read problem and bug ids from `<problemId>_<bugId>_<name>_<type>.txt`.

        Any file that is not a `socratic_dialogue` counts as a thread, so
        files with typos in their type (`socratic_thread`, `thead`) are kept.
        """
        name = path.rsplit("/", 1)[-1]
        problem_id, bug_id = name.split("_")[:2]
        file_type = "socratic_dialogue" if name.endswith("_socratic_dialogue.txt") else "conversational_thread"
        return {"source_file": name, "problem_id": problem_id, "bug_id": bug_id, "file_type": file_type}

    def build_examples(sections: dict, meta: dict) -> list:
        """One example per tutor turn: everything said before it, then the turn.

        The tutor sees the problem, the buggy code and the conversation.
        Bug description and fixes are kept as metadata only, never as input.
        """
        context = f"Problem statement:\n{sections['problem']}\n\nMy code:\n```python\n{sections['bug_code']}\n```"
        turns = merge_same_role(parse_dialogue(sections["dialogue"]))
        history = [{"role": "system", "content": system_prompt}]
        if turns and turns[0]["role"] == "assistant":
            history.append({"role": "user", "content": context})
            context_used = True
        else:
            context_used = False

        examples = []
        for index, turn in enumerate(turns):
            if turn["role"] == "assistant":
                examples.append(
                    {
                        "example_id": f"{meta['source_file'][:-4]}#turn{index}",
                        **meta,
                        "turn_index": index,
                        "messages": history + [{"role": "assistant", "content": turn["content"]}],
                        "reference_alternatives": turn["alts"],
                        "bug_desc": sections["bug_desc"],
                        "bug_fixes": sections["bug_fixes"],
                    }
                )
            content = turn["content"]
            if turn["role"] == "user" and not context_used:
                content = f"{context}\n\n{content}"
                context_used = True
            history = history + [{"role": turn["role"], "content": content}]
        return examples

    def comparison_key(messages: list) -> str:
        """Key used only to detect copies; the kept example keeps its original text.

        Ignored: spacing, backticks, and , . ! ? ; : at the end of a word
        (so "`a` is set to `0`" and "a is set to 0," compare equal).
        Kept: letter case, operators and punctuation inside a word, because
        code is case-sensitive and `n - 1`, `n + 1`, `1.5`, `15` differ.
        """

        def normalise(text: str) -> str:
            text = text.replace("`", "")
            text = re.sub(r"[,.!?;:]+(?=\s|$)", "", text)
            return " ".join(text.split())

        return json.dumps([(m["role"], normalise(m["content"])) for m in messages])

    def deduplicate(examples: list) -> list:
        """Drop examples whose messages are copies of an earlier one.

        Thread files repeat the opening of the main dialogue, sometimes with
        formatting differences only. All messages (system, history, target)
        are compared with comparison_key. The alternative replies of the
        copies are merged into the kept example.
        """
        kept = {}
        for example in examples:
            key = comparison_key(example["messages"])
            if key not in kept:
                kept[key] = example
            else:
                alts = kept[key]["reference_alternatives"]
                alts.extend(a for a in example["reference_alternatives"] if a not in alts)
        return list(kept.values())

    def load_split_folder(folder: str) -> list:
        """Parse every .txt file of one authors' folder (train or testset)."""
        fs, root = fsspec.core.url_to_fs(raw_dataset_uri.rstrip("/"))
        paths = sorted(fs.glob(f"{root}/{folder}/*.txt"))
        if not paths:
            raise FileNotFoundError(f"No .txt files in {raw_dataset_uri}/{folder}")
        examples = []
        for path in paths:
            with fs.open(path, "r", encoding="utf-8") as file:
                examples.extend(build_examples(parse_sections(file.read()), file_metadata(path)))
        logger.info(f"{folder}: {len(paths)} files, {len(examples)} examples before deduplication")
        return examples

    def write_jsonl(examples: list, path: str, split: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            for example in examples:
                record = {**example, "split": split, "prompt_version": prompt_version}
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
        problems = sorted({e["problem_id"] for e in examples}, key=int)
        logger.info(f"{split}: {len(examples)} examples from {len(problems)} problems {problems} -> {path}")

    logger.info(f"Reading raw dataset from {raw_dataset_uri}, system prompt v{prompt_version}")
    train_pool = deduplicate(load_split_folder("train"))
    test_examples = deduplicate(load_split_folder("testset"))

    # Split by problem, never by example: all turns of a problem stay together.
    train_problems = sorted({e["problem_id"] for e in train_pool}, key=int)
    validation_problems = set(random.Random(seed).sample(train_problems, num_validation_problems))
    train_examples = [e for e in train_pool if e["problem_id"] not in validation_problems]
    validation_examples = [e for e in train_pool if e["problem_id"] in validation_problems]

    split_problems = [
        {e["problem_id"] for e in examples} for examples in (train_examples, validation_examples, test_examples)
    ]
    for i in range(3):
        for j in range(i + 1, 3):
            overlap = split_problems[i] & split_problems[j]
            if overlap:
                raise ValueError(f"Problems {sorted(overlap)} appear in two splits: data would leak")

    write_jsonl(train_examples, train_dataset, "train")
    write_jsonl(validation_examples, validation_dataset, "validation")
    write_jsonl(test_examples, test_dataset, "test")
    logger.info("Data transformation completed successfully")
