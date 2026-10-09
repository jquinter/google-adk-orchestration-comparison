"""Writer/critic — ADK 2.x Workflow graph.

Translation of `examples/writer_critic/workflow` (LoopAgent + exit_loop +
Presenter). The critic only ever ran a deterministic check, so in the graph it
is a code node; the loop is a routed cycle, bounded by a counter in state:

    START -> intake -> writer (LLM) -> critic --revise--> writer   (cycle)
                                         \--default--> present

No `exit_loop`, so no LLM can end the loop early or late, and the final draft
is always presented (the "silent loop exit" cannot happen).
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from examples.common import graceful_plugin  # noqa: E402
from examples.writer_critic.specialists import make_specialists  # noqa: E402
from examples.writer_critic.tools import check, parse_constraints  # noqa: E402
from adk2.common import as_text  # noqa: E402
from google.adk import Context, Workflow  # noqa: E402
from google.adk.apps.app import App  # noqa: E402
from google.adk.workflow import DEFAULT_ROUTE, START  # noqa: E402

MAX_ROUNDS = 5

writer, _critic = make_specialists("single_turn")


def intake(ctx: Context, node_input) -> str:
    ctx.state.update({"brief": as_text(node_input), "rounds": 0})
    return "Write the first draft."


def critic(ctx: Context, node_input, brief: str, rounds: int, draft: str = "") -> str:
    """Deterministic review (same check as the check_draft tool), no LLM call."""
    violations = check(parse_constraints(brief), draft) if draft else ["no draft saved yet"]
    ctx.state.update({"review": {"passed": not violations, "violations": violations}, "rounds": rounds + 1})
    ctx.route = "revise" if violations and rounds + 1 < MAX_ROUNDS else "done"
    return "Revise the draft. Violations:\n" + "\n".join(f"- {v}" for v in violations)


def present(node_input, review: dict, draft: str = "") -> str:
    status = "APPROVED" if review.get("passed") else "NOT APPROVED"
    return f"STATUS: {status}\nFINAL DRAFT:\n{draft}"


root_agent = Workflow(
    name="copywriting_graph",
    description="Write (LLM) -> check (code), until approved or the round limit.",
    edges=[
        (START, intake, writer, critic),
        (critic, {"revise": writer, DEFAULT_ROUTE: present}),
    ],
)

plugin = graceful_plugin()
plugin.apply_429_interceptor(writer)

app = App(name="workflow_graph", root_agent=root_agent, plugins=[plugin])
