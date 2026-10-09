"""Benchmark cases for the invoice pipeline.

Invoices are generated from structured data, so the expected outcome is correct
by construction. `complexity` is the number of line items. Note that the
pipeline length is fixed (4 steps): the coordination tax here is a *fixed cost
per document*, which multiplies with document volume rather than with size.
"""

import re

from examples.invoice_pipeline.tools import VAT_RATE, rut_check_digit

CATALOG = [
    ("Resma papel carta 500 hojas", 4_990),
    ("Licencia anual software contable", 189_000),
    ("Asesoria tributaria (horas)", 45_000),
    ("Pasaje aereo SCL-CCP", 98_500),
    ("Almuerzo reunion con cliente", 23_800),
    ("Toner impresora laser", 54_990),
    ("Suscripcion almacenamiento en la nube", 12_500),
    ("Servicio de traduccion juridica", 160_000),
    ("Hotel Concepcion 1 noche", 72_000),
    ("Archivadores y carpetas", 8_490),
]

MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
          "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _clp(n: int) -> str:
    return "$" + f"{n:,}".replace(",", ".")


def _rut(body: int, valid: bool = True) -> str:
    dv = rut_check_digit(body)
    if not valid:  # any other digit makes it invalid
        dv = "1" if dv != "1" else "2"
    return f"{body:,}".replace(",", ".") + "-" + dv


def _invoice(folio, n_lines, rut_valid=True, tax_delta=0, total_delta=0):
    items = [(desc, (i % 3) + 1, price) for i, (desc, price) in enumerate(CATALOG[:n_lines])]
    net = sum(q * p for _, q, p in items)
    tax = round(net * VAT_RATE) + tax_delta
    total = net + tax + total_delta
    lines = "\n".join(f"  {q} x {d} ......... {_clp(p)} c/u = {_clp(q * p)}" for d, q, p in items)
    text = f"""FACTURA ELECTRONICA N° {folio}
Emisor: Comercial Andes SpA   RUT: {_rut(76_123_456, rut_valid)}
Fecha de emision: {12 + n_lines} de {MONTHS[n_lines % 12]} de 2026
Detalle:
{lines}
Monto neto: {_clp(net)}
IVA (19%): {_clp(tax)}
TOTAL: {_clp(total)}"""
    return text, total


def _case(case_id, folio, n_lines, expected, **kw):
    text, total = _invoice(folio, n_lines, **kw)
    if expected == "APPROVED":
        exp = {"status": "APPROVED", "total": total}
    else:
        exp = {"status": "REJECTED", "reasons": expected}
    return {"id": case_id, "input": text, "complexity": n_lines, "expected": exp}


LADDER = [
    _case("I1", 1041, 1, "APPROVED"),
    _case("I3", 1042, 3, "APPROVED"),
    _case("I6", 1043, 6, "APPROVED"),
    _case("I10", 1044, 10, "APPROVED"),
]

GUARD = [
    _case("R_RUT", 1045, 3, ["INVALID_RUT"], rut_valid=False),
    _case("R_TAX", 1046, 3, ["TAX_MISMATCH"], tax_delta=1_000),
    _case("R_TOT", 1047, 3, ["TOTAL_MISMATCH"], total_delta=-500),
]


def grade(case: dict, final_text: str, metrics: dict) -> bool:
    """Correct iff the final STATUS line matches the expected outcome."""
    exp = case["expected"]
    text = (final_text or "").upper()
    if exp["status"] == "APPROVED":
        m = re.search(r"TOTAL:\s*\$?([\d.,]+)", text)
        return ("STATUS: APPROVED" in text and m is not None
                and int(re.sub(r"[^\d]", "", m.group(1))) == exp["total"])
    return "STATUS: REJECTED" in text and all(r in text for r in exp["reasons"])
