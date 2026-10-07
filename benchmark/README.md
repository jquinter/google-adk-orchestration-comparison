# Benchmark: the cost of coordination

This directory quantifies the trade-off between the two orchestration patterns
across a ladder of expressions of increasing complexity, so the comparison is
backed by measurements rather than intuition.

## What it measures

Per run: LLM calls, input/output tokens, tool-call counts (`transfer_to_agent`
vs. `update_expression`), cost (USD), wall-clock, and the variance across `N`
repetitions.

The independent variable is **expression complexity** (number of binary
operations). The hypothesis is that the multi-agent pattern pays a
*coordination tax* — every `transfer_to_agent` is an LLM call that computes
nothing — that scales with complexity, while the workflow loop, whose
orchestration is code rather than inference, stays cheaper and more
predictable.

## Running it

From the repo root:

```bash
# 1. Run the matrix (2 patterns x 5 rungs x N reps, + guard cases) -> results.jsonl
PYTHONPATH=. .venv/bin/python benchmark/bench_run.py

# 2. Aggregate into a table (mean +/- sigma) and a CSV
.venv/bin/python benchmark/bench_report.py --csv benchmark/bench.csv

# 3. Generate the three figures with error bars
.venv/bin/python benchmark/bench_plot.py --csv benchmark/bench.csv
```

`bench_plot.py` writes `fig1_escalado.png`, `fig2_predictibilidad.png` and
`fig3_coordinacion.png` to the current directory.

## Prerequisites

Same setup the evaluators already need: valid Application Default Credentials
(the agent modules initialise Cloud Logging on import) and `MODEL` set in each
package's `.env` (loaded automatically by `bench_run.py` before the agents
import).

## Reading the numbers honestly

- **LLM-call and token counts are the robust metrics.** They are reproducible
  across regions and drive both cost and latency. Lead with them.
- **Wall-clock is noisy here.** The agents retry up to 30x on HTTP 429, so
  under rate limiting wall-clock inflates while call/token counts stay stable.
  Report wall-clock with error bars (`bench_report.py` emits the standard
  deviation), or don't lead with it.
- **Variance is a first-class result**, not a footnote: a tight, predictable
  cost is often worth more in production than a lower but noisier average.
- **The cost model** assumes Gemini 2.5 Flash at $0.30 / $2.50 per 1M
  input/output tokens (Vertex standard, verified Oct 2026). Update the
  constants in `bench_run.py` if you change `MODEL`.
