"""Writer/critic — workflow pattern.

A LoopAgent iterates writer -> critic with a hard `max_iterations` bound; the
critic ends it with `exit_loop`. A code-only presenter then prints the result
from state, which avoids the "silent loop exit" failure (exit_loop closing the
run before the final draft is shown) at the cost of zero LLM calls.
"""

import os
import sys
from typing import AsyncGenerator

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from examples.common import graceful_plugin  # noqa: E402
from examples.writer_critic.specialists import make_specialists  # noqa: E402
from google.adk.agents import BaseAgent, LoopAgent, SequentialAgent  # noqa: E402
from google.adk.agents.invocation_context import InvocationContext  # noqa: E402
from google.adk.apps.app import App  # noqa: E402
from google.adk.events import Event  # noqa: E402
from google.genai import types  # noqa: E402

MAX_ROUNDS = 5


class Presenter(BaseAgent):
    """Prints the final status and draft from state. Pure code, no LLM call."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        status = "APPROVED" if state.get("review", {}).get("passed") else "NOT APPROVED"
        text = f"STATUS: {status}\nFINAL DRAFT:\n{state.get('draft', '')}"
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(role="model", parts=[types.Part(text=text)]),
        )


writer_critic_loop = LoopAgent(
    name="writer_critic_loop",
    max_iterations=MAX_ROUNDS,
    sub_agents=make_specialists("workflow"),
)

root_agent = SequentialAgent(
    name="copywriting_pipeline",
    description="Iterate writer -> critic until approved (or the bound is hit), then present.",
    sub_agents=[writer_critic_loop, Presenter(name="presenter")],
)

plugin = graceful_plugin()
plugin.apply_429_interceptor(writer_critic_loop)

app = App(name="writer_critic_workflow", root_agent=root_agent, plugins=[plugin])
