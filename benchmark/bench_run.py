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

# Tool calls that coordinate rather than do work.
COORDINATION_TOOLS = {"transfer_to_agent", "exit_loop"}


def _calc_grade(case, final_text, metrics):
    expected = case["expected"]
    return None if expected is None else (str(expected) in (final_text or ""))


def load_calculator():
    # The agent modules call load_dotenv() and read os.getenv("MODEL") at import
    # time, so each package's .env must be in the environment first.
    load_dotenv(REPO / "adk_multiagent_systems" / "parent_and_subagents" / ".env")
    from adk_multiagent_systems.parent_and_subagents.agent import root_agent as multiagent_root
    load_dotenv(REPO / "adk_multiagent_systems" / "workflow_agents" / ".env", override=True)
    from adk_multiagent_systems.workflow_agents.agent import root_agent as workflow_root

    to_case = lambda t: {"id": t[0], "input": t[1], "complexity": t[2], "expected": t[3]}  # noqa: E731
    return ({"multiagent": multiagent_root, "workflow": workflow_root},
            [to_case(t) for t in CALC_LADDER], [to_case(t) for t in CALC_GUARD], _calc_grade)


def load_example(name):
    load_dotenv(REPO / ".env")
    patterns = {pat: importlib.import_module(f"examples.{name}.{pat}.agent").root_agent
                for pat in ("multiagent", "workflow")}
    cases = importlib.import_module(f"examples.{name}.cases")
    return patterns, cases.LADDER, cases.GUARD, cases.grade


async def one_run(root, text):
    runner = InMemoryRunner(agent=root, app_name="bench")
    session = await runner.session_service.create_session(app_name="bench", user_id="u")
    msg = types.Content(role="user", parts=[types.Part(text=text)])

    m = {"llm_calls": 0, "in_tok": 0, "out_tok": 0,
         "tool_calls": {}, "activations": {}, "final_text": ""}

    t0 = time.perf_counter()
    async for event in runner.run_async(user_id="u", session_id=session.id, new_message=msg):
        um = getattr(event, "usage_metadata", None)
        if um:
            m["llm_calls"] += 1
            m["in_tok"] += getattr(um, "prompt_token_count", 0) or 0
            m["out_tok"] += getattr(um, "candidates_token_count", 0) or 0
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

    m["wall_s"] = time.perf_counter() - t0
    m["cost_usd"] = m["in_tok"] * PRICE_IN + m["out_tok"] * PRICE_OUT
    m["coordination_calls"] = sum(v for k, v in m["tool_calls"].items() if k in COORDINATION_TOOLS)
    m["work_calls"] = sum(v for k, v in m["tool_calls"].items() if k not in COORDINATION_TOOLS)

    final = await runner.session_service.get_session(app_name="bench", user_id="u", session_id=session.id)
    state = dict(final.state) if final else {}
    return m, state


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--example", default="calculator")
    ap.add_argument("--reps", type=int, default=N)
    ap.add_argument("--out", default=None,
                    help="default: benchmark/results.jsonl (calculator) or benchmark/results_<example>.jsonl")
    args = ap.parse_args()

    if args.example == "calculator":
        patterns, ladder, guard, grade = load_calculator()
        out = Path(args.out or REPO / "benchmark" / "results.jsonl")
    else:
        patterns, ladder, guard, grade = load_example(args.example)
        out = Path(args.out or REPO / "benchmark" / f"results_{args.example}.jsonl")

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
            print(f'{pat:10} {case["id"]:12} rep{rep:>2} '
                  f'calls={m["llm_calls"]:>2} in={m["in_tok"]:>6} out={m["out_tok"]:>5} '
                  f'coord={m["coordination_calls"]:>2} work={m["work_calls"]:>2} '
                  f'{m["wall_s"]:>5.1f}s ${m["cost_usd"]:.5f} ok={correct}')
    print(f"\nWrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
