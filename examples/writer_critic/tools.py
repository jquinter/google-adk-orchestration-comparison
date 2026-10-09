"""Draft storage and a deterministic constraint checker for the writer/critic loop.

The brief (the user message) ends with a machine-readable block:

    Constraints:
    - max_words: 50
    - must_include: fiber; 24/7 support

The critic does not judge style: it runs `check_draft`, which parses that block
and verifies the draft in code, so "approved" means the same thing in every run.
"""

import logging
import re

from google.adk.tools.tool_context import ToolContext


def parse_constraints(brief: str) -> dict[str, str]:
    block = brief.split("Constraints:", 1)[-1]
    return {k.strip(): v.strip() for k, v in re.findall(r"^\s*-\s*([a-z_]+):\s*(.+)$", block, re.M)}


def _terms(value: str) -> list[str]:
    return [t.strip() for t in value.split(";") if t.strip()]


def check(constraints: dict[str, str], draft: str) -> list[str]:
    """Return the violated constraints (empty list means the draft passes)."""
    text = draft.strip()
    words = re.findall(r"\b[\w'/.-]+\b", text)
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    violations = []
    for key, value in constraints.items():
        if key == "max_words" and len(words) > int(value):
            violations.append(f"max_words: {len(words)} words, limit is {value}")
        elif key == "min_words" and len(words) < int(value):
            violations.append(f"min_words: {len(words)} words, minimum is {value}")
        elif key == "must_include":
            missing = [t for t in _terms(value) if t.lower() not in text.lower()]
            if missing:
                violations.append(f"must_include: missing {missing}")
        elif key == "must_not_include":
            present = [t for t in _terms(value) if re.search(rf"\b{re.escape(t)}\b", text, re.I)]
            if present:
                violations.append(f"must_not_include: found {present}")
        elif key == "end_with" and not text.endswith({"question": "?", "period": "."}[value]):
            violations.append(f"end_with: must end with a {value}")
        elif key == "start_with" and not text.lower().startswith(value.lower()):
            violations.append(f"start_with: must start with '{value}'")
        elif key == "max_sentences" and len(sentences) > int(value):
            violations.append(f"max_sentences: {len(sentences)} sentences, limit is {value}")
        elif key == "forbid_char" and value in text:
            violations.append(f"forbid_char: must not contain '{value}'")
    return violations


# --- Tools ---------------------------------------------------------------------

def save_draft(tool_context: ToolContext, draft: str) -> dict:
    """Save the current draft in the shared state.

    Args:
        draft (str): The full text of the draft (only the text, no title or commentary).

    Returns:
        dict: {"status": "success", "revision": n}
    """
    revision = tool_context.state.get("revision", 0) + 1
    tool_context.state["draft"] = draft
    tool_context.state["revision"] = revision
    logging.info(f"[Draft r{revision}] {draft}")
    return {"status": "success", "revision": revision}


def check_draft(tool_context: ToolContext) -> dict:
    """Check the saved draft against the brief's constraints.

    Returns:
        dict: {"passed": bool, "violations": [...]}
    """
    brief = tool_context.state.get("brief", "")  # ADK 2.x variants keep the brief in state
    if not brief and tool_context.user_content and tool_context.user_content.parts:
        brief = "".join(p.text or "" for p in tool_context.user_content.parts)
    draft = tool_context.state.get("draft", "")
    violations = check(parse_constraints(brief), draft) if draft else ["no draft saved yet"]
    review = {"passed": not violations, "violations": violations}
    tool_context.state["review"] = review
    logging.info(f"[Review] {review}")
    return review
