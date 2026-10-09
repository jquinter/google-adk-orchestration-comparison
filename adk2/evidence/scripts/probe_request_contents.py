"""Per-call request size for the invoice workflow (approved path), scripted LLM, no real calls."""
import asyncio, os, sys, json
from unittest import mock
sys.path.insert(0, os.getcwd())
os.environ.update(MODEL="gemini-2.5-flash", GOOGLE_GENAI_USE_VERTEXAI="TRUE", GOOGLE_CLOUD_PROJECT="t", GOOGLE_CLOUD_LOCATION="us-central1")
import google.cloud.logging; google.cloud.logging.Client = mock.MagicMock()
import google.adk
from google.adk.models import BaseLlm, LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types
from examples.invoice_pipeline.workflow.agent import root_agent

PLANS = {
 "extractor": [("record_invoice", dict(issuer_rut="76.123.456-0", issuer_name="X", invoice_number="7", issue_date="1 de enero de 2026",
     line_descriptions=["Toner"], line_quantities=[2], line_unit_prices=[1000], net_amount=2000, tax_amount=380, total_amount=2380)), "Extracted."],
 "validator": [("validate_invoice", {}), "Validation passed."],
 "normalizer": [("record_normalized", dict(issue_date_iso="2026-01-01", line_categories=["office_supplies"])), "Normalized."],
 "accountant": [("post_journal_entry", {}), "STATUS: APPROVED | TOTAL: 2380 | ENTRY: JE-7"],
}
class Probe(BaseLlm):
    agent: str = ""
    n: int = 0
    async def generate_content_async(self, req, stream=False):
        roles = [c.role for c in req.contents]
        chars = sum(len(str(p.to_json_dict())) for c in req.contents for p in (c.parts or []))
        (self.agent=="validator" and self.n==0) and [print(c.role, json.dumps(p.to_json_dict(), ensure_ascii=False)[:900]) for c in req.contents for p in (c.parts or [])]
        step = PLANS[self.agent][min(self.n, 1)]; self.n += 1
        part = types.Part(function_call=types.FunctionCall(name=step[0], args=step[1])) if isinstance(step, tuple) else types.Part(text=step)
        yield LlmResponse(content=types.Content(role="model", parts=[part]))
for a in root_agent.sub_agents: object.__setattr__(a, "model", Probe(model="p", agent=a.name))
async def main():
    print(f"ADK {google.adk.__version__}")
    r = InMemoryRunner(agent=root_agent, app_name="p"); s = await r.session_service.create_session(app_name="p", user_id="u")
    async for _ in r.run_async(user_id="u", session_id=s.id, new_message=types.Content(role="user", parts=[types.Part(text="FACTURA ELECTRONICA N 7 ...")])): pass
asyncio.run(main())
