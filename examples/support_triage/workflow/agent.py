"""Support triage — workflow pattern.

An LLM classifies the request once (possibly into several teams), then code
dispatches to those teams in order. Cheap and predictable, but the route is
fixed before any tool runs: a cause discovered mid-way cannot change it.
"""

import os
import sys
from typing import AsyncGenerator

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from examples.common import (  # noqa: E402
    DETERMINISTIC, graceful_plugin, log_model_response, log_query_to_model, model,
)
from examples.support_triage.specialists import make_specialists  # noqa: E402
from examples.support_triage.tools import set_route  # noqa: E402
from google.adk import Agent  # noqa: E402
from google.adk.agents import BaseAgent, SequentialAgent  # noqa: E402
from google.adk.agents.invocation_context import InvocationContext  # noqa: E402
from google.adk.apps.app import App  # noqa: E402
from google.adk.events import Event  # noqa: E402


class Dispatcher(BaseAgent):
    """Runs the specialists listed in state['route'], in order. Pure code, no LLM call."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        teams = {agent.name: agent for agent in self.sub_agents}
        for category in ctx.session.state.get("route", []):
            async for event in teams[category].run_async(ctx):
                yield event


triage = Agent(
    name="triage",
    model=model(),
    description="Classifies a support request into the teams that must handle it.",
    instruction="""
        - You are the triage step of an internet provider's support.
        - Read the customer's request and decide which teams must handle it, in order:
          'billing' (charges, refunds, unpaid balances), 'technical' (connectivity, faulty devices),
          'returns' (returning purchased equipment), 'escalation' (legal threats, regulator complaints).
        - Save the list with the 'set_route' tool, then end your turn.
        """,
    generate_content_config=DETERMINISTIC,
    before_model_callback=log_query_to_model,
    after_model_callback=log_model_response,
    tools=[set_route],
)

root_agent = SequentialAgent(
    name="support_pipeline",
    description="Classify once, then dispatch to the selected teams in code.",
    sub_agents=[triage, Dispatcher(name="dispatcher", sub_agents=make_specialists("workflow"))],
)

plugin = graceful_plugin()
plugin.apply_429_interceptor(triage)
plugin.apply_429_interceptor(root_agent.sub_agents[1])

app = App(name="support_triage_workflow", root_agent=root_agent, plugins=[plugin])
