"""
bench_run.py — Run the (pattern x expression x repetition) matrix and capture
metrics LIVE from ADK's event stream into results.jsonl.

Token metrics (usage_metadata) are read off each Event while it runs — where
they are guaranteed present — rather than relying on ADK persisting them to its
SQLite session store. results.jsonl is the source of truth; re-analyse it with
bench_report.py without spending another token.

Run from the repo root:
    PYTHONPATH=. .venv/bin/python benchmark/bench_run.py

Prerequisites (same as running the evaluators):
  - Valid Application Default Credentials — the agent modules initialise Cloud
    Logging on import.
  - MODEL set in each package's .env (loaded below before the agents import).

Portability note: attribute names (usage_metadata, prompt_token_count,
candidates_token_count, function_call) and the InMemoryRunner / run_async /
create_session surface follow ADK 1.x. If your version differs, adjust here.
"""

import asyncio
import json
import random
import time
from pathlib import Path

from dotenv import load_dotenv
from google.genai import types
from google.adk.runners import InMemoryRunner

# --- Load each package's .env BEFORE importing its agent -----------------------
# The agent modules call load_dotenv() and read os.getenv("MODEL") at import
# time, so MODEL must be in the environment first.
REPO = Path(__file__).resolve().parent.parent
load_dotenv(REPO / "adk_multiagent_systems" / "parent_and_subagents" / ".env")
from adk_multiagent_systems.parent_and_subagents.agent import root_agent as multiagent_root  # noqa: E402
load_dotenv(REPO / "adk_multiagent_systems" / "workflow_agents" / ".env", override=True)
from adk_multiagent_systems.workflow_agents.agent import root_agent as workflow_root  # noqa: E402

PATTERNS = {
    "multiagent": multiagent_root,
    "workflow": workflow_root,
}

# --- Complexity ladder: (id, expression, n_ops, expected_result) ---------------
LADDER = [
    ("B",  "10 / 2",                                                                                     1,  5),
    ("L1", "2 + 3 * 4 - 10 / 2",                                                                          4,  9),
    ("L2", "(12 + 8) * 5 - (10 / 2) + 4 * 6",                                                             6,  119),
    ("L3", "((12 + 8) * 5) - (10 / 2) + (4 * 6) - (50 / 5)",                                              8,  109),
    ("L4", "((12 + 8) * 5) - (10 / 2) + (4 * 6) - (50 / 5) + (100 / 4) - (7 * 3) + (18 / 2)",             14, 122),
]

# --- Guard (error path): division by zero --------------------------------------
GUARD = [
    ("G1", "10 / 0",            None, None),
    ("G2", "(4 * 6) / (5 - 5)", None, None),
]

N = 10          # repetitions per cell
WARMUP = 1      # discarded per pattern (cold start)

# Gemini 2.5 Flash, Vertex standard tier. Verified Oct 2026. UPDATE if you swap MODEL.
PRICE_IN = 0.30 / 1e6    # USD / input token
PRICE_OUT = 2.50 / 1e6   # USD / output token


async def one_run(root, expr):
    runner = InMemoryRunner(agent=root, app_name="bench")
    session = await runner.session_service.create_session(app_name="bench", user_id="u")
    msg = types.Content(role="user", parts=[types.Part(text=expr)])

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
    return m


async def main():
    warmups = [(pat, LADDER[0], -1) for pat in PATTERNS for _ in range(WARMUP)]
    grid = [(pat, rung, rep)
            for pat in PATTERNS
            for rung in (LADDER + GUARD)
            for rep in range(N)]
    random.shuffle(grid)
    jobs = warmups + grid

    out = REPO / "benchmark" / "results.jsonl"
    with open(out, "w") as f:
        for pat, rung, rep in jobs:
            name, expr, ops, expected = rung
            m = await one_run(PATTERNS[pat], expr)
            correct = None if expected is None else (str(expected) in (m["final_text"] or ""))
            rec = {"pattern": pat, "rung": name, "ops": ops, "rep": rep,
                   "expected": expected, "correct": correct, **m}
            if rep >= 0:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
            transfers = m["tool_calls"].get("transfer_to_agent", 0)
            updates = m["tool_calls"].get("update_expression", 0)
            print(f'{pat:10} {name:3} rep{rep:>2} '
                  f'calls={m["llm_calls"]:>2} in={m["in_tok"]:>6} out={m["out_tok"]:>5} '
                  f'transfer={transfers:>2} update={updates:>2} '
                  f'{m["wall_s"]:>5.1f}s ${m["cost_usd"]:.5f} ok={correct}')
    print(f"\nWrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
