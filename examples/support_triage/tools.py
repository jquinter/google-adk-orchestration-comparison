"""Mock back-office tools for the support triage example.

Data is static and read-only, so every run sees the same world. Actions that
would change something (refunds, labels, tickets) are recorded in session
state instead of mutating the data.
"""

import logging

from google.adk.tools.tool_context import ToolContext

CATEGORIES = ["billing", "technical", "returns", "escalation"]

ACCOUNTS = {
    "C100": {"plan": "Fiber 500", "service": "active", "balance_due": 0,
             "charges": [{"id": "CH-901", "amount": 29990, "date": "2026-09-01"},
                         {"id": "CH-902", "amount": 29990, "date": "2026-09-01"}]},
    "C200": {"plan": "Fiber 300", "service": "active", "balance_due": 0,
             "charges": [{"id": "CH-910", "amount": 24990, "date": "2026-09-01"}]},
    "C300": {"plan": "Fiber 300", "service": "active", "balance_due": 0,
             "charges": [{"id": "CH-920", "amount": 24990, "date": "2026-09-01"}]},
    "C400": {"plan": "Fiber 500", "service": "active", "balance_due": 0,
             "charges": [{"id": "CH-930", "amount": 29990, "date": "2026-09-01"},
                         {"id": "CH-931", "amount": 29990, "date": "2026-09-01"}]},
    "C500": {"plan": "Fiber 300", "service": "suspended_nonpayment", "balance_due": 74970,
             "charges": []},
    "C600": {"plan": "Fiber 500", "service": "active", "balance_due": 0,
             "charges": [{"id": "CH-950", "amount": 29990, "date": "2026-09-01"}]},
    "C700": {"plan": "Fiber 1000", "service": "active", "balance_due": 0,
             "charges": [{"id": "CH-960", "amount": 39990, "date": "2026-09-01"}]},
}

LINES = {  # result of a remote line diagnostic
    "C200": "fault_detected", "C600": "fault_detected",
}

ORDERS = {  # order_id -> (customer_id, item, days_since_delivery)
    "O-552": ("C300", "WiFi 6 router", 10),
    "O-553": ("C400", "Fiber modem", 12),
    "O-600": ("C600", "WiFi 6 router", 45),
}

RETURN_WINDOW_DAYS = 30


def _record(tool_context: ToolContext, action: str, detail: dict) -> None:
    actions = list(tool_context.state.get("actions", []))
    actions.append({"action": action, **detail})
    tool_context.state["actions"] = actions
    logging.info(f"[{action}] {detail}")


# --- Triage (workflow only) ----------------------------------------------------

def set_route(tool_context: ToolContext, categories: list[str]) -> dict:
    """Store which teams must handle the request, in the order they should act.

    Args:
        categories (list[str]): One or more of: billing, technical, returns, escalation.

    Returns:
        dict: {"status": "success"} or {"status": "error", "message": ...}
    """
    unknown = [c for c in categories if c not in CATEGORIES]
    if unknown or not categories:
        return {"status": "error", "message": f"Categories must be a non-empty subset of {CATEGORIES}"}
    tool_context.state["route"] = categories
    return {"status": "success"}


# --- Billing ----------------------------------------------------------------------

def lookup_account(customer_id: str) -> dict:
    """Look up a customer's plan, service status, balance due and recent charges.

    Args:
        customer_id (str): Customer id, e.g. "C100".
    """
    return ACCOUNTS.get(customer_id, {"error": f"Unknown customer {customer_id}"})


def issue_refund(tool_context: ToolContext, customer_id: str, charge_id: str) -> dict:
    """Refund a charge. Only duplicate charges (same amount and date as another charge) are refundable.

    Args:
        customer_id (str): Customer id.
        charge_id (str): The duplicate charge to refund.
    """
    charges = ACCOUNTS.get(customer_id, {}).get("charges", [])
    charge = next((c for c in charges if c["id"] == charge_id), None)
    if not charge:
        return {"status": "error", "message": "Charge not found."}
    duplicate = any(c["id"] != charge_id and c["amount"] == charge["amount"] and c["date"] == charge["date"]
                    for c in charges)
    if not duplicate:
        return {"status": "rejected", "message": "Charge is not a duplicate; not refundable."}
    _record(tool_context, "refund", {"customer_id": customer_id, "charge_id": charge_id})
    return {"status": "refunded", "amount": charge["amount"]}


def create_payment_plan(tool_context: ToolContext, customer_id: str, installments: int) -> dict:
    """Split an overdue balance into installments and reactivate a suspended service.

    Args:
        customer_id (str): Customer id.
        installments (int): Number of monthly installments (2 to 6).
    """
    account = ACCOUNTS.get(customer_id)
    if not account or account["balance_due"] <= 0:
        return {"status": "error", "message": "No balance due."}
    if not 2 <= installments <= 6:
        return {"status": "error", "message": "Installments must be between 2 and 6."}
    _record(tool_context, "payment_plan", {"customer_id": customer_id, "installments": installments})
    return {"status": "created", "installment_amount": round(account["balance_due"] / installments),
            "service": "reactivated"}


# --- Technical ----------------------------------------------------------------------

def check_service_status(customer_id: str) -> dict:
    """Check whether the customer's service is active, suspended, or affected by an outage.

    Args:
        customer_id (str): Customer id.
    """
    account = ACCOUNTS.get(customer_id)
    if not account:
        return {"error": f"Unknown customer {customer_id}"}
    status = {"service": account["service"], "area_outage": False}
    if account["service"] == "suspended_nonpayment":
        status["note"] = "Service suspended for non-payment. Billing must resolve the balance."
    return status


def run_line_diagnostics(customer_id: str) -> dict:
    """Run a remote diagnostic on the customer's fiber line.

    Args:
        customer_id (str): Customer id.
    """
    return {"result": LINES.get(customer_id, "ok")}


def schedule_technician(tool_context: ToolContext, customer_id: str) -> dict:
    """Schedule an on-site technician visit. Only use after diagnostics detected a fault.

    Args:
        customer_id (str): Customer id.
    """
    if LINES.get(customer_id) != "fault_detected":
        return {"status": "rejected", "message": "No fault detected; a visit is not justified."}
    _record(tool_context, "technician", {"customer_id": customer_id})
    return {"status": "scheduled", "slot": "next business day, 9:00-13:00"}


# --- Returns ----------------------------------------------------------------------

def check_return_eligibility(order_id: str) -> dict:
    """Check whether an order can still be returned (30-day window from delivery).

    Args:
        order_id (str): Order id, e.g. "O-552".
    """
    order = ORDERS.get(order_id)
    if not order:
        return {"error": f"Unknown order {order_id}"}
    customer_id, item, days = order
    eligible = days <= RETURN_WINDOW_DAYS
    result = {"order_id": order_id, "item": item, "days_since_delivery": days, "eligible": eligible}
    if not eligible:
        result["note"] = "Outside the return window. If the device is faulty, Technical support can help."
    return result


def create_return_label(tool_context: ToolContext, order_id: str) -> dict:
    """Create a prepaid return label for an eligible order.

    Args:
        order_id (str): Order id.
    """
    order = ORDERS.get(order_id)
    if not order or order[2] > RETURN_WINDOW_DAYS:
        return {"status": "rejected", "message": "Order is not eligible for return."}
    _record(tool_context, "return_label", {"order_id": order_id})
    return {"status": "created", "label": f"RL-{order_id}"}


# --- Escalation -------------------------------------------------------------------

def escalate_to_human(tool_context: ToolContext, customer_id: str, summary: str) -> dict:
    """Open a priority ticket for a human agent (legal threats, complaints to regulators, abuse).

    Args:
        customer_id (str): Customer id.
        summary (str): One-sentence summary of the situation.
    """
    _record(tool_context, "escalation", {"customer_id": customer_id})
    return {"status": "escalated", "ticket": f"HUM-{customer_id}"}
