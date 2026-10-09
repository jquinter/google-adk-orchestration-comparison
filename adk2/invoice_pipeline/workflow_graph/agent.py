"""Invoice pipeline — ADK 2.x Workflow graph.

Translation of `examples/invoice_pipeline/workflow` (SequentialAgent). In the
graph, deterministic steps are nodes in their own right instead of LLM agents
whose only job is to call one tool: validation and posting become code, and
the rejection short-circuit is a routed edge instead of a before_agent_callback.

    START -> intake -> extractor (LLM) -> validate --approved--> normalizer (LLM) -> post --\
                                              \--rejected--> reject ----------------------+--> finish
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from examples.common import graceful_plugin  # noqa: E402
from examples.invoice_pipeline.specialists import make_specialists, rejection_line  # noqa: E402
from examples.invoice_pipeline.tools import build_journal_entry, check_invoice  # noqa: E402
from adk2.common import as_text  # noqa: E402
from google.adk import Context, Workflow  # noqa: E402
from google.adk.apps.app import App  # noqa: E402
from google.adk.workflow import DEFAULT_ROUTE, START  # noqa: E402

extractor, _validator, normalizer, _accountant = make_specialists("single_turn")


def intake(ctx: Context, node_input) -> str:
    """Keep the raw invoice in state; the extractor reads it from there."""
    ctx.state["raw_input"] = as_text(node_input)
    return "Extract the invoice."


def validate(ctx: Context, node_input, invoice: dict | None = None) -> str:
    """Same checks as the validate_invoice tool, as a code node (no LLM call)."""
    errors = check_invoice(invoice) if invoice else ["NOT_EXTRACTED"]
    ctx.state["validation"] = {"status": "REJECTED", "reasons": errors} if errors else {"status": "APPROVED"}
    ctx.route = "rejected" if errors else "approved"
    return "Normalize the recorded invoice."


def reject(validation: dict) -> str:
    return rejection_line(validation)


def post(ctx: Context, node_input, invoice: dict, normalized: dict | None = None) -> str:
    """Same logic as the post_journal_entry tool, as a code node (no LLM call)."""
    if not normalized:
        return "STATUS: ERROR | REASONS: NOT_NORMALIZED"
    entry = build_journal_entry(invoice, normalized)
    ctx.state["journal_entry"] = entry
    return f"STATUS: APPROVED | TOTAL: {entry['total']} | ENTRY: {entry['entry_id']}"


def finish(node_input: str) -> str:
    return node_input


root_agent = Workflow(
    name="invoice_graph",
    description="Extract (LLM) -> validate (code) -> normalize (LLM) -> post (code).",
    edges=[
        (START, intake, extractor, validate),
        (validate, {"rejected": reject, DEFAULT_ROUTE: normalizer}),  # "approved" -> default
        (normalizer, post),
        (post, finish),
        (reject, finish),
    ],
)

plugin = graceful_plugin()
for specialist in (extractor, normalizer):
    plugin.apply_429_interceptor(specialist)

app = App(name="workflow_graph", root_agent=root_agent, plugins=[plugin])
