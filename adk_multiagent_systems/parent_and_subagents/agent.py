import os
import sys
import logging

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)
from callback_logging import log_query_to_model, log_model_response
from dotenv import load_dotenv
import google.cloud.logging
from google.adk import Agent
from google.adk.models import Gemini
from google.genai import types
from typing import Optional, List, Dict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adk_utils.plugins import Graceful429Plugin
from google.adk.apps.app import App

load_dotenv()

cloud_logging_client = google.cloud.logging.Client()
cloud_logging_client.setup_logging()

RETRY_OPTIONS = types.HttpRetryOptions(initial_delay=1, max_delay=3, attempts=30)
model_name = os.getenv("MODEL")

# Agents

adder = Agent(
    name="adder",
    model=Gemini(model=model_name, retry_options=RETRY_OPTIONS),
    description="A specialist in adding numbers",
    instruction="""
        - You are the addition specialist.
        - Find addition operations in the provided expression and calculate them.
        - Return the updated, simplified expression.
        - ONLY perform additions. Do NOT perform other operations.
        - Once you have performed the additions and updated the expression, transfer control back to the 'steering' agent using the 'transfer_to_agent' tool.
        """,
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
    ),
    before_model_callback=log_query_to_model,
    after_model_callback=log_model_response,
)

substracter = Agent(
    name="substracter",
    model=Gemini(model=model_name, retry_options=RETRY_OPTIONS),
    description="A specialist in subtracting numbers",
    instruction="""
        - You are the subtraction specialist.
        - Find subtraction operations in the provided expression and calculate them.
        - Return the updated, simplified expression.
        - ONLY perform subtractions. Do NOT perform other operations.
        - Once you have performed the subtractions and updated the expression, transfer control back to the 'steering' agent using the 'transfer_to_agent' tool.
        """,
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
    ),
    before_model_callback=log_query_to_model,
    after_model_callback=log_model_response,
)

multiplier = Agent(
    name="multiplier",
    model=Gemini(model=model_name, retry_options=RETRY_OPTIONS),
    description="A specialist in multiplying numbers",
    instruction="""
        - You are the multiplication specialist.
        - Find multiplication operations in the provided expression and calculate them.
        - Return the updated, simplified expression.
        - ONLY perform multiplications. Do NOT perform other operations.
        - Once you have performed the multiplications and updated the expression, transfer control back to the 'steering' agent using the 'transfer_to_agent' tool.
        """,
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
    ),
    before_model_callback=log_query_to_model,
    after_model_callback=log_model_response,
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
            - Transfer control back to the 'divider' parent agent using the 'transfer_to_agent' tool.
        - If the division is safe (the divisor is NOT zero):
            - Output: "Valid division. Safe to proceed."
            - Transfer control back to the 'divider' parent agent using the 'transfer_to_agent' tool.
        """,
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
    ),
    before_model_callback=log_query_to_model,
    after_model_callback=log_model_response,
)

divider = Agent(
    name="divider",
    model=Gemini(model=model_name, retry_options=RETRY_OPTIONS),
    description="A specialist in dividing numbers",
    instruction="""
        - You are the division specialist.
        - Look at the expression to be evaluated.
        - If you have NOT yet validated the division operation with the 'zero_division_guard':
            - Transfer control to the 'zero_division_guard' using the 'transfer_to_agent' tool to validate the operation first.
        - If the 'zero_division_guard' has already run and returned an error (e.g. "Error: División por cero detectada"):
            - Output the error message and transfer control back to the 'steering' agent using the 'transfer_to_agent' tool.
        - If the validation was successful (safe to proceed):
            - Calculate the division operation and simplify the expression.
            - Transfer control back to the 'steering' agent using the 'transfer_to_agent' tool.
        """,
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
    ),
    before_model_callback=log_query_to_model,
    after_model_callback=log_model_response,
    sub_agents=[zero_division_guard],
)

root_agent = Agent(
    name="steering",
    model=Gemini(model=model_name, retry_options=RETRY_OPTIONS),
    description="An assistant for math operations.",
    instruction="""
        - You are an orchestration assistant for math operations.
        - The user will provide a mathematical expression.
        - Route the expression to the correct specialist sub-agent (adder, substracter, multiplier, divider) based on the order of operations.
        - When a specialist returns a simplified expression, if there are still operations remaining, route it to the next appropriate specialist.
        - If an error is returned (e.g., "Error: División por cero detectada"), print the error message and terminate the interaction.
        - Continue routing until the expression is reduced to a single number, then present the final answer to the user.
        """,
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
    ),
    sub_agents=[adder, substracter, multiplier, divider]
)

graceful_plugin = Graceful429Plugin(
    name="graceful_429_plugin",
    fallback_text={
        "default": "**[Simulated Response via 429 Graceful Fallback]**\n\nThe API is out of quota. Please retry."
    }
)
graceful_plugin.apply_429_interceptor(root_agent)

app = App(
    name="parent_and_subagents",
    root_agent=root_agent,
    plugins=[graceful_plugin]
)
