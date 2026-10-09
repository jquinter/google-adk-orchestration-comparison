"""Case 0a — a single agent with a one-line instruction (the naive baseline).

No orchestration at all: one LLM call evaluates the whole expression. This is
the control group for the instruction-structure comparison with
`baseline/structured_agent`.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from examples.common import DETERMINISTIC, graceful_plugin, model  # noqa: E402
from google.adk import Agent  # noqa: E402
from google.adk.apps.app import App  # noqa: E402

root_agent = Agent(
    name="naive_calculator",
    model=model(),
    description="Evaluates arithmetic expressions.",
    instruction="Evaluate the arithmetic expression the user gives you.",
    generate_content_config=DETERMINISTIC,
)

plugin = graceful_plugin()
plugin.apply_429_interceptor(root_agent)

app = App(name="naive_agent", root_agent=root_agent, plugins=[plugin])
