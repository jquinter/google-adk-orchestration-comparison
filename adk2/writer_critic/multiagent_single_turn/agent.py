"""Writer/critic — ADK 2.x multi-agent with single-turn delegation.

Same editor, writer and critic as `examples/writer_critic/multiagent`, but the
writer and critic are called like functions (mode="single_turn"), so the
critic's verdict always comes back to the editor (in 1.x the critic often
answered "APPROVED" without transferring back, and the run ended there).
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from examples.common import DETERMINISTIC, graceful_plugin, model  # noqa: E402
from examples.writer_critic.specialists import COORDINATOR, make_specialists  # noqa: E402
from adk2.common import single_turn, stash_user_input  # noqa: E402
from google.adk import Agent  # noqa: E402
from google.adk.apps.app import App  # noqa: E402

MAX_ROUNDS = 5

root_agent = Agent(
    name=COORDINATOR,
    model=model(),
    description="Editor that iterates a draft with a writer and a critic.",
    instruction=f"""
        - You are the editor. The user provided a brief with hard constraints (the writer and critic can read it).
        - Alternate: call the 'writer' tool to produce a draft, then the 'critic' tool to check it.
        - If the critic says "APPROVED", stop iterating.
        - If not, call the writer again to revise. Stop after at most {MAX_ROUNDS} rounds even if not approved.
        - The latest saved draft is: {{draft?}}
        - The latest review is: {{review?}}
        - When you stop, your final answer must have exactly three parts, in this order:
          1. "STATUS: APPROVED" if the latest review passed, otherwise "STATUS: NOT APPROVED"
          2. a line with "FINAL DRAFT:"
          3. the latest saved draft, copied verbatim
        """,
    generate_content_config=DETERMINISTIC,
    before_agent_callback=stash_user_input("brief"),
    sub_agents=single_turn(make_specialists("single_turn")),
)

plugin = graceful_plugin()
plugin.apply_429_interceptor(root_agent)

app = App(name="multiagent_single_turn", root_agent=root_agent, plugins=[plugin])
