# ADK 2.x port

Every case in this repo (the calculator and the three `examples/`) ported to the two ADK 2.x orchestration forms, and benchmarked against the unchanged 1.x code running on ADK 2.11.

| Variant | Where | What it is |
|---|---|---|
| `multiagent_chat` | `adk_multiagent_systems/parent_and_subagents`, `examples/*/multiagent` | The 1.x code, unchanged: `sub_agents` + `transfer_to_agent` (`mode="chat"`, the 2.x default) |
| `workflow_legacy` | `adk_multiagent_systems/workflow_agents`, `examples/*/workflow` | The 1.x code, unchanged: `SequentialAgent` / `LoopAgent` (deprecated in 2.x, still working) |
| `multiagent_single_turn` | `adk2/<case>/multiagent_single_turn` | Same coordinator and specialists, specialists with `mode="single_turn"`: each one is a function tool of the coordinator and always returns control |
| `workflow_graph` | `adk2/<case>/workflow_graph` | `google.adk.Workflow`: nodes and edges; routing decisions are code (`ctx.route`), cycles are bounded in code |

## Setup

ADK 1.x and 2.x cannot share a virtualenv:

```bash
python3.13 -m venv .venv2 && .venv2/bin/pip install -r adk2/requirements.txt
cp .env.TEMPLATE .env   # if you have not already
```

```bash
# Interactive
PYTHONPATH=. .venv2/bin/adk web adk2/support_triage          # pick workflow_graph or multiagent_single_turn

# Benchmark the four variants of one case
PYTHONPATH=. .venv2/bin/python benchmark/bench_run.py --adk2 --example support_triage --reps 3
PYTHONPATH=. .venv2/bin/python benchmark/bench_run.py --adk2 --reps 3                 # calculator

# Offline checks (no credentials, scripted LLM)
.venv2/bin/python adk2/evidence/scripts/adk2_offline_test.py
```

## How each case translates

- **Calculator** — `plan` (code) picks the next operation by parentheses and precedence and routes to the specialist that performs it; `apply` (code) substitutes the result; a divisor of zero is a routed edge. One LLM call per operation, and the "broken precedence" and "LLM ends the loop early" failure modes cannot happen.
- **Invoice pipeline** — extract (LLM) → validate (code) → normalize (LLM) → post (code). The rejection short-circuit is a routed edge instead of a `before_agent_callback`.
- **Support triage** — triage (LLM, `output_schema`) → `dispatch` (code) → specialist (LLM, structured `Report` with `handoff_to`) → back to `dispatch`. The LLM declares what it discovered; code decides where the ticket goes next, each team at most once.
- **Writer/critic** — writer (LLM) → critic (code, the same deterministic check) → `revise` back to the writer or `present`, bounded by a round counter in state.

## Results (smoke run: ADK 2.11, gemini-2.5-flash, 1 run per case)

| Variant | Correct (4 cases) | LLM calls per run: calc / invoice / triage / writer |
|---|---|---|
| `multiagent_chat` | 19/24 | 10.6 / 8.9 / 6.1 / 9.8 |
| `multiagent_single_turn` | 14/24 | 6.7 / 8.3 / 6.4 / 8.8 |
| `workflow_legacy` | 22/24 | 9.6 / 6.3 / 5.7 / 9.8 |
| **`workflow_graph`** | **24/24** | **5.0 / 3.1 / 5.0 / 3.6** |

What showed up while measuring:

1. **The 1.x code runs unchanged on 2.11**, but uses **+30–70% input tokens**: 2.x wraps every event authored by another agent in an anti-prompt-injection preamble. See `evidence/06_token_overhead_cause.txt`.
2. **The dev UI flags every `transfer_to_agent` as a context-cache miss** (`evidence/screenshots/03_*`): the coordination tax, acknowledged by the framework.
3. **`workflow_graph` resolves the discovery case** the 1.x workflow loses (`D_SUSP`: "internet down" → suspended for non-payment → billing), see `evidence/screenshots/04–06_*`.
4. **`single_turn` removes the dropped hand-off but adds its own failure**: the coordinator sometimes ends with an empty final response, or passes a specialist only a fragment of the expression.
5. **Thinking tokens dominate output cost** on Gemini 2.5 and are not part of `candidates_token_count`; `bench_run.py` now records them (`thought_tok`) and includes them in `cost_usd`. Runs in `evidence/` made before that change (`04_*`, `05_*`, the calculator, invoice and triage `08_*`) exclude them.

These are smoke numbers (N=1); run with `--reps 10` before quoting them as results.

## Evidence

`evidence/` holds the text outputs, raw JSONL, dev UI screenshots and the scripts that reproduce them:

| File | Content |
|---|---|
| `00_versions.txt` | ADK, google-genai and Python versions of both virtualenvs |
| `01_offline_tests_adk{1,2}.txt` | Offline tests of `examples/` on both versions |
| `02_calculator_integration_adk{1,2}.txt` | `test_agents.py` on both versions (on 1.39 `adk run` no longer accepts the query as an argument, so the script itself fails) |
| `04_*`, `05_smoke_adk1_vs_adk2.txt` | The unchanged `examples/` on 2.x, and the 1.x vs 2.x comparison |
| `06_token_overhead_cause.txt` | Request-size trace explaining the token overhead (`scripts/probe_*`) |
| `07_smoke_calculator_adk1.txt` | Calculator smoke on 1.x |
| `08_smoke_adk2_4variants_*.txt`, `raw/` | The four-variant benchmark |
| `screenshots/` | ADK 2.11 dev UI: calculator runs, the cache-miss warning, the triage graph re-routing |
