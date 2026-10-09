# Examples: when each orchestration pattern wins

The calculator in [`adk_multiagent_systems/`](../adk_multiagent_systems/) isolates the *coordination tax* in its simplest form. These examples move the same comparison to production-shaped problems — including one where the **multi-agent pattern is the right call** — so the conclusion is "which pattern, when", not "workflow always wins".

| Example | Shape of the problem | Expected winner | What it demonstrates |
|---|---|---|---|
| [`invoice_pipeline/`](invoice_pipeline/) | Fixed sequence: extract → validate → normalize → post | **Workflow** (`SequentialAgent`) | An LLM coordinator spends calls re-deriving an order the code already knew. The tax is a *fixed cost per document*, multiplied by volume. |
| [`support_triage/`](support_triage/) | Route depends on the request — and sometimes on what a tool discovers mid-way | **Multi-agent** | "Classify once, dispatch in code" is cheap but fixes the route before any tool runs. When the real cause only appears in a tool result ("internet down" → *suspended for non-payment* → billing), only dynamic routing resolves it. |
| [`writer_critic/`](writer_critic/) | Iterate until a checkable bar is met | **Workflow** (`LoopAgent`) | Each revision round costs the multi-agent pattern extra routing calls; `max_iterations` bounds cost in code instead of in a prompt. Also shows the fix for the *silent loop exit*. |

## Design rules (so the comparison is fair)

- **Same specialists in both patterns.** Each example builds its specialists with a factory in `specialists.py`; only the hand-off line of the instructions differs between `multiagent/` and `workflow/`.
- **Work in code, judgement in the LLM.** Anything checkable — RUT check digits, VAT, refund eligibility, return windows, text constraints — is a deterministic tool. The LLM reads messy input, classifies, and writes.
- **Graded by code.** Each `cases.py` defines the inputs, a `complexity` value (the benchmark's x-axis) and a `grade()` function. Correctness never depends on an LLM judging an LLM.
- **Workflow roots are code.** The workflow variants use a `SequentialAgent` root (no LLM front-door), plus small code-only agents where needed: a `Dispatcher` (triage) and a `Presenter` (writer/critic).

## Layout

```
examples/
  common.py                  # env, logging, model, 429 plugin (shared)
  <example>/
    tools.py                 # deterministic tools + mock data
    specialists.py           # the specialists, built per pattern
    multiagent/agent.py      # LLM coordinator + transfer_to_agent
    workflow/agent.py        # SequentialAgent / LoopAgent + code agents
    cases.py                 # LADDER + GUARD cases and grade()
```

## Running

From the repo root, with a `.env` in place (`cp .env.TEMPLATE .env`):

```bash
# Interactive, with the ADK CLI
PYTHONPATH=. .venv/bin/adk run examples/support_triage/multiagent

# Benchmark one example (2 patterns x cases x reps) -> benchmark/results_<example>.jsonl
PYTHONPATH=. .venv/bin/python benchmark/bench_run.py --example invoice_pipeline --reps 3
.venv/bin/python benchmark/bench_report.py --infile benchmark/results_invoice_pipeline.jsonl --csv benchmark/invoice.csv
.venv/bin/python benchmark/bench_plot.py --csv benchmark/invoice.csv --prefix invoice_
```

For the examples, the report's `transf` / `updt` columns are *coordination* tool calls (`transfer_to_agent`, `exit_loop`) vs. *work* tool calls (everything else).

## Cases

**invoice_pipeline** — Chilean supplier invoices (text in Spanish, as received). `I1`…`I10`: valid invoices with 1–10 line items. Guards: invalid RUT check digit, wrong VAT, wrong total. Graded on the final `STATUS:` line.

**support_triage** — Mock ISP back-office. `T_*`: single-team requests. `M_BILL_RET`: two intents in one message. `D_SUSP`, `D_RET_TECH`: *discovery* cases where the team that must act is only revealed by a tool result. Guard: legal threat → human escalation. Graded on the exact set of actions taken (refunds, labels, visits, payment plans, escalations).

**writer_critic** — Product copy with 2–8 hard constraints parsed from the brief. Guard: unsatisfiable constraints, to measure what each pattern spends when approval never comes. Graded by re-checking the presented draft in code.
