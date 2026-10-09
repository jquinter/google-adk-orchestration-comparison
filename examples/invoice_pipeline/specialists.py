"""The four invoice specialists, built identically for both patterns.

Only the last line of each instruction (what to do when finished) depends on
the orchestration pattern, so any difference in the benchmark comes from the
coordination, not from the work prompts.
"""

from typing import Optional

from google.adk import Agent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from examples.common import (
    DETERMINISTIC, log_model_response, log_query_to_model, model,
)
from examples.invoice_pipeline.tools import (
    EXPENSE_ACCOUNTS, post_journal_entry, record_invoice, record_normalized, validate_invoice,
)

COORDINATOR = "invoice_coordinator"


def _handoff(pattern: str) -> str:
    if pattern == "multiagent":
        return f"- When you are done, transfer control back to the '{COORDINATOR}' agent using the 'transfer_to_agent' tool."
    return "- When you are done, end your turn."


def rejection_line(validation: dict) -> str:
    return f"STATUS: REJECTED | REASONS: {', '.join(validation.get('reasons', []))}"


def halt_if_rejected(callback_context: CallbackContext) -> Optional[types.Content]:
    """Workflow guard: skip this step (no LLM call) once validation rejected the invoice.

    Returning content from a before_agent_callback skips only *this* agent (it
    runs on a copy of the invocation context), so the guard goes on every step
    after the validator.
    """
    validation = callback_context.state.get("validation", {})
    if validation.get("status") == "REJECTED":
        return types.Content(role="model", parts=[types.Part(text=rejection_line(validation))])
    return None


def make_specialists(pattern: str) -> list[Agent]:
    """pattern: "multiagent" (transfer back), "workflow" (SequentialAgent) or
    "single_turn" (ADK 2.x: no transcript; the raw invoice comes from state)."""
    common = dict(
        generate_content_config=DETERMINISTIC,
        before_model_callback=log_query_to_model,
        after_model_callback=log_model_response,
    )
    if pattern in ("workflow", "single_turn"):
        # The order is code (or a function-like call); specialists never transfer.
        common.update(disallow_transfer_to_parent=True, disallow_transfer_to_peers=True)

    extractor = Agent(
        name="extractor",
        model=model(),
        description="Extracts structured fields from a raw invoice text.",
        instruction=f"""
        - You are the invoice extraction specialist.
        {"- The raw invoice text is: {raw_input?}" if pattern == "single_turn" else "- Read the raw invoice text provided by the user."}
        - Extract the issuer RUT and name, invoice number, issue date, every line item
          (description, quantity, unit price) and the net, VAT (IVA) and total amounts.
        - Copy values exactly as printed: do NOT fix, recompute or round anything.
        - Amounts are Chilean pesos: drop the '$' sign and the '.' thousands separators.
        - Save them with the 'record_invoice' tool, then output a one-line summary.
        {_handoff(pattern)}
        """,
        tools=[record_invoice],
        **common,
    )

    validator = Agent(
        name="validator",
        model=model(),
        description="Validates the extracted invoice (RUT, line totals, VAT, total).",
        instruction=f"""
        - You are the invoice validation specialist.
        - Call the 'validate_invoice' tool exactly once.
        - If it returns APPROVED, output "Validation passed."
        - If it returns REJECTED, output exactly: "STATUS: REJECTED | REASONS: <reasons, comma-separated>"
        {_handoff(pattern)}
        """,
        tools=[validate_invoice],
        **common,
    )

    normalizer = Agent(
        name="normalizer",
        model=model(),
        description="Normalizes the issue date and classifies each line item into an expense category.",
        instruction=f"""
        - You are the normalization specialist.
        - The recorded invoice is: {{invoice?}}
        - Convert the issue date to ISO format (YYYY-MM-DD).
        - Classify each line item, in order, into exactly one of: {', '.join(EXPENSE_ACCOUNTS)}.
        - Save them with the 'record_normalized' tool, then output a one-line summary.
        {_handoff(pattern)}
        """,
        tools=[record_normalized],
        **common,
    )

    accountant = Agent(
        name="accountant",
        model=model(),
        description="Posts the journal entry for a validated, normalized invoice.",
        instruction=f"""
        - You are the accounting specialist.
        - Call the 'post_journal_entry' tool exactly once.
        - Output exactly: "STATUS: APPROVED | TOTAL: <total> | ENTRY: <entry_id>"
        {_handoff(pattern)}
        """,
        tools=[post_journal_entry],
        **common,
    )

    if pattern == "workflow":
        normalizer.before_agent_callback = halt_if_rejected
        accountant.before_agent_callback = halt_if_rejected

    return [extractor, validator, normalizer, accountant]
