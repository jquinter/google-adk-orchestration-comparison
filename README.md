# Google ADK Calculator: Multi-Agent vs. Workflow Orchestration

This repository contains two alternative implementations of a mathematical expression evaluator built on the **Google Agent Development Kit (ADK)** and the Gemini API, adapted and extended from the [skills.google](https://www.skills.google) code lab **GENAI106: Build Multi-Agent Systems with ADK**.

It provides a comparative codebase demonstrating the differences between **Dynamic Multi-Agent Routing** and **Structured Workflow Loops (`LoopAgent`)**, including deep hierarchical nesting and error boundary validation.

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
Ensure you have the virtual environment activated before running any scripts:
```bash
source .venv/bin/activate
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
