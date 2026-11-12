# M7 traffic replay: eval cases through the app's traced path

Run 2026-11-12 23:53:06 to 23:55:58 UTC, endpoint 298550392290017280 (europe-west2), one request at a time, from Dhia's Mac. Script: `scripts/replay_traffic.py`. Rows: `m7_traffic_replay.csv`.

End-to-end = wall clock of one turn on the client: input guardrail, endpoint call over the internet, output guardrail, Langfuse span creation (export is asynchronous). Percentiles are nearest-rank.

Cases: 106. Errors: 0 (0.0%).

| Outcome | Count |
|---|---|
| answered | 96 |
| input_blocked | 9 |
| output_blocked | 1 |
| error | 0 |

| Slice | n | P50 s | P95 s | P99 s | max s | mean s |
|---|---|---|---|---|---|---|
| All successful turns | 106 | 1.47 | 2.68 | 6.48 | 17.42 | 1.62 |
| Turns that called the model | 97 | 1.54 | 2.68 | 17.42 | 17.42 | 1.77 |
| Input-blocked turns (no model call) | 9 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

| Category | Outcomes |
|---|---|
| ask_for_answer | answered 10 |
| off_topic | answered 6 |
| prompt_injection | input_blocked 9, output_blocked 1 |
| socratic_turn | answered 80 |

With about 100 values, P99 is the largest or second-largest value: read it as an indication, not a stable estimate.
