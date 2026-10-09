"""Deterministic tools for the invoice pipeline.

The LLM does what only an LLM can do (read a messy invoice, classify line
items); everything checkable is done in code and shared through session state.
"""

import logging
from collections import defaultdict

from google.adk.tools.tool_context import ToolContext

VAT_RATE = 0.19  # Chilean IVA

# Chart of accounts used by the normalizer and the journal entry.
EXPENSE_ACCOUNTS = {
    "office_supplies": "6101 Office Supplies",
    "software": "6102 Software & Subscriptions",
    "professional_services": "6103 Professional Services",
    "travel": "6104 Travel",
    "meals": "6105 Meals & Entertainment",
}
VAT_CREDIT_ACCOUNT = "1150 VAT Credit (IVA Credito Fiscal)"
PAYABLE_ACCOUNT = "2101 Accounts Payable"


def rut_check_digit(body: int) -> str:
    """Modulo-11 check digit of a Chilean RUT body."""
    total, factor = 0, 2
    for digit in reversed(str(body)):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    remainder = 11 - (total % 11)
    return {11: "0", 10: "K"}.get(remainder, str(remainder))


def is_valid_rut(rut: str) -> bool:
    cleaned = rut.replace(".", "").replace(" ", "").upper()
    if "-" not in cleaned:
        return False
    body, dv = cleaned.rsplit("-", 1)
    return body.isdigit() and rut_check_digit(int(body)) == dv


def check_invoice(invoice: dict) -> list[str]:
    """Return the list of failed checks (empty list means the invoice is valid)."""
    errors = []
    if not is_valid_rut(invoice.get("issuer_rut", "")):
        errors.append("INVALID_RUT")
    lines_total = sum(int(i["quantity"]) * int(i["unit_price"]) for i in invoice.get("line_items", []))
    if lines_total != int(invoice["net_amount"]):
        errors.append("LINES_MISMATCH")
    if round(int(invoice["net_amount"]) * VAT_RATE) != int(invoice["tax_amount"]):
        errors.append("TAX_MISMATCH")
    if int(invoice["net_amount"]) + int(invoice["tax_amount"]) != int(invoice["total_amount"]):
        errors.append("TOTAL_MISMATCH")
    return errors


# --- Tools ---------------------------------------------------------------------

def record_invoice(
    tool_context: ToolContext,
    issuer_rut: str,
    issuer_name: str,
    invoice_number: str,
    issue_date: str,
    line_descriptions: list[str],
    line_quantities: list[int],
    line_unit_prices: list[int],
    net_amount: int,
    tax_amount: int,
    total_amount: int,
) -> dict[str, str]:
    """Store the fields extracted from the raw invoice in the shared state.

    All amounts are integers in CLP, without thousands separators.

    Args:
        issuer_rut (str): Issuer tax ID exactly as printed (e.g. "76.123.456-0").
        issuer_name (str): Issuer company name.
        invoice_number (str): Invoice number (folio).
        issue_date (str): Issue date exactly as printed.
        line_descriptions (list[str]): Description of each line item, in order.
        line_quantities (list[int]): Quantity of each line item, same order.
        line_unit_prices (list[int]): Unit price of each line item, same order.
        net_amount (int): Net amount (neto).
        tax_amount (int): VAT amount (IVA).
        total_amount (int): Total amount.

    Returns:
        dict[str, str]: {"status": "success"} or {"status": "error", "message": ...}
    """
    if not len(line_descriptions) == len(line_quantities) == len(line_unit_prices):
        return {"status": "error", "message": "Line item lists must have the same length."}
    tool_context.state["invoice"] = {
        "issuer_rut": issuer_rut,
        "issuer_name": issuer_name,
        "invoice_number": invoice_number,
        "issue_date": issue_date,
        "line_items": [
            {"description": d, "quantity": q, "unit_price": p}
            for d, q, p in zip(line_descriptions, line_quantities, line_unit_prices)
        ],
        "net_amount": net_amount,
        "tax_amount": tax_amount,
        "total_amount": total_amount,
    }
    logging.info(f"[Recorded invoice] {invoice_number} from {issuer_name}")
    return {"status": "success"}


def validate_invoice(tool_context: ToolContext) -> dict:
    """Validate the recorded invoice: issuer RUT check digit, line totals, VAT and total.

    Returns:
        dict: {"status": "APPROVED"} or {"status": "REJECTED", "reasons": [...]}
    """
    invoice = tool_context.state.get("invoice")
    if not invoice:
        result = {"status": "REJECTED", "reasons": ["NOT_EXTRACTED"]}
    else:
        errors = check_invoice(invoice)
        result = {"status": "REJECTED", "reasons": errors} if errors else {"status": "APPROVED"}
    tool_context.state["validation"] = result
    logging.info(f"[Validation] {result}")
    return result


def record_normalized(
    tool_context: ToolContext, issue_date_iso: str, line_categories: list[str]
) -> dict[str, str]:
    """Store the normalized date and the expense category of each line item.

    Args:
        issue_date_iso (str): Issue date as YYYY-MM-DD.
        line_categories (list[str]): One category per line item, in the same order.
            Allowed: office_supplies, software, professional_services, travel, meals.

    Returns:
        dict[str, str]: {"status": "success"} or {"status": "error", "message": ...}
    """
    invoice = tool_context.state.get("invoice", {})
    n_lines = len(invoice.get("line_items", []))
    unknown = [c for c in line_categories if c not in EXPENSE_ACCOUNTS]
    if unknown or len(line_categories) != n_lines:
        return {"status": "error",
                "message": f"Expected {n_lines} categories from {sorted(EXPENSE_ACCOUNTS)}; got {line_categories}"}
    tool_context.state["normalized"] = {"issue_date": issue_date_iso, "line_categories": line_categories}
    return {"status": "success"}


def post_journal_entry(tool_context: ToolContext) -> dict:
    """Build and post the journal entry for the validated, normalized invoice.

    Returns:
        dict: The posted entry with its id, lines and the invoice total.
    """
    invoice = tool_context.state.get("invoice")
    normalized = tool_context.state.get("normalized")
    if not invoice or not normalized:
        return {"status": "error", "message": "Invoice must be recorded and normalized first."}

    debits = defaultdict(int)
    for item, category in zip(invoice["line_items"], normalized["line_categories"]):
        debits[EXPENSE_ACCOUNTS[category]] += int(item["quantity"]) * int(item["unit_price"])
    lines = [{"account": acc, "debit": amt, "credit": 0} for acc, amt in sorted(debits.items())]
    lines.append({"account": VAT_CREDIT_ACCOUNT, "debit": int(invoice["tax_amount"]), "credit": 0})
    lines.append({"account": PAYABLE_ACCOUNT, "debit": 0, "credit": int(invoice["total_amount"])})

    entry = {
        "status": "posted",
        "entry_id": f"JE-{invoice['invoice_number']}",
        "date": normalized["issue_date"],
        "lines": lines,
        "total": int(invoice["total_amount"]),
    }
    tool_context.state["journal_entry"] = entry
    logging.info(f"[Posted] {entry['entry_id']}")
    return entry
