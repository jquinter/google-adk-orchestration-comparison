"""Writer/critic — multi-agent pattern.

An LLM editor alternates writer and critic and decides when to stop. Every
round costs two extra routing calls, and the stop condition lives in a prompt.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from examples.common import DETERMINISTIC, graceful_plugin, model  # noqa: E402
from examples.writer_critic.specialists import COORDINATOR, make_specialists  # noqa: E402
from google.adk import Agent  # noqa: E402
from google.adk.apps.app import App  # noqa: E402

MAX_ROUNDS = 5

root_agent = Agent(
    name=COORDINATOR,
    model=model(),
    description="Editor that iterates a draft with a writer and a critic.",
    instruction=f"""
        - You are the editor. The user provides a brief with hard constraints.
        - Alternate: transfer to 'writer' to produce a draft, then to 'critic' to check it.
        - If the critic says "APPROVED", stop iterating.
        - If not, send the writer back to revise. Stop after at most {MAX_ROUNDS} rounds even if not approved.
        - The latest saved draft is: {{draft?}}
        - The latest review is: {{review?}}
        - When you stop, your final answer must have exactly three parts, in this order:
          1. "STATUS: APPROVED" if the latest review passed, otherwise "STATUS: NOT APPROVED"
          2. a line with "FINAL DRAFT:"
          3. the latest saved draft, copied verbatim
        """,
    generate_content_config=DETERMINISTIC,
    sub_agents=make_specialists("multiagent"),
)

plugin = graceful_plugin()
plugin.apply_429_interceptor(root_agent)

app = App(name="writer_critic_multiagent", root_agent=root_agent, plugins=[plugin])
