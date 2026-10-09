"""Invoice pipeline — multi-agent pattern.

An LLM coordinator decides, step by step, which specialist runs next. The
steps are always the same four, so every routing decision is an LLM call that
re-derives an order the code already knew.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from examples.common import DETERMINISTIC, graceful_plugin, model  # noqa: E402
from examples.invoice_pipeline.specialists import COORDINATOR, make_specialists  # noqa: E402
from google.adk import Agent  # noqa: E402
from google.adk.apps.app import App  # noqa: E402

root_agent = Agent(
    name=COORDINATOR,
    model=model(),
    description="Coordinates the processing of a supplier invoice.",
    instruction="""
        - You are the coordinator of an accounts-payable pipeline.
        - The user will provide the raw text of a supplier invoice.
        - Route the work to the specialists, one at a time: 'extractor' -> 'validator' -> 'normalizer' -> 'accountant'.
        - If the 'validator' reports "STATUS: REJECTED", stop routing.
        - When the 'accountant' has posted the journal entry, stop routing.
        - Validation result so far: {validation?}
        - Posted journal entry so far: {journal_entry?}
        - Your final answer must be exactly ONE line, with every field filled in:
          - rejected: "STATUS: REJECTED | REASONS: <reasons from the validation result, comma-separated>"
          - approved: "STATUS: APPROVED | TOTAL: <total from the journal entry> | ENTRY: <entry_id from the journal entry>"
        """,
    generate_content_config=DETERMINISTIC,
    sub_agents=make_specialists("multiagent"),
)

plugin = graceful_plugin()
plugin.apply_429_interceptor(root_agent)

app = App(name="invoice_pipeline_multiagent", root_agent=root_agent, plugins=[plugin])
