"""Benchmark cases for support triage.

`complexity` is the number of teams that must act. The interesting cases are
the "discovery" ones (D*): the team that must act is only revealed by a tool
result, so a route fixed up-front sends the ticket to the wrong team.

Grading uses the actions recorded in session state (refunds, labels, visits,
payment plans, escalations): the right set, nothing more.
"""

LADDER = [
    {"id": "T_BILL", "complexity": 1, "expected": {"refund"},
     "input": "Customer C100: I was charged twice for September, please fix it."},
    {"id": "T_TECH", "complexity": 1, "expected": {"technician"},
     "input": "Customer C200: my internet keeps dropping every few minutes since yesterday."},
    {"id": "T_RET", "complexity": 1, "expected": {"return_label"},
     "input": "Customer C300: I'd like to return the router from order O-552, I don't need it anymore."},
    {"id": "M_BILL_RET", "complexity": 2, "expected": {"refund", "return_label"},
     "input": "Customer C400: I got charged twice this month, and I also want to return the modem from order O-553."},
    {"id": "D_SUSP", "complexity": 2, "expected": {"payment_plan"},
     "input": "Customer C500: my internet is completely down, nothing works. Please help."},
    {"id": "D_RET_TECH", "complexity": 2, "expected": {"technician"},
     "input": "Customer C600: I want to return the router from order O-600, it doesn't work properly."},
]

GUARD = [
    {"id": "E_LEGAL", "complexity": 1, "expected": {"escalation"},
     "input": "Customer C700: this is the third outage this month. I'm filing a complaint with SUBTEL and talking to my lawyer."},
]


def grade(case: dict, final_text: str, metrics: dict) -> bool:
    """Correct iff exactly the expected set of actions was taken."""
    actions = {a["action"] for a in metrics.get("state", {}).get("actions", [])}
    return actions == case["expected"]
