# Google ADK Calculator: Multi-Agent vs. Workflow Orchestration

This repository contains two alternative implementations of a mathematical expression evaluator built on the **Google Agent Development Kit (ADK)** and the Gemini API, adapted and extended from the [skills.google](https://www.skills.google) code lab **GENAI106: Build Multi-Agent Systems with ADK**.

It provides a comparative codebase demonstrating the differences between **Dynamic Multi-Agent Routing** and **Structured Workflow Loops (`LoopAgent`)**, including deep hierarchical nesting and error boundary validation.

> ### ADK version compatibility
>
> The code in `adk_multiagent_systems/` and `examples/` was written against **ADK 1.x** and **also runs unchanged on ADK 2.11** — verified offline and against Gemini, see [`adk2/evidence/`](adk2/evidence/). In 2.x, `transfer_to_agent` routing is still the default (`mode="chat"`), while `SequentialAgent`, `LoopAgent` and `ParallelAgent` are **deprecated** in favour of `Workflow`: they emit a `DeprecationWarning` but work. `requirements.txt` pins `google-adk<2` so the 1.x results stay reproducible and nothing breaks when the deprecated agents are removed.
>
> | This repo (ADK 1.x) | ADK 2.x |
> |---|---|
> | Multi-agent routing (`sub_agents` + `transfer_to_agent`) | Unchanged (`mode="chat"`), or **`mode="single_turn"`**: each specialist becomes a function tool of the coordinator and always returns control (`mode="task"` adds multi-turn delegation) |
> | `SequentialAgent` / `LoopAgent` + `exit_loop` | **`google.adk.Workflow`** graph: nodes (agents, functions, tools) and edges; routing decisions are code (`ctx.route`), cycles are bounded in code |
>
> [`adk2/`](adk2/) ports every case to both 2.x forms and benchmarks four variants side by side. Two 2.x behaviours matter for this comparison: inter-agent history is wrapped in anti-prompt-injection quoting (**+30–70% input tokens on identical code**), and the dev UI now flags every `transfer_to_agent` as a context-cache miss.

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
Copy the template and fill in your Vertex AI project, location, and model:
```bash
cp .env.TEMPLATE .env
```
A single `.env` at the repo root is picked up by every agent (`load_dotenv()` searches upwards from each agent's directory). A `.env` inside a package directory (e.g. `parent_and_subagents/.env`) takes precedence for that package. The minimum configuration is:
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

## More examples

The calculator isolates the coordination tax in its simplest form. [`examples/`](examples/) applies the same comparison to production-shaped problems — an invoice pipeline (workflow wins), support triage with mid-flight discovery (multi-agent wins) and a writer/critic loop — each with code-graded cases that plug into the benchmark via `--example`. See [`examples/README.md`](examples/README.md).

**Case 0** — what a single, well-instructed agent does with the same problem, with no orchestration at all — lives in [`baseline/`](baseline/).

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
