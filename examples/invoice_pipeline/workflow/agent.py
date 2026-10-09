"""Invoice pipeline — workflow pattern.

The order of the steps is code (a SequentialAgent), so the only LLM calls are
the ones that do actual work. Once an invoice is rejected, the remaining steps
are skipped by a before_agent_callback, without spending an LLM call on it.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from examples.common import graceful_plugin  # noqa: E402
from examples.invoice_pipeline.specialists import make_specialists  # noqa: E402
from google.adk.agents import SequentialAgent  # noqa: E402
from google.adk.apps.app import App  # noqa: E402

root_agent = SequentialAgent(
    name="invoice_pipeline",
    description="Extract -> validate -> normalize -> post, in a fixed order.",
    sub_agents=make_specialists("workflow"),
)

plugin = graceful_plugin()
plugin.apply_429_interceptor(root_agent)

app = App(name="invoice_pipeline_workflow", root_agent=root_agent, plugins=[plugin])
