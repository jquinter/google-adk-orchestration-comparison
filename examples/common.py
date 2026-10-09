"""Shared setup for the examples: env, logging, model and generation config.

Each example builds the *same* specialists for both orchestration patterns
(via a factory in its `specialists.py`), so the only thing that differs between
`multiagent/` and `workflow/` is how the specialists are coordinated.
"""

import os
import sys

from dotenv import load_dotenv
import google.cloud.logging
from google.adk.models import Gemini
from google.genai import types

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)
sys.path.append(os.path.join(REPO_ROOT, "adk_multiagent_systems"))
from callback_logging import log_query_to_model, log_model_response  # noqa: E402,F401
from adk_utils.plugins import Graceful429Plugin  # noqa: E402

load_dotenv()

cloud_logging_client = google.cloud.logging.Client()
cloud_logging_client.setup_logging()

RETRY_OPTIONS = types.HttpRetryOptions(initial_delay=1, max_delay=3, attempts=30)
MODEL_NAME = os.getenv("MODEL")

DETERMINISTIC = types.GenerateContentConfig(temperature=0)


def model() -> Gemini:
    """A fresh Gemini instance per agent (as in the calculator apps)."""
    return Gemini(model=MODEL_NAME, retry_options=RETRY_OPTIONS)


def graceful_plugin() -> Graceful429Plugin:
    return Graceful429Plugin(
        name="graceful_429_plugin",
        fallback_text={
            "default": "**[Simulated Response via 429 Graceful Fallback]**\n\nThe API is out of quota. Please retry."
        },
    )
