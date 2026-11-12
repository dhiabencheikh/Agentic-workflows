# M4 leak check calibration

Measured with `scripts/calibrate_leak_check.py`; leak check `eval/leak_checks.py` frozen at commit `b1828bd`
(`REWRITE_SIMILARITY=0.75`, `MIN_LINE_TOKENS=3`). Data: the M1 cards (Vertex run
`model-training-pipeline-20261112142518`). Measured on 2026-11-12.

## What is measured

- **False alarms:** the share of real human tutor replies (each card's reply plus its `reference_alternatives`)
  that the check flags as leaks. Human tutors do not leak, so this should be close to zero.
- **Catch rate:** the share of known leaking replies that the check flags, in three categories:
  A = the full corrected function, B = the fix stated outright, C = a student line rewritten for them.

| Split | Human replies | Known leaks | Leaks built by |
|---|---|---|---|
| train | 1,299 | 187 | `scripts/build_leak_examples.py`, from the corrected code students reach in the dialogues |
| validation | 288 | 38 | same script |
| test | 207 | 36 | written by hand during the PR #6 review (`eval/fixtures/leaks_test.jsonl`) |

## Results

| Split | False alarms on human replies | Caught A full function | B fix stated | C line rewritten | All known leaks |
|---|---|---|---|---|---|
| train | 0/1299 (0.0%) | 40/40 | 32/43 | 70/104 | 142/187 (76%) |
| validation | 0/288 (0.0%) | 7/8 | 7/8 | 13/22 | 27/38 (71%) |
| **test** | **3/207 (1.4%)** | **6/6** | **9/12** | **14/18** | **29/36 (81%)** |

For comparison, on the same test sets during the review: the first version of the check flagged 7/207 test
human replies and caught 19/36 test leaks (53%).

## How the rules were tuned (no contamination of test)

- Every rule change and the two settings were chosen on **train and validation only**: 1,587 human replies and
  225 generated leaks. The settings come from a grid over `MIN_LINE_TOKENS` in {2, 3, 4} and
  `REWRITE_SIMILARITY` in {0.7, 0.75, 0.8}: 3 and 0.75 is the setting with 0 false alarms on train and
  validation and the most leaks caught (169/225).
- The test split was then measured **once**, with the rules frozen, and only totals were printed. The 3 test
  false alarms and 7 missed test leaks were deliberately not inspected.

## Caveats (read before quoting the test figure)

- **The test figures may be slightly optimistic.** During the PR #6 review, test false alarms and test catch
  rates were viewed for three earlier variants of the check (the original, a snippet-only fix, a prototype),
  and those views shaped the direction of the fixes (replacement side only, rewritten-line detection).
  No setting was tuned on test, but the test set is not fully untouched.
- **Different leak styles:** train and validation leaks are generated from templates; test leaks are written by
  hand with more varied phrasing. This is one reason the rates differ between splits.
- **About 1 leak in 5 is still missed on test**, mostly fixes stated in prose without code (B) and rewrites the
  token comparison does not recognise (C). The leak check is a fast, deterministic first line; the LLM judge
  (M3) is needed for the rest.
- **Known blind spot, by design:** sentences that frame code as an experiment to run (terminal, shell, "try
  running") are allowed as toy examples (`10_39_xnglxsh`), so a fix disguised as an experiment is not caught.

## Correction

An earlier version of this file reported "0 false positives on 80 human test cards". Those figures came from
`eval/results.json`, which the runner had computed on **empty replies** (it read fields that do not exist in
the cards). They did not measure the check and are replaced by the figures above.

## Reproduce

```bash
uv run --no-dev python -m scripts.build_leak_examples          # train/validation leaks
uv run --no-dev python -m scripts.calibrate_leak_check         # tuning view: train, validation
uv run --no-dev python -m scripts.calibrate_leak_check --final-test   # final figures, totals only
```
