import os
import sys
import logging
import google.cloud.logging
from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)
from callback_logging import log_query_to_model, log_model_response

from google.adk import Agent
from google.adk.agents import LoopAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.tools import exit_loop
from google.adk.models import Gemini
from google.genai import types

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adk_utils.plugins import Graceful429Plugin
from google.adk.apps.app import App

load_dotenv()

cloud_logging_client = google.cloud.logging.Client()
cloud_logging_client.setup_logging()

RETRY_OPTIONS = types.HttpRetryOptions(initial_delay=1, max_delay=3, attempts=30)
model_name = os.getenv("MODEL")

# Tools

def update_expression(
    tool_context: ToolContext, expression: str
) -> dict[str, str]:
    """Update the mathematical expression in the shared state.

    Args:
        expression (str): The updated mathematical expression.

    Returns:
        dict[str, str]: {"status": "success"}
    """
    tool_context.state['expression'] = expression
    logging.info(f"[Updated expression] {expression}")
    return {"status": "success"}

# Agents

adder = Agent(
    name="adder",
    model=Gemini(model=model_name, retry_options=RETRY_OPTIONS),
    description="A specialist in adding numbers",
    instruction="""
        - You are the addition specialist.
        - Read the current expression from the state key 'expression': { expression? }
        - Look for addition operations in the expression.
        - Do NOT perform additions if they are immediately preceded by a subtraction (e.g., in '100 - 5 + 24', you must NOT add 5 + 24 because the minus sign belongs to 5).
        - If there are additions to perform:
            - Calculate them and simplify the expression.
            - Save the updated expression using the 'update_expression' tool.
            - After calling the tool, output the updated expression as text and end your turn. Do NOT call the tool again.
        - If there are no additions to perform:
            - If the expression is reduced to a single number (no operations remaining), output the final result clearly (e.g. "El resultado es X") and call the 'exit_loop' tool.
            - Otherwise, output a message saying no additions were found and end your turn.
        """,
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
    ),
    before_model_callback=log_query_to_model,
    after_model_callback=log_model_response,
    tools=[update_expression, exit_loop],
)

substracter = Agent(
    name="substracter",
    model=Gemini(model=model_name, retry_options=RETRY_OPTIONS),
    description="A specialist in subtracting numbers",
    instruction="""
        - You are the subtraction specialist.
        - Read the current expression from the state key 'expression': { expression? }
        - Look for subtraction operations in the expression.
        - If there are subtractions to perform:
            - Calculate them and simplify the expression.
            - Save the updated expression using the 'update_expression' tool.
            - After calling the tool, output the updated expression as text and end your turn. Do NOT call the tool again.
        - If there are no subtractions to perform:
            - If the expression is reduced to a single number (no operations remaining), output the final result clearly (e.g. "El resultado es X") and call the 'exit_loop' tool.
            - Otherwise, output a message saying no subtractions were found and end your turn.
        """,
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
    ),
    before_model_callback=log_query_to_model,
    after_model_callback=log_model_response,
    tools=[update_expression, exit_loop],
)

multiplier = Agent(
    name="multiplier",
    model=Gemini(model=model_name, retry_options=RETRY_OPTIONS),
    description="A specialist in multiplying numbers",
    instruction="""
        - You are the multiplication specialist.
        - Read the current expression from the state key 'expression': { expression? }
        - Look for multiplication operations in the expression.
        - Do NOT perform multiplications if they are immediately preceded by a division (e.g., in '100 / 5 * 2', you must NOT multiply 5 * 2).
        - If there are multiplications to perform:
            - Calculate them and simplify the expression.
            - Save the updated expression using the 'update_expression' tool.
            - After calling the tool, output the updated expression as text and end your turn. Do NOT call the tool again.
        - If there are no multiplications to perform:
            - If the expression is reduced to a single number (no operations remaining), output the final result clearly (e.g. "El resultado es X") and call the 'exit_loop' tool.
            - Otherwise, output a message saying no multiplications were found and end your turn.
        """,
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
    ),
    before_model_callback=log_query_to_model,
    after_model_callback=log_model_response,
    tools=[update_expression, exit_loop],
)

zero_division_guard = Agent(
    name="zero_division_guard",
    model=Gemini(model=model_name, retry_options=RETRY_OPTIONS),
    description="A guard that checks if a division operation divides by zero.",
    instruction="""
        - You are the division by zero guard.
        - Analyze the division operation to be performed.
        - If the divisor (denominator) is equal to zero or evaluates to zero (e.g. '10 / 0' or '5 / (5-5)'):
            - Output: "Error: División por cero detectada. Operación cancelada."
            - Call the 'exit_loop' tool immediately to abort the execution.
        - If the division is safe (the divisor is NOT zero):
            - Output: "Valid division. Safe to proceed."
            - Transfer control back to the 'divider' parent agent using the 'transfer_to_agent' tool.
        """,
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
    ),
    before_model_callback=log_query_to_model,
    after_model_callback=log_model_response,
    tools=[exit_loop],
)

divider = Agent(
    name="divider",
    model=Gemini(model=model_name, retry_options=RETRY_OPTIONS),
    description="A specialist in dividing numbers",
    instruction="""
        - You are the division specialist.
        - Read the current expression from the state key 'expression': { expression? }
        - Look for division operations in the expression.
        - If there are divisions to perform:
            - Before dividing, transfer control to the 'zero_division_guard' using the 'transfer_to_agent' tool to validate the operation first.
            - Once the validation is successful (safe to proceed):
                - Calculate the division and simplify the expression.
                - Save the updated expression using the 'update_expression' tool.
                - After calling the tool, output the updated expression as text and end your turn. Do NOT call the tool again.
        - If there are no divisions to perform:
            - If the expression is reduced to a single number (no operations remaining), output the final result clearly (e.g. "El resultado es X") and call the 'exit_loop' tool.
            - Otherwise, output a message saying no divisions were found and end your turn.
        """,
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
    ),
    before_model_callback=log_query_to_model,
    after_model_callback=log_model_response,
    tools=[update_expression, exit_loop],
    sub_agents=[zero_division_guard],
)

calculator_loop = LoopAgent(
    name="calculator_loop",
    sub_agents=[adder, substracter, multiplier, divider],
)

root_agent = Agent(
    name="workflow_steering",
    model=Gemini(model=model_name, retry_options=RETRY_OPTIONS),
    description="Guides the user in performing math operations.",
    instruction="""
        - You are an orchestration assistant for math operations.
        - The user will provide a mathematical expression.
        - Store the expression in the state key 'expression' using the 'update_expression' tool.
        - Transfer to the 'calculator_loop' agent using the 'transfer_to_agent' tool.
        - Once the calculation is complete, present the final answer to the user.
        """,
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
    ),
    tools=[update_expression],
    sub_agents=[calculator_loop],
)

graceful_plugin = Graceful429Plugin(
    name="graceful_429_plugin",
    fallback_text={
        "default": "**[Simulated Response via 429 Graceful Fallback]**\n\nThe API is out of quota. Please retry."
    }
)
graceful_plugin.apply_429_interceptor(root_agent)

app = App(
    name="workflow_agents",
    root_agent=root_agent,
    plugins=[graceful_plugin]
)
