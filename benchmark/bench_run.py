"""
bench_run.py — Run the (pattern x case x repetition) matrix and capture
metrics LIVE from ADK's event stream into a JSONL file.

Token metrics (usage_metadata) are read off each Event while it runs — where
they are guaranteed present — rather than relying on ADK persisting them to its
SQLite session store. The JSONL file is the source of truth; re-analyse it with
bench_report.py without spending another token.

Run from the repo root:
    PYTHONPATH=. .venv/bin/python benchmark/bench_run.py                        # calculator
    PYTHONPATH=. .venv/bin/python benchmark/bench_run.py --example invoice_pipeline
    PYTHONPATH=. .venv/bin/python benchmark/bench_run.py --example support_triage --reps 3

`--example` is "calculator" (the original apps) or any folder under examples/
that provides multiagent/agent.py, workflow/agent.py and cases.py.

`--adk2` (run with the ADK 2.x virtualenv, see adk2/README.md) benchmarks four
variants instead of two: the unchanged 1.x code (multiagent_chat,
workflow_legacy) plus the 2.x ports under adk2/ (multiagent_single_turn,
workflow_graph).

For the calculator, two single-agent baselines ("case 0", baseline/) run in
both modes: single_naive (one-line instruction) and single_structured (identity,
mission, methodology, boundaries, few-shot examples). `--patterns` limits a run
to some patterns, e.g. `--patterns single_naive,single_structured`.

Thinking tokens (Gemini 2.5 thinks by default) are billed as output but are not
part of candidates_token_count, so they are recorded separately (thought_tok)
and included in cost_usd.

Prerequisites (same as running the evaluators):
  - Valid Application Default Credentials — the agent modules initialise Cloud
    Logging on import.
  - MODEL set in a `.env` (repo root, or each calculator package's own `.env`).

Portability note: attribute names (usage_metadata, prompt_token_count,
candidates_token_count, function_call) and the InMemoryRunner / run_async /
create_session surface follow ADK 1.x. If your version differs, adjust here.
"""

import argparse
import asyncio
import importlib
import json
import random
import time
from pathlib import Path

from dotenv import load_dotenv
from google.genai import types
from google.adk.runners import InMemoryRunner

REPO = Path(__file__).resolve().parent.parent

# --- Calculator: complexity ladder (id, expression, n_ops, expected_result) ---
CALC_LADDER = [
    ("B",  "10 / 2",                                                                                     1,  5),
    ("L1", "2 + 3 * 4 - 10 / 2",                                                                          4,  9),
    ("L2", "(12 + 8) * 5 - (10 / 2) + 4 * 6",                                                             6,  119),
    ("L3", "((12 + 8) * 5) - (10 / 2) + (4 * 6) - (50 / 5)",                                              8,  109),
    ("L4", "((12 + 8) * 5) - (10 / 2) + (4 * 6) - (50 / 5) + (100 / 4) - (7 * 3) + (18 / 2)",             14, 122),
]

# --- Calculator guard (error path): division by zero ---------------------------
CALC_GUARD = [
    ("G1", "10 / 0",            None, None),
    ("G2", "(4 * 6) / (5 - 5)", None, None),
]

N = 10          # repetitions per cell
WARMUP = 1      # discarded per pattern (cold start)

# Gemini 2.5 Flash, Vertex standard tier. Verified Oct 2026. UPDATE if you swap MODEL.
PRICE_IN = 0.30 / 1e6    # USD / input token
PRICE_OUT = 2.50 / 1e6   # USD / output token

# Tool calls that coordinate rather than do work. In ADK 2.x single-turn
# delegation, calling a specialist (e.g. `adder(request=...)`) is also a routing
# decision, so calls named after an agent in the tree count as coordination.
COORDINATION_TOOLS = {"transfer_to_agent", "exit_loop"}


def agent_names(root):
    names, stack = set(), [root]
    while stack:
        node = stack.pop()
        names.add(getattr(node, "name", None))
        stack.extend(getattr(node, "sub_agents", None) or [])
    return names - {None}


def _calc_grade(case, final_text, metrics):
    expected = case["expected"]
    if expected is None:  # guard cases: the division by zero must be detected and reported
        text = (final_text or "").lower()   # any explicit wording counts, not only the instructed phrase
        return any(k in text for k in ("cero", "zero", "undefined", "indefinid", "no está definid"))
    return str(expected) in (final_text or "")


def _adk2_patterns(name, chat_module, legacy_module):
    return {
        "multiagent_chat": importlib.import_module(chat_module).root_agent,
        "workflow_legacy": importlib.import_module(legacy_module).root_agent,
        "multiagent_single_turn": importlib.import_module(f"adk2.{name}.multiagent_single_turn.agent").root_agent,
        "workflow_graph": importlib.import_module(f"adk2.{name}.workflow_graph.agent").root_agent,
    }


def load_calculator(adk2=False):
    # The agent modules call load_dotenv() and read os.getenv("MODEL") at import
    # time, so each package's .env must be in the environment first.
    load_dotenv(REPO / "adk_multiagent_systems" / "parent_and_subagents" / ".env")
    from adk_multiagent_systems.parent_and_subagents.agent import root_agent as multiagent_root
    load_dotenv(REPO / "adk_multiagent_systems" / "workflow_agents" / ".env", override=True)
    from adk_multiagent_systems.workflow_agents.agent import root_agent as workflow_root
    load_dotenv(REPO / ".env")

    to_case = lambda t: {"id": t[0], "input": t[1], "complexity": t[2], "expected": t[3]}  # noqa: E731
    patterns = {"multiagent": multiagent_root, "workflow": workflow_root}
    if adk2:
        patterns = _adk2_patterns("calculator", "adk_multiagent_systems.parent_and_subagents.agent",
                                  "adk_multiagent_systems.workflow_agents.agent")
    patterns["single_naive"] = importlib.import_module("baseline.naive_agent.agent").root_agent
    patterns["single_structured"] = importlib.import_module("baseline.structured_agent.agent").root_agent
    return patterns, [to_case(t) for t in CALC_LADDER], [to_case(t) for t in CALC_GUARD], _calc_grade


def load_example(name, adk2=False):
    load_dotenv(REPO / ".env")
    if adk2:
        patterns = _adk2_patterns(name, f"examples.{name}.multiagent.agent", f"examples.{name}.workflow.agent")
    else:
        patterns = {pat: importlib.import_module(f"examples.{name}.{pat}.agent").root_agent
                    for pat in ("multiagent", "workflow")}
    cases = importlib.import_module(f"examples.{name}.cases")
    return patterns, cases.LADDER, cases.GUARD, cases.grade


async def one_run(root, text):
    runner = InMemoryRunner(agent=root, app_name="bench")
    session = await runner.session_service.create_session(app_name="bench", user_id="u")
    msg = types.Content(role="user", parts=[types.Part(text=text)])

    m = {"llm_calls": 0, "in_tok": 0, "out_tok": 0, "thought_tok": 0,
         "tool_calls": {}, "activations": {}, "final_text": ""}

    t0 = time.perf_counter()
    async for event in runner.run_async(user_id="u", session_id=session.id, new_message=msg):
        um = getattr(event, "usage_metadata", None)
        if um:
            m["llm_calls"] += 1
            m["in_tok"] += getattr(um, "prompt_token_count", 0) or 0
            m["out_tok"] += getattr(um, "candidates_token_count", 0) or 0
            m["thought_tok"] += getattr(um, "thoughts_token_count", 0) or 0
        author = getattr(event, "author", None)
        if author:
            m["activations"][author] = m["activations"].get(author, 0) + 1
        content = getattr(event, "content", None)
        for p in (getattr(content, "parts", None) or []):
            fc = getattr(p, "function_call", None)
            if fc:
                m["tool_calls"][fc.name] = m["tool_calls"].get(fc.name, 0) + 1
            txt = getattr(p, "text", None)
            if txt and author:
                m["final_text"] = txt
        output = getattr(event, "output", None)  # ADK 2.x: workflow nodes emit results as event.output
        if output is not None:
            m["final_text"] = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)

    m["wall_s"] = time.perf_counter() - t0
    m["cost_usd"] = m["in_tok"] * PRICE_IN + (m["out_tok"] + m["thought_tok"]) * PRICE_OUT
    coordination = COORDINATION_TOOLS | agent_names(root)
    m["coordination_calls"] = sum(v for k, v in m["tool_calls"].items() if k in coordination)
    m["work_calls"] = sum(v for k, v in m["tool_calls"].items() if k not in coordination)

    final = await runner.session_service.get_session(app_name="bench", user_id="u", session_id=session.id)
    state = dict(final.state) if final else {}
    return m, state


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--example", default="calculator")
    ap.add_argument("--reps", type=int, default=N)
    ap.add_argument("--adk2", action="store_true", help="benchmark the 4 ADK 2.x variants (needs ADK 2.x)")
    ap.add_argument("--patterns", default=None, help="comma-separated subset of patterns to run")
    ap.add_argument("--out", default=None,
                    help="default: benchmark/results[_adk2].jsonl (calculator) or benchmark/results[_adk2]_<example>.jsonl")
    args = ap.parse_args()

    tag = "_adk2" if args.adk2 else ""
    if args.example == "calculator":
        patterns, ladder, guard, grade = load_calculator(args.adk2)
        out = Path(args.out or REPO / "benchmark" / f"results{tag}.jsonl")
    else:
        patterns, ladder, guard, grade = load_example(args.example, args.adk2)
        out = Path(args.out or REPO / "benchmark" / f"results{tag}_{args.example}.jsonl")

    if args.patterns:
        wanted = args.patterns.split(",")
        unknown = [p for p in wanted if p not in patterns]
        if unknown:
            raise SystemExit(f"unknown patterns {unknown}; available: {list(patterns)}")
        patterns = {p: patterns[p] for p in wanted}

    warmups = [(pat, ladder[0], -1) for pat in patterns for _ in range(WARMUP)]
    grid = [(pat, case, rep)
            for pat in patterns
            for case in (ladder + guard)
            for rep in range(args.reps)]
    random.shuffle(grid)
    jobs = warmups + grid

    with open(out, "w") as f:
        for pat, case, rep in jobs:
            m, state = await one_run(patterns[pat], case["input"])
            correct = grade(case, m["final_text"], {**m, "state": state})
            expected = case["expected"]
            rec = {"example": args.example, "pattern": pat, "rung": case["id"], "ops": case["complexity"],
                   "rep": rep, "expected": sorted(expected) if isinstance(expected, set) else expected,
                   "correct": correct, **m}
            if rep >= 0:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
            print(f'{pat:22} {case["id"]:12} rep{rep:>2} '
                  f'calls={m["llm_calls"]:>2} in={m["in_tok"]:>6} out={m["out_tok"]:>5} think={m["thought_tok"]:>5} '
                  f'coord={m["coordination_calls"]:>2} work={m["work_calls"]:>2} '
                  f'{m["wall_s"]:>5.1f}s ${m["cost_usd"]:.5f} ok={correct}')
    print(f"\nWrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
