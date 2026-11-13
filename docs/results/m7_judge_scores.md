# M7 LLM-as-a-judge scores on the replayed traces

Judge openai/gpt-4o-mini via OpenRouter, temperature 0, JSON schema answer. Script `scripts/judge_traces.py`, traces since 2026-11-12 23:53:00 UTC. **Not calibrated against human labels.** Rows: `m7_judge_scores.csv`.

Traces judged: 97 (every endpoint-generation; input-blocked turns have no model reply). Matched to a case: 97.

Judge tokens: 285092 in, 11743 out. Cost at OpenRouter's listed price (0.15 / 0.60 USD per 1M): $0.0498 ($0.00051 per trace, 3 evaluators).

- **socratic_quality**, all (n = 97): 1: 10, 2: 2, 3: 10, 4: 6, 5: 69; mean 4.26
- **socratic_quality**, test cards (n = 80): 1: 5, 2: 2, 3: 6, 4: 5, 5: 62; mean 4.46
- **socratic_quality**, adversarial (n = 17): 1: 5, 3: 4, 4: 1, 5: 7; mean 3.29

- **leak**, all (n = 97): 0: 88, 1: 9; mean 0.09
- **leak**, test cards (n = 80): 0: 73, 1: 7; mean 0.09
- **leak**, adversarial (n = 17): 0: 15, 1: 2; mean 0.12

- **confirms_incorrect_fix**, all (n = 97): 0: 82, 1: 15; mean 0.15
- **confirms_incorrect_fix**, test cards (n = 80): 0: 66, 1: 14; mean 0.17
- **confirms_incorrect_fix**, adversarial (n = 17): 0: 16, 1: 1; mean 0.06
