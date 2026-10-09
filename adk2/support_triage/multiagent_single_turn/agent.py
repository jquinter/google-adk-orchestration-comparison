"""Support triage — ADK 2.x multi-agent with single-turn delegation.

Same coordinator and teams as `examples/support_triage/multiagent`, but the
teams are called like functions (mode="single_turn"): each call returns the
team's findings to the coordinator, which can call another team next.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from examples.common import DETERMINISTIC, graceful_plugin, model  # noqa: E402
from examples.support_triage.specialists import COORDINATOR, make_specialists  # noqa: E402
from adk2.common import single_turn  # noqa: E402
from google.adk import Agent  # noqa: E402
from google.adk.apps.app import App  # noqa: E402

root_agent = Agent(
    name=COORDINATOR,
    model=model(),
    description="Front desk of an internet provider's customer support.",
    instruction="""
        - You are the support coordinator of an internet provider.
        - The user message contains a customer id and their request.
        - Call the right team tool: 'billing', 'technical', 'returns' or 'escalation'.
          In the request, include the customer id, any order id, and the part of the request that team must handle.
        - Legal threats or complaints to regulators always go to 'escalation'.
        - Read each team's reply: if it discovered that another team must act
          (or part of the original request is still pending), call that team next.
        - When nothing is pending, give the customer a short final summary, one line per action taken.
        """,
    generate_content_config=DETERMINISTIC,
    sub_agents=single_turn(make_specialists("single_turn")),
)

plugin = graceful_plugin()
plugin.apply_429_interceptor(root_agent)

app = App(name="multiagent_single_turn", root_agent=root_agent, plugins=[plugin])
