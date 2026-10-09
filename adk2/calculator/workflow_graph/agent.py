"""Calculator — ADK 2.x Workflow graph.

Translation of `adk_multiagent_systems/workflow_agents` (LoopAgent). The LLM
specialists still do the arithmetic, one operation at a time; everything
structural is code:

    START -> intake -> plan --add--> adder ------\
                         |  --sub--> substracter -+--> apply --> plan  (cycle)
                         |  --mul--> multiplier --|
                         |  --div--> divider -----/
                         |  --zero_division--> zero_division --\
                         \  --default (done)-------------------+--> finish

What disappears compared with the 1.x LoopAgent:
- broken precedence from a fixed adder->substracter->multiplier->divider pass
  (`plan` picks the next operation by parentheses and precedence);
- an LLM calling `exit_loop` before the expression is done (the loop ends when
  `plan` sees a single number);
- the LLM zero-division guard (a code check on the divisor, routed to an edge);
- every "no additions were found" turn: a specialist only runs when it has work.
"""

import os
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from examples.common import (  # noqa: E402
    DETERMINISTIC, graceful_plugin, log_model_response, log_query_to_model, model,
)
from adk2.common import as_text  # noqa: E402
from adk2.calculator.expression import apply_result, fmt, next_operation, tokenize  # noqa: E402
from google.adk import Agent, Context, Workflow  # noqa: E402
from google.adk.apps.app import App  # noqa: E402
from google.adk.workflow import DEFAULT_ROUTE, START  # noqa: E402

MAX_STEPS = 30
SYMBOL = {"add": "+", "sub": "-", "mul": "*", "div": "/"}
ZERO_DIVISION = "Error: División por cero detectada. Operación cancelada."


def _specialist(name: str, operation: str) -> Agent:
    return Agent(
        name=name,
        model=model(),
        description=f"A specialist in {operation}",
        instruction=f"""
        - You are the {operation} specialist.
        - The user gives you exactly one operation of the form 'a <op> b'.
        - Reply with ONLY the resulting number, nothing else.
        """,
        generate_content_config=DETERMINISTIC,
        before_model_callback=log_query_to_model,
        after_model_callback=log_model_response,
    )


adder = _specialist("adder", "addition")
substracter = _specialist("substracter", "subtraction")
multiplier = _specialist("multiplier", "multiplication")
divider = _specialist("divider", "division")


def intake(ctx: Context, node_input) -> str:
    """Parse the user's expression into tokens kept in state."""
    expression = as_text(node_input)
    ctx.state["tokens"] = tokenize(expression)
    ctx.state["steps"] = 0
    return expression


def plan(ctx: Context, node_input, tokens: list, steps: int) -> str:
    """Pick the next operation (code) and route to the specialist that performs it."""
    op = next_operation(tokens)
    if op is None or steps >= MAX_STEPS:
        ctx.route = "done"
        return " ".join(tokens)
    if op["op"] == "div" and float(op["right"]) == 0:
        ctx.route = "zero_division"
        return f"{op['left']} / {op['right']}"
    ctx.state["pending"] = op["index"]
    ctx.route = op["op"]
    return f"{op['left']} {SYMBOL[op['op']]} {op['right']}"


def apply(ctx: Context, node_input, tokens: list, pending: int, steps: int) -> str:
    """Substitute the specialist's number back into the expression."""
    ctx.state["steps"] = steps + 1
    match = re.search(r"-?\d+(?:\.\d+)?", as_text(node_input).replace(",", ""))
    if match:  # a non-numeric reply leaves the expression unchanged; plan retries, bounded by MAX_STEPS
        ctx.state["tokens"] = apply_result(tokens, pending, fmt(float(match.group())))
    return " ".join(ctx.state["tokens"])


def zero_division(ctx: Context, node_input) -> str:
    ctx.state["error"] = ZERO_DIVISION
    return ZERO_DIVISION


def finish(node_input, tokens: list, error: str = "") -> str:
    if error:
        return error
    if len(tokens) != 1:
        return f"Error: could not finish within {MAX_STEPS} steps. Remaining: {' '.join(tokens)}"
    return f"El resultado es {tokens[0]}"


root_agent = Workflow(
    name="calculator_graph",
    description="Evaluates an arithmetic expression; code decides the order, LLMs do the arithmetic.",
    edges=[
        (START, intake, plan),
        (plan, {"add": adder, "sub": substracter, "mul": multiplier, "div": divider,
                "zero_division": zero_division, DEFAULT_ROUTE: finish}),  # "done" -> default
        (adder, apply), (substracter, apply), (multiplier, apply), (divider, apply),
        (apply, plan),
        (zero_division, finish),
    ],
)

plugin = graceful_plugin()
for specialist in (adder, substracter, multiplier, divider):
    plugin.apply_429_interceptor(specialist)

app = App(name="workflow_graph", root_agent=root_agent, plugins=[plugin])
