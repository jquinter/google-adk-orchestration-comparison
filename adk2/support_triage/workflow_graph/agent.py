"""Support triage — ADK 2.x Workflow graph with code-controlled re-routing.

Translation of `examples/support_triage/workflow` (classify once + Dispatcher).
That version fixes the route before any tool runs, so a cause discovered
mid-way ("internet down" -> suspended for non-payment -> billing) is lost.

Here every specialist returns a structured report (`output_schema`) that says
which team, if any, must act next. A code node reads it and routes again:

    START -> intake -> triage (LLM) -> dispatch --billing----> billing ----\
                                          ^     --technical--> technical --+
                                          |     --returns----> returns ----+
                                          |     --escalation-> escalation -+
                                          |                                |
                                          \--------------------------------/
                                        dispatch --default (done)--> finish

The LLM decides *what* it found; code decides *where* the ticket goes next,
with a hard bound on the number of hand-offs.
"""

import os
import sys
from typing import Literal

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from examples.common import (  # noqa: E402
    DETERMINISTIC, graceful_plugin, log_model_response, log_query_to_model, model,
)
from examples.support_triage.specialists import make_specialists  # noqa: E402
from adk2.common import as_text  # noqa: E402
from google.adk import Agent, Context, Workflow  # noqa: E402
from google.adk.apps.app import App  # noqa: E402
from google.adk.workflow import DEFAULT_ROUTE, START  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

Team = Literal["billing", "technical", "returns", "escalation"]
MAX_HANDOFFS = 4


class Route(BaseModel):
    categories: list[Team] = Field(description="Teams that must handle the request, in order.")


class Report(BaseModel):
    resolution: str = Field(description='One line starting with "RESOLUTION:" describing what you did.')
    handoff_to: Literal["billing", "technical", "returns", "escalation", "none"] = Field(
        description="Team that must act next because of something you discovered, or 'none'.")


triage = Agent(
    name="triage",
    model=model(),
    description="Classifies a support request into the teams that must handle it.",
    instruction="""
        - You are the triage step of an internet provider's support.
        - Read the customer's request and decide which teams must handle it, in order:
          'billing' (charges, refunds, unpaid balances), 'technical' (connectivity, faulty devices),
          'returns' (returning purchased equipment), 'escalation' (legal threats, regulator complaints).
        """,
    output_schema=Route,
    generate_content_config=DETERMINISTIC,
    before_model_callback=log_query_to_model,
    after_model_callback=log_model_response,
)

specialists = make_specialists("single_turn")
for specialist in specialists:
    specialist.output_schema = Report


def intake(ctx: Context, node_input) -> str:
    request = as_text(node_input)
    ctx.state.update({"raw_input": request, "queue": [], "visited": [], "findings": []})
    return request


def dispatch(ctx: Context, node_input, raw_input: str, queue: list, visited: list, findings: list) -> str:
    """Route to the next pending team. Pure code: reads the triage plan or a specialist's report."""
    if isinstance(node_input, dict) and "categories" in node_input:       # from triage
        queue = list(node_input["categories"])
    elif isinstance(node_input, dict) and "resolution" in node_input:     # from a specialist
        findings = findings + [node_input["resolution"]]
        team = node_input.get("handoff_to", "none")
        if team != "none" and team not in visited and team not in queue:
            queue = queue + [team]
    pending = [t for t in queue if t not in visited]
    if not pending or len(visited) >= MAX_HANDOFFS:
        ctx.state.update({"queue": queue, "findings": findings})
        ctx.route = "done"
        return "\n".join(findings)
    team = pending[0]
    ctx.state.update({"queue": queue, "visited": visited + [team], "findings": findings})
    ctx.route = team
    notes = "\n".join(f"- {f}" for f in findings) or "- none yet"
    return f"Customer request: {raw_input}\nFindings from other teams so far:\n{notes}"


def finish(node_input, findings: list) -> str:
    return "\n".join(findings) or "RESOLUTION: no action taken."


root_agent = Workflow(
    name="support_graph",
    description="Classify, dispatch in code, and re-route on what specialists discover.",
    edges=[
        (START, intake, triage, dispatch),
        (dispatch, {s.name: s for s in specialists} | {DEFAULT_ROUTE: finish}),  # "done" -> default
        *[(s, dispatch) for s in specialists],
    ],
)

plugin = graceful_plugin()
for agent in (triage, *specialists):
    plugin.apply_429_interceptor(agent)

app = App(name="workflow_graph", root_agent=root_agent, plugins=[plugin])
