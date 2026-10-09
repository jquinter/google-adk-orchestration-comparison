"""Helpers for the ADK 2.x variants (shared env/model setup lives in examples/common.py)."""

from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.genai import types


def single_turn(agents):
    """Turn specialists into single-turn delegates: the coordinator calls each one
    like a function tool and always gets control back (no transfer_to_agent)."""
    for agent in agents:
        agent.mode = "single_turn"
    return agents


def stash_user_input(key: str):
    """before_agent_callback that copies the user's message into state[key].

    Single-turn specialists and workflow nodes do not see the conversation, so
    data they need travels through state instead of through the transcript.
    """
    def callback(callback_context: CallbackContext) -> Optional[types.Content]:
        if key not in callback_context.state and callback_context.user_content:
            parts = callback_context.user_content.parts or []
            callback_context.state[key] = "".join(p.text or "" for p in parts)
        return None
    return callback


def as_text(node_input) -> str:
    """Workflow nodes may receive a str, a Content or a dict; normalize to text."""
    if isinstance(node_input, types.Content):
        return "".join(p.text or "" for p in (node_input.parts or []))
    return node_input if isinstance(node_input, str) else str(node_input)
