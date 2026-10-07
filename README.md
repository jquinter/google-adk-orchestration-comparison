# Google ADK Calculator: Multi-Agent vs. Workflow Orchestration

This repository contains two alternative implementations of a mathematical expression evaluator built on the **Google Agent Development Kit (ADK)** and the Gemini API, adapted and extended from the [skills.google](https://www.skills.google) code lab **GENAI106: Build Multi-Agent Systems with ADK**.

It provides a comparative codebase demonstrating the differences between **Dynamic Multi-Agent Routing** and **Structured Workflow Loops (`LoopAgent`)**, including deep hierarchical nesting and error boundary validation.

> ### ⚠️ ADK version compatibility
>
> This code targets **ADK 1.x**. It uses the 1.x agent API — `Agent` with `transfer_to_agent` routing, `LoopAgent`, and `exit_loop`. **ADK 2.0 (GA) introduced breaking changes** to the agent API, the event model, and the session schema, so a bare `pip install google-adk` — which now resolves to 2.x — will **not** run this repo as-is. Install the pinned dependencies with `pip install -r requirements.txt` (which pins `google-adk<2`).
>
> The two patterns map cleanly onto ADK 2.0's dual orchestration model, so the comparison stays conceptually current:
>
> | This repo (ADK 1.x) | ADK 2.0 equivalent |
> |---|---|
> | Multi-agent routing (`transfer_to_agent`) | **Task API** — coordinator + sub-agents delegation |
> | `LoopAgent` workflow | **Workflow DAG** (`google.adk.Workflow`) |
>
> The findings below — the coordination-cost trade-off and the failure modes — are *structural*: they describe orchestrating with an LLM vs. with code, not a specific API version, and hold after migration. A 2.0 port is future work.

---

## Codebase Architecture

```
├── adk_multiagent_systems/
│   ├── parent_and_subagents/        # Multi-Agent implementation
│   │   ├── .env                     # App configuration (Vertex AI, model info)
│   │   └── agent.py                 # Steering and 4 specialist agents
│   └── workflow_agents/             # Workflow implementation
│       ├── .env                     # App configuration (Vertex AI, model info)
│       └── agent.py                 # LoopAgent, state tools, and specialists
│
├── test_agents.py                   # Self-contained integration test suite
├── print_timeline_multiagent.py     # Parse SQLite logs for parent_and_subagents
├── print_timeline_workflow.py       # Parse SQLite logs for workflow_agents
└── README.md                        # This documentation file
```

### 1. Dynamic Multi-Agent evaluator (`parent_and_subagents`)
- **Root Agent:** `steering` (acts as an orchestrator coordinator).
- **Specialist Sub-agents:** `adder`, `substracter`, `multiplier`, `divider`.
- **Validation Guard:** `zero_division_guard` (nested sub-agent of `divider`).
- **Orchestration:** `steering` routes terms dynamically to the correct specialist using ADK's `transfer_to_agent` tool based on mathematical precedence. The specialists evaluate their part, and transfer control back to `steering`.

### 2. Workflow bucle evaluator (`workflow_agents`)
- **Root Agent:** `workflow_steering` (coordinator that initializes state and delegates).
- **Loop Container:** `calculator_loop` (a structured `LoopAgent`).
- **Specialist Sub-agents:** `adder`, `substracter`, `multiplier`, `divider` (executing in a fixed sequence).
- **Validation Guard:** `zero_division_guard` (nested sub-agent of `divider`).
- **Orchestration:** The specialists execute in a pre-defined sequential loop, modifying the shared session state via the `update_expression` tool. Whichever specialist resolves the expression to a single number prints the final value and exits the loop using `exit_loop`.

---

## Getting Started

### 1. Enable Virtual Environment & Install Dependencies
Activate your virtual environment and install the pinned dependencies before running any scripts:
```bash
source .venv/bin/activate
pip install -r requirements.txt   # pins google-adk<2 (ADK 1.x)
```

### 2. Configure Environment Variables
Verify that the `.env` files in both directories (`parent_and_subagents/.env` and `workflow_agents/.env`) contain your correct Vertex AI project, location, and model configuration:
```env
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
MODEL=gemini-2.5-flash
```

---

## Running the Evaluator

You can execute either evaluator from the command line using the ADK CLI:

### Running the Multi-Agent App
```bash
PYTHONPATH=. .venv/bin/adk run adk_multiagent_systems/parent_and_subagents "((12 + 8) * 5) - (10 / 2) + (4 * 6) - (50 / 5)"
```

### Running the Workflow-based App
```bash
PYTHONPATH=. .venv/bin/adk run adk_multiagent_systems/workflow_agents "((12 + 8) * 5) - (10 / 2) + (4 * 6) - (50 / 5)"
```

---

## Self-Contained Testing

To verify the evaluation correctness, mathematical operator precedence, and the nested `zero_division_guard` validation boundaries for both applications, run the integration test suite:
```bash
PYTHONPATH=. .venv/bin/python test_agents.py
```
This runs four test cases:
1. Complex expression evaluation (`109`) on the Multi-Agent app.
2. Complex expression evaluation (`109`) on the Workflow-based app.
3. Division by zero validation error on the Multi-Agent app.
4. Division by zero validation error on the Workflow-based app.

---

## Log Analysis & Explainability Timeline

To see a unified, step-by-step history of all internal agent transitions, tool calls, and intermediate simplified expressions, run the log parsers:

### View Multi-Agent Execution Timeline
```bash
PYTHONPATH=. .venv/bin/python print_timeline_multiagent.py
```

### View Workflow Loop Execution Timeline
```bash
PYTHONPATH=. .venv/bin/python print_timeline_workflow.py
```

---

## Quantitative Benchmark

The [`benchmark/`](benchmark/) directory measures the **cost of coordination** for each pattern across a ladder of expressions of increasing complexity, so the multi-agent-vs-workflow trade-off is backed by numbers rather than intuition. It captures, per run: LLM calls, input/output tokens, tool-call counts (`transfer_to_agent` vs. `update_expression`), per-run cost (USD), wall-clock, and the variance across repetitions.

```bash
# 1. Run the matrix (2 patterns x 5 rungs x N reps) -> benchmark/results.jsonl
PYTHONPATH=. .venv/bin/python benchmark/bench_run.py

# 2. Aggregate into a table (mean +/- sigma) and a CSV
.venv/bin/python benchmark/bench_report.py --csv benchmark/bench.csv

# 3. Generate the three figures (with error bars)
.venv/bin/python benchmark/bench_plot.py --csv benchmark/bench.csv
```

LLM-call and token counts are the robust, reproducible metrics and drive both cost and latency; wall-clock is noisy (the agents retry up to 30x on HTTP 429), so report it with error bars or lead with calls and tokens. See [`benchmark/README.md`](benchmark/README.md) for the full methodology and caveats.

---

## Hard-won lessons

Three failure modes that only surface once these systems actually run — each with its fix in the code:

1. **Tool-loop recurrence** — uncontrolled recursion of tool-calls that never converges.
2. **Operator precedence breaking** under a fixed sequential pass — the right answer for the wrong reason.
3. **Silent loop exit** — `exit_loop` closing the session before the final result is printed.

These are discussed in the companion article: [*Comparing Orchestration Patterns in Google ADK*](https://medium.com/google-cloud/comparing-orchestration-patterns-in-google-adk-multi-agent-vs-workflow-based-loops-958eb1a835dd).

---

## A note on the model

The `.env` uses `gemini-2.5-flash`. As of late 2026 this is a prior-generation model (Gemini 3 Flash is the current default), but it is still available and its pricing — $0.30 / $2.50 per 1M input/output tokens (Vertex standard, verified Oct 2026) — is what the benchmark's cost model assumes. The pattern-level conclusions are **model-independent**: the coordination tax is a property of the orchestration, not of the model generation. Swap `MODEL` in `.env` to benchmark another model.
