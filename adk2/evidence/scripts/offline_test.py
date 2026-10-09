"""Offline checks for examples/: no credentials, no LLM calls."""
import asyncio
import os
import sys
from typing import AsyncGenerator
from unittest import mock

sys.path.insert(0, os.getcwd())
os.environ.setdefault("MODEL", "gemini-2.5-flash")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")

import google.cloud.logging  # noqa: E402
google.cloud.logging.Client = mock.MagicMock()

import importlib  # noqa: E402
from google.adk.models import BaseLlm, LlmResponse  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.adk.agents import LlmAgent  # noqa: E402
from google.genai import types  # noqa: E402

EXAMPLES = ["invoice_pipeline", "support_triage", "writer_critic"]
failures = []


def ok(cond, msg):
    print(("  PASS " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


class ScriptedLlm(BaseLlm):
    """Returns a fixed list of responses, one per call (function call or text)."""
    script: list = []
    calls: int = 0

    async def generate_content_async(self, llm_request, stream=False) -> AsyncGenerator[LlmResponse, None]:
        step = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        if isinstance(step, tuple):
            name, args = step
            part = types.Part(function_call=types.FunctionCall(name=name, args=args))
        else:
            part = types.Part(text=step)
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


def all_llm_agents(agent):
    if isinstance(agent, LlmAgent):
        yield agent
    for sub in agent.sub_agents:
        yield from all_llm_agents(sub)


def script(root, plans):
    for a in all_llm_agents(root):
        object.__setattr__(a, "model", ScriptedLlm(model="fake", script=plans.get(a.name, ["done"])))


async def run(root, text):
    runner = InMemoryRunner(agent=root, app_name="t")
    s = await runner.session_service.create_session(app_name="t", user_id="u")
    final = ""
    authors = []
    async for ev in runner.run_async(user_id="u", session_id=s.id,
                                     new_message=types.Content(role="user", parts=[types.Part(text=text)])):
        authors.append(ev.author)
        for p in (ev.content.parts if ev.content and ev.content.parts else []):
            if p.text:
                final = p.text
    s = await runner.session_service.get_session(app_name="t", user_id="u", session_id=s.id)
    return final, dict(s.state), authors


async def main():
    print("1. Build all agents and their tool declarations")
    roots = {}
    for ex in EXAMPLES:
        for pat in ("multiagent", "workflow"):
            mod = importlib.import_module(f"examples.{ex}.{pat}.agent")
            roots[(ex, pat)] = mod.root_agent
            n = 0
            for a in all_llm_agents(mod.root_agent):
                for t in await a.canonical_tools():
                    d = t._get_declaration()
                    n += 1
                    assert d is not None and d.name
            ok(True, f"{ex}/{pat}: {n} tool declarations built")

    print("2. Cases are self-consistent")
    from examples.invoice_pipeline import cases as ic
    from examples.writer_critic import cases as wc
    from examples.writer_critic.tools import check, parse_constraints
    for c in wc.LADDER:
        ok(len(parse_constraints(c["input"])) == c["complexity"], f"writer {c['id']} parses {c['complexity']} constraints")
    good = ("Meet Fiber 500: 500 Mbps symmetric fiber for your whole home, streaming, gaming and remote work "
            "without slowdowns, all for $24.990 per month with professional installation included and "
            "friendly local support. Ready to upgrade your connection today?")
    ok(check(parse_constraints(wc.LADDER[-1]["input"]), good) == [], "a compliant draft passes W8")
    ok(check(parse_constraints(wc.GUARD[0]["input"]), good) != [], "W_IMPOSSIBLE can never pass")
    ok(wc.grade(wc.LADDER[-1], f"STATUS: APPROVED\nFINAL DRAFT:\n{good}", {}), "writer grader accepts compliant draft")
    ok(not wc.grade(wc.LADDER[-1], "STATUS: APPROVED\nFINAL DRAFT:\nCheap!", {}), "writer grader rejects a false APPROVED")
    t = ic.LADDER[1]["expected"]["total"]
    ok(ic.grade(ic.LADDER[1], f"STATUS: APPROVED | TOTAL: {t:,} | ENTRY: JE-1042".replace(",", "."), {}), "invoice grader accepts CLP-formatted total")

    print("3. Workflow code paths with a scripted LLM")
    # Invoice: rejected invoice stops before normalizer/accountant, without calling them.
    root = roots[("invoice_pipeline", "workflow")]
    script(root, {
        "extractor": [("record_invoice", dict(issuer_rut="76.123.456-1", issuer_name="X", invoice_number="1",
                                              issue_date="1 de enero de 2026", line_descriptions=["a"],
                                              line_quantities=[1], line_unit_prices=[1000],
                                              net_amount=1000, tax_amount=190, total_amount=1190)), "ok"],
        "validator": [("validate_invoice", {}), "STATUS: REJECTED | REASONS: INVALID_RUT"],
    })
    final, state, authors = await run(root, "invoice")
    ok(final == "STATUS: REJECTED | REASONS: INVALID_RUT", f"invoice reject short-circuits: {final!r}")
    ok(root.sub_agents[2].model.calls == 0 and root.sub_agents[3].model.calls == 0, "normalizer/accountant never called the LLM")

    # Invoice: approved path posts the entry.
    root = roots[("invoice_pipeline", "workflow")]
    script(root, {
        "extractor": [("record_invoice", dict(issuer_rut="76.123.456-0", issuer_name="X", invoice_number="7",
                                              issue_date="1 de enero de 2026", line_descriptions=["Toner"],
                                              line_quantities=[2], line_unit_prices=[1000],
                                              net_amount=2000, tax_amount=380, total_amount=2380)), "ok"],
        "validator": [("validate_invoice", {}), "Validation passed."],
        "normalizer": [("record_normalized", dict(issue_date_iso="2026-01-01", line_categories=["office_supplies"])), "ok"],
        "accountant": [("post_journal_entry", {}), "STATUS: APPROVED | TOTAL: 2380 | ENTRY: JE-7"],
    })
    final, state, _ = await run(root, "invoice")
    je = state.get("journal_entry", {})
    ok(je.get("total") == 2380 and sum(l["debit"] for l in je["lines"]) == sum(l["credit"] for l in je["lines"]),
       "journal entry posted and balanced")

    # Triage: dispatcher runs exactly the routed teams, in order.
    root = roots[("support_triage", "workflow")]
    script(root, {
        "triage": [("set_route", {"categories": ["billing", "returns"]}), "routed"],
        "billing": [("issue_refund", {"customer_id": "C400", "charge_id": "CH-931"}), "RESOLUTION: refunded"],
        "returns": [("create_return_label", {"order_id": "O-553"}), "RESOLUTION: label"],
        "technical": ["SHOULD NOT RUN"],
    })
    final, state, authors = await run(root, "C400 ...")
    ok({a["action"] for a in state.get("actions", [])} == {"refund", "return_label"}, "dispatcher ran billing + returns")
    ok("technical" not in authors, "dispatcher skipped unrouted teams")
    from examples.support_triage import cases as tc
    ok(tc.grade(tc.LADDER[3], final, {"state": state}), "triage grader accepts M_BILL_RET")

    # Writer/critic: loop exits on approval and the presenter prints the draft.
    root = roots[("writer_critic", "workflow")]
    script(root, {
        "writer": [("save_draft", {"draft": good}), "saved"],
        "critic": [("check_draft", {}), ("exit_loop", {}), "APPROVED"],
    })
    final, state, authors = await run(root, wc.LADDER[-1]["input"])
    ok(final.startswith("STATUS: APPROVED") and good in final, "presenter prints approved draft after exit_loop")
    ok(wc.grade(wc.LADDER[-1], final, {}), "writer grader accepts presenter output")

    # Writer/critic: never approved -> bounded by max_iterations.
    root = roots[("writer_critic", "workflow")]
    script(root, {
        "writer": [("save_draft", {"draft": "short"}), "saved"] * 10,
        "critic": [("check_draft", {}), "violations"] * 10,
    })
    final, state, _ = await run(root, wc.GUARD[0]["input"])
    ok(final.startswith("STATUS: NOT APPROVED") and state.get("revision") == 5, f"loop bounded at 5 rounds (revision={state.get('revision')})")

    print(f"\n{'ALL PASSED' if not failures else f'{len(failures)} FAILED'}")
    sys.exit(1 if failures else 0)


asyncio.run(main())
