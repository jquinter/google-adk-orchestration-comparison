"""Calculator — ADK 2.x multi-agent with single-turn delegation.

Same coordinator and specialists as `adk_multiagent_systems/parent_and_subagents`,
but each specialist has mode="single_turn": the coordinator calls it like a
function tool (`adder(request=...)`) and always gets its answer back. There is
no `transfer_to_agent`, so a specialist cannot "forget" to hand control back.
The LLM still decides the order of operations at every step.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from examples.common import (  # noqa: E402
    DETERMINISTIC, graceful_plugin, log_model_response, log_query_to_model, model,
)
from adk2.common import single_turn  # noqa: E402
from google.adk import Agent  # noqa: E402
from google.adk.apps.app import App  # noqa: E402

COMMON = dict(
    generate_content_config=DETERMINISTIC,
    before_model_callback=log_query_to_model,
    after_model_callback=log_model_response,
)


def _specialist(name: str, operation: str, plural: str) -> Agent:
    return Agent(
        name=name,
        model=model(),
        description=f"A specialist in {operation}. Pass it the current expression; it returns the simplified expression.",
        instruction=f"""
        - You are the {operation} specialist.
        - The request contains a mathematical expression.
        - Find {operation} operations in the expression and calculate them.
        - ONLY perform {plural}. Do NOT perform other operations.
        - Reply with the updated, simplified expression only.
        """,
        **COMMON,
    )


zero_division_guard = Agent(
    name="zero_division_guard",
    model=model(),
    description="Checks whether a division operation divides by zero.",
    instruction="""
        - You are the division by zero guard.
        - If the divisor (denominator) of the division in the request is zero or evaluates to zero:
          reply exactly "Error: División por cero detectada. Operación cancelada."
        - Otherwise reply exactly "Valid division. Safe to proceed."
        """,
    **COMMON,
)

divider = Agent(
    name="divider",
    model=model(),
    description="A specialist in division. Pass it the current expression; it returns the simplified expression or an error.",
    instruction="""
        - You are the division specialist.
        - The request contains a mathematical expression.
        - Before dividing, call the 'zero_division_guard' tool with the division to validate it.
        - If the guard returns an error, reply with that error message only.
        - Otherwise calculate the division operations and reply with the updated, simplified expression only.
        """,
    sub_agents=single_turn([zero_division_guard]),
    **COMMON,
)

root_agent = Agent(
    name="steering",
    model=model(),
    description="An assistant for math operations.",
    instruction="""
        - You are an orchestration assistant for math operations.
        - The user will provide a mathematical expression.
        - Call the correct specialist tool (adder, substracter, multiplier, divider) based on the order of operations,
          passing the current expression as the request.
        - Each specialist returns the simplified expression. If operations remain, call the next appropriate specialist.
        - If an error is returned (e.g., "Error: División por cero detectada"), print the error message and stop.
        - Continue until the expression is reduced to a single number, then present the final answer to the user.
        """,
    generate_content_config=DETERMINISTIC,
    sub_agents=single_turn([
        _specialist("adder", "addition", "additions"),
        _specialist("substracter", "subtraction", "subtractions"),
        _specialist("multiplier", "multiplication", "multiplications"),
        divider,
    ]),
)

plugin = graceful_plugin()
plugin.apply_429_interceptor(root_agent)

app = App(name="multiagent_single_turn", root_agent=root_agent, plugins=[plugin])
