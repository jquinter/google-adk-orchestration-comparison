"""Writer and critic, built identically for both patterns.

Only what happens after each turn differs: in the multi-agent pattern both
report back to a coordinator that decides whether to iterate; in the workflow
a LoopAgent iterates and the critic ends the loop with `exit_loop`.
"""

from google.adk import Agent
from google.adk.tools import exit_loop

from examples.common import (
    DETERMINISTIC, log_model_response, log_query_to_model, model,
)
from examples.writer_critic.tools import check_draft, save_draft

COORDINATOR = "editor"


def make_specialists(pattern: str) -> list[Agent]:
    common = dict(
        generate_content_config=DETERMINISTIC,
        before_model_callback=log_query_to_model,
        after_model_callback=log_model_response,
    )
    back = f"- Then transfer control back to the '{COORDINATOR}' agent using the 'transfer_to_agent' tool."

    writer = Agent(
        name="writer",
        model=model(),
        description="Writes or revises the draft so it satisfies the brief.",
        instruction=f"""
        - You are a marketing copywriter.
        - The user's brief describes the product and lists hard constraints.
        - Current draft (empty on the first round): {{draft?}}
        - Critic's last review (empty on the first round): {{review?}}
        - Write a new draft that satisfies EVERY constraint, fixing each violation listed in the review.
        - Save the full draft text with the 'save_draft' tool, exactly once.
        {back if pattern == "multiagent" else "- Then end your turn."}
        """,
        tools=[save_draft],
        **common,
    )

    if pattern == "multiagent":
        critic_outcome = f"""
        - If it passed, output "APPROVED".
        - Otherwise, output the list of violations as feedback for the writer.
        {back}"""
        critic_tools = [check_draft]
    else:
        critic_outcome = """
        - If it passed, output "APPROVED" and call the 'exit_loop' tool.
        - Otherwise, output the list of violations as feedback for the writer and end your turn."""
        critic_tools = [check_draft, exit_loop]

    critic = Agent(
        name="critic",
        model=model(),
        description="Checks the draft against the brief's constraints.",
        instruction=f"""
        - You are the reviewer. You do not rewrite the draft.
        - Call the 'check_draft' tool exactly once.{critic_outcome}
        """,
        tools=critic_tools,
        **common,
    )

    if pattern == "workflow":
        for agent in (writer, critic):
            agent.disallow_transfer_to_parent = True
            agent.disallow_transfer_to_peers = True

    return [writer, critic]
