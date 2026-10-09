"""The four support teams, built identically for both patterns.

Only the hand-off line differs: in the multi-agent pattern a specialist can
report back what it discovered, so the coordinator can route again; in the
workflow the route was fixed up-front by the triage step.
"""

from google.adk import Agent

from examples.common import (
    DETERMINISTIC, log_model_response, log_query_to_model, model,
)
from examples.support_triage.tools import (
    check_return_eligibility, check_service_status, create_payment_plan, create_return_label,
    escalate_to_human, issue_refund, lookup_account, run_line_diagnostics, schedule_technician,
)

COORDINATOR = "support_coordinator"


def _handoff(pattern: str) -> str:
    if pattern == "multiagent":
        return (f"- When you are done, transfer control back to the '{COORDINATOR}' agent using the "
                "'transfer_to_agent' tool, including in your reply anything you discovered that another team must handle.")
    return "- If part of the request belongs to another team, mention it in one line; do NOT attempt it."


def make_specialists(pattern: str) -> list[Agent]:
    """pattern: "multiagent" (transfer back), "workflow" (code dispatcher) or
    "single_turn" (ADK 2.x: called like a function, reports back in its reply)."""
    common = dict(
        generate_content_config=DETERMINISTIC,
        before_model_callback=log_query_to_model,
        after_model_callback=log_model_response,
    )
    if pattern == "single_turn":
        common.update(disallow_transfer_to_parent=True, disallow_transfer_to_peers=True)
    scope = "- Only handle the part of the request that is in your scope."

    billing = Agent(
        name="billing",
        model=model(),
        description="Handles charges, refunds of duplicate charges, overdue balances and payment plans.",
        instruction=f"""
        - You are the billing specialist of an internet provider.
        - Use 'lookup_account' to inspect the customer's charges and balance.
        - If the customer was charged twice (two charges with same amount and date), refund ONE of them with 'issue_refund'.
        - If the service is suspended for non-payment, offer and create a 3-installment plan with 'create_payment_plan'.
        {scope}
        - Reply with one line starting with "RESOLUTION:".
        {_handoff(pattern)}
        """,
        tools=[lookup_account, issue_refund, create_payment_plan],
        **common,
    )

    technical = Agent(
        name="technical",
        model=model(),
        description="Handles connectivity problems and faulty devices.",
        instruction=f"""
        - You are the technical support specialist of an internet provider.
        - First call 'check_service_status'. If the service is not active, do NOT run diagnostics: report the status and its note.
        - If the service is active, call 'run_line_diagnostics'. If a fault is detected, book a visit with 'schedule_technician'.
        {scope}
        - Reply with one line starting with "RESOLUTION:".
        {_handoff(pattern)}
        """,
        tools=[check_service_status, run_line_diagnostics, schedule_technician],
        **common,
    )

    returns = Agent(
        name="returns",
        model=model(),
        description="Handles returns of purchased equipment.",
        instruction=f"""
        - You are the returns specialist of an internet provider.
        - Call 'check_return_eligibility' for the order.
        - If eligible, create the label with 'create_return_label'. If not, explain why and relay any note from the tool.
        {scope}
        - Reply with one line starting with "RESOLUTION:".
        {_handoff(pattern)}
        """,
        tools=[check_return_eligibility, create_return_label],
        **common,
    )

    escalation = Agent(
        name="escalation",
        model=model(),
        description="Escalates legal threats, regulator complaints or abusive situations to a human.",
        instruction=f"""
        - You are the escalation specialist.
        - Open a priority ticket with 'escalate_to_human' and tell the customer a human will contact them.
        - Reply with one line starting with "RESOLUTION:".
        {_handoff(pattern)}
        """,
        tools=[escalate_to_human],
        **common,
    )

    return [billing, technical, returns, escalation]
