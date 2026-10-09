"""Benchmark cases for the writer/critic loop.

`complexity` is the number of hard constraints in the brief. More constraints
mean more revision rounds, and each round costs the multi-agent pattern two
extra routing calls. The guard case is unsatisfiable on purpose: it checks that
each pattern terminates (and how much it spends) when approval never comes.
"""

import re

from examples.writer_critic.tools import check, parse_constraints

PRODUCT = "Fiber 500, a home fiber internet plan with 500 Mbps symmetric speed, priced at $24.990 per month."

CONSTRAINT_POOL = [
    "max_words: 45",
    "must_include: 500 Mbps; $24.990",
    "must_not_include: cheap; best; unlimited",
    "end_with: question",
    "start_with: Meet",
    "max_sentences: 3",
    "forbid_char: !",
    "min_words: 30",
]


def _brief(constraints: list[str]) -> str:
    lines = "\n".join(f"- {c}" for c in constraints)
    return f"Write a short product description for: {PRODUCT}\nConstraints:\n{lines}"


def _case(case_id, n):
    return {"id": case_id, "complexity": n, "input": _brief(CONSTRAINT_POOL[:n]),
            "expected": {"status": "APPROVED"}}


LADDER = [_case("W2", 2), _case("W4", 4), _case("W6", 6), _case("W8", 8)]

GUARD = [
    {"id": "W_IMPOSSIBLE", "complexity": 2,
     "input": _brief(["min_words: 60", "max_words: 40"]),
     "expected": {"status": "NOT APPROVED"}},
]


def grade(case: dict, final_text: str, metrics: dict) -> bool:
    """Correct iff the reported status is the expected one and, when approved,
    the presented draft really passes every constraint (checked in code)."""
    text = final_text or ""
    m = re.search(r"STATUS:\s*(NOT APPROVED|APPROVED)", text)
    if not m or m.group(1) != case["expected"]["status"]:
        return False
    if m.group(1) == "NOT APPROVED":
        return True
    draft = text.split("FINAL DRAFT:", 1)[-1].strip().strip('"')
    return not check(parse_constraints(case["input"]), draft)
