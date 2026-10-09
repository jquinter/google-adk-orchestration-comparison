# Case 0: no orchestration

What if one agent evaluates the whole expression in a single LLM call? Two variants, to separate the effect of orchestration from the effect of the instruction:

- `naive_agent/` — a one-line instruction: "Evaluate the arithmetic expression the user gives you."
- `structured_agent/` — the five patterns of a professional ADK instruction (Google Skills, *Structured instructions*): identity, mission, methodology, boundaries (scope, quality, the exact division-by-zero message) and few-shot examples including the edge cases.

Both run on ADK 1.x and 2.x and are part of the calculator benchmark as `single_naive` and `single_structured`:

```bash
PYTHONPATH=. .venv/bin/python benchmark/bench_run.py --patterns single_naive,single_structured --reps 3
```

## Results (ADK 1.39, gemini-2.5-flash, 2 runs × 7 cases per pattern)

| Pattern | Correct | LLM calls | Tokens (in + out + thinking) | Cost per run | Time |
|---|---|---|---|---|---|
| Single agent, naive | 14/14 | 1 | 270 | $0.0006 | 1.5 s |
| Single agent, structured | 14/14 | 1 | 904 | $0.0011 | 2.2 s |
| Workflow (`LoopAgent`) | 13/14 | 13.3 | 15,370 | $0.0091 | 23.2 s |
| Multi-agent | 13/14 | 9.9 | 11,726 | $0.0103 | 23.2 s |

For this problem orchestration is pure overhead: the same accuracy at roughly 10× the cost and 10× the latency. The structured instruction did not buy accuracy (both single agents are 14/14); it bought a **contract** — the steps, a fixed final line (`El resultado es N`) and the exact error message — where the naive agent answers `109` or a free-form English sentence.

The calculator remains a teaching vehicle: it isolates the cost of coordination precisely because one agent could solve it alone. Raw data and the summary are in `evidence/`.
