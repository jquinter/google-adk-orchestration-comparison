"""Offline checks for the ADK 2.x ports in adk2/: no credentials, no real LLM calls.

Run from the repo root with the ADK 2.x venv:  .venv2/bin/python adk2/evidence/scripts/adk2_offline_test.py
"""
import asyncio, importlib, json, os, re, sys, warnings
from unittest import mock
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
os.environ.update(MODEL="gemini-2.5-flash", GOOGLE_GENAI_USE_VERTEXAI="TRUE", GOOGLE_CLOUD_PROJECT="t", GOOGLE_CLOUD_LOCATION="us-central1")
import google.cloud.logging; google.cloud.logging.Client = mock.MagicMock()
from google.adk.models import LlmResponse
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import types

# --- Scripted model, patched at class level BEFORE the agents are imported (Workflow copies agents).
SCRIPT, COUNT = {}, {}
async def scripted(self, req, stream=False):
    name = (req.config.labels or {})["adk_agent_name"]
    i = COUNT.get(name, 0); COUNT[name] = i + 1
    steps = SCRIPT.get(name, ["done"]); step = steps[min(i, len(steps) - 1)]
    if callable(step):
        step = step(req)
    part = types.Part(function_call=types.FunctionCall(name=step[0], args=step[1])) if isinstance(step, tuple) else types.Part(text=step)
    yield LlmResponse(content=types.Content(role="model", parts=[part]),
                      usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=10, candidates_token_count=5))
Gemini.generate_content_async = scripted

failures = []
def ok(cond, msg):
    print(("  PASS " if cond else "  FAIL ") + msg)
    if not cond: failures.append(msg)

async def run(root, text, script):
    SCRIPT.clear(); SCRIPT.update(script); COUNT.clear()
    r = InMemoryRunner(agent=root, app_name="t"); s = await r.session_service.create_session(app_name="t", user_id="u")
    final = None
    async for ev in r.run_async(user_id="u", session_id=s.id, new_message=types.Content(role="user", parts=[types.Part(text=text)])):
        if getattr(ev, "output", None) is not None: final = ev.output
        elif ev.content and ev.content.parts and any(p.text for p in ev.content.parts): final = "".join(p.text or "" for p in ev.content.parts)
    s = await r.session_service.get_session(app_name="t", user_id="u", session_id=s.id)
    return final, dict(s.state), dict(COUNT)

async def main():
    print("1. Build all ADK 2.x variants")
    roots = {}
    for ex in ("calculator", "invoice_pipeline", "support_triage", "writer_critic"):
        for var in ("multiagent_single_turn", "workflow_graph"):
            roots[(ex, var)] = importlib.import_module(f"adk2.{ex}.{var}.agent").root_agent
        tools = [t.name for t in await roots[(ex, "multiagent_single_turn")].canonical_tools()]
        ok("transfer_to_agent" not in tools and tools, f"{ex}/single_turn: coordinator tools = {tools}")

    print("2. Calculator graph (scripted arithmetic)")
    from benchmark.bench_run import CALC_LADDER, CALC_GUARD
    def arith(req):
        q = "".join(p.text or "" for c in req.contents for p in (c.parts or []) if c.role == "user")
        a, op, b = re.search(r"(-?[\d.]+)\s*([-+*/])\s*(-?[\d.]+)", q).groups(); r = eval(f"{a}{op}{b}")
        return str(int(r) if r == int(r) else r)
    calc = {n: [arith] for n in ("adder", "substracter", "multiplier", "divider")}
    for cid, e, ops, exp in CALC_LADDER + CALC_GUARD:
        final, state, count = await run(roots[("calculator", "workflow_graph")], e, calc)
        good = (exp is None and "División por cero" in final) or final == f"El resultado es {exp}"
        ok(good and sum(count.values()) == (ops or sum(count.values())), f"calculator {cid}: {final!r}, llm_calls={sum(count.values())}")

    print("3. Invoice graph")
    from examples.invoice_pipeline import cases as ic
    rec = lambda rut: ("record_invoice", dict(issuer_rut=rut, issuer_name="X", invoice_number="7", issue_date="1 de enero de 2026",
        line_descriptions=["Toner"], line_quantities=[2], line_unit_prices=[1000], net_amount=2000, tax_amount=380, total_amount=2380))
    final, state, count = await run(roots[("invoice_pipeline", "workflow_graph")], "invoice", {
        "extractor": [rec("76.123.456-0"), "ok"],
        "normalizer": [("record_normalized", dict(issue_date_iso="2026-01-01", line_categories=["office_supplies"])), "ok"]})
    ok(final == "STATUS: APPROVED | TOTAL: 2380 | ENTRY: JE-7" and sum(count.values()) == 4, f"approved: {final!r}, llm_calls={count}")
    final, state, count = await run(roots[("invoice_pipeline", "workflow_graph")], "invoice", {"extractor": [rec("76.123.456-1"), "ok"]})
    ok(final == "STATUS: REJECTED | REASONS: INVALID_RUT" and "normalizer" not in count, f"rejected: {final!r}, llm_calls={count}")
    ok(state.get("raw_input") == "invoice", "raw invoice kept in state for the extractor")

    print("4. Support triage graph: re-routing on discovery (D_SUSP)")
    from examples.support_triage import cases as tc
    d_susp = next(c for c in tc.LADDER if c["id"] == "D_SUSP")
    final, state, count = await run(roots[("support_triage", "workflow_graph")], d_susp["input"], {
        "triage": ['{"categories": ["technical"]}'],
        "technical": [("check_service_status", {"customer_id": "C500"}),
                      '{"resolution": "RESOLUTION: service suspended for non-payment", "handoff_to": "billing"}'],
        "billing": [("create_payment_plan", {"customer_id": "C500", "installments": 3}),
                    '{"resolution": "RESOLUTION: 3-installment plan created, service reactivated", "handoff_to": "none"}']})
    ok(state.get("visited") == ["technical", "billing"], f"route technical -> billing: visited={state.get('visited')}")
    ok(tc.grade(d_susp, final, {"state": state}), f"D_SUSP graded correct; final={final!r}")
    final, state, count = await run(roots[("support_triage", "workflow_graph")], "loop?", {
        "triage": ['{"categories": ["technical"]}'],
        "technical": ['{"resolution": "RESOLUTION: x", "handoff_to": "billing"}'],
        "billing": ['{"resolution": "RESOLUTION: y", "handoff_to": "technical"}']})
    ok(state.get("visited") == ["technical", "billing"], f"ping-pong hand-offs stop (each team at most once): {state.get('visited')}")

    print("5. Writer/critic graph")
    from examples.writer_critic import cases as wc
    good = ("Meet Fiber 500: 500 Mbps symmetric fiber for your whole home, streaming, gaming and remote work "
            "without slowdowns, all for $24.990 per month with professional installation included and "
            "friendly local support. Ready to upgrade your connection today?")
    final, state, count = await run(roots[("writer_critic", "workflow_graph")], wc.LADDER[-1]["input"],
                                    {"writer": [("save_draft", {"draft": good}), "saved"]})
    ok(wc.grade(wc.LADDER[-1], final, {}) and count == {"writer": 2}, f"approved in 1 round, critic is code: llm_calls={count}")
    final, state, count = await run(roots[("writer_critic", "workflow_graph")], wc.GUARD[0]["input"],
                                    {"writer": [("save_draft", {"draft": "short"}), "saved"] * 10})
    ok(final.startswith("STATUS: NOT APPROVED") and state.get("rounds") == 5 and count == {"writer": 10},
       f"impossible brief bounded at 5 rounds: rounds={state.get('rounds')}, llm_calls={count}")
    ok(state.get("brief", "").startswith("Write a short product description"), "brief kept in state for writer and checker")

    print(f"\n{'ALL PASSED' if not failures else f'{len(failures)} FAILED'}")
    sys.exit(1 if failures else 0)

asyncio.run(main())
