"""Invoice pipeline — ADK 2.x multi-agent with single-turn delegation.

Same coordinator and specialists as `examples/invoice_pipeline/multiagent`, but
the specialists are called like functions (mode="single_turn") and always
return control. The raw invoice travels through state, not through the
coordinator's arguments, so the coordinator never re-types it.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from examples.common import DETERMINISTIC, graceful_plugin, model  # noqa: E402
from examples.invoice_pipeline.specialists import COORDINATOR, make_specialists  # noqa: E402
from adk2.common import single_turn, stash_user_input  # noqa: E402
from google.adk import Agent  # noqa: E402
from google.adk.apps.app import App  # noqa: E402

root_agent = Agent(
    name=COORDINATOR,
    model=model(),
    description="Coordinates the processing of a supplier invoice.",
    instruction="""
        - You are the coordinator of an accounts-payable pipeline.
        - The user provided the raw text of a supplier invoice (the specialists can already read it).
        - Call the specialist tools one at a time: 'extractor' -> 'validator' -> 'normalizer' -> 'accountant'.
        - If the 'validator' reports "STATUS: REJECTED", stop calling specialists.
        - When the 'accountant' has posted the journal entry, stop calling specialists.
        - Validation result so far: {validation?}
        - Posted journal entry so far: {journal_entry?}
        - Your final answer must be exactly ONE line, with every field filled in:
          - rejected: "STATUS: REJECTED | REASONS: <reasons from the validation result, comma-separated>"
          - approved: "STATUS: APPROVED | TOTAL: <total from the journal entry> | ENTRY: <entry_id from the journal entry>"
        """,
    generate_content_config=DETERMINISTIC,
    before_agent_callback=stash_user_input("raw_input"),
    sub_agents=single_turn(make_specialists("single_turn")),
)

plugin = graceful_plugin()
plugin.apply_429_interceptor(root_agent)

app = App(name="multiagent_single_turn", root_agent=root_agent, plugins=[plugin])
