"""Support triage — multi-agent pattern.

The coordinator routes, reads what each specialist discovered, and can route
again. That re-routing is what a ticket like "my internet is down" needs when
the real cause (an unpaid balance) only shows up after a tool call.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from examples.common import DETERMINISTIC, graceful_plugin, model  # noqa: E402
from examples.support_triage.specialists import COORDINATOR, make_specialists  # noqa: E402
from google.adk import Agent  # noqa: E402
from google.adk.apps.app import App  # noqa: E402

root_agent = Agent(
    name=COORDINATOR,
    model=model(),
    description="Front desk of an internet provider's customer support.",
    instruction="""
        - You are the support coordinator of an internet provider.
        - The user message contains a customer id and their request.
        - Route the request to the right specialist: 'billing', 'technical', 'returns' or 'escalation'.
        - Legal threats or complaints to regulators always go to 'escalation'.
        - When a specialist returns, read its findings: if it discovered that another team must act
          (or part of the original request is still pending), route to that team next.
        - When nothing is pending, give the customer a short final summary, one line per action taken.
        """,
    generate_content_config=DETERMINISTIC,
    sub_agents=make_specialists("multiagent"),
)

plugin = graceful_plugin()
plugin.apply_429_interceptor(root_agent)

app = App(name="support_triage_multiagent", root_agent=root_agent, plugins=[plugin])
