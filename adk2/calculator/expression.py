"""Deterministic structure for the calculator: which operation comes next.

The LLM specialists still do the arithmetic; code decides the order (precedence
and parentheses) and detects division by zero. This removes the failure modes
that came from an LLM deciding structure: precedence broken by a fixed
sequential pass, and a specialist ending the loop before the expression is done.
"""

import re

OPS = {"+": "add", "-": "sub", "*": "mul", "/": "div"}
_TOKEN = re.compile(r"\s*(\d+(?:\.\d+)?|[()+\-*/])")


def tokenize(expression: str) -> list[str]:
    raw = _TOKEN.findall(expression)
    if "".join(raw) != re.sub(r"\s+", "", expression):
        raise ValueError(f"Unsupported characters in {expression!r}")
    tokens: list[str] = []
    for tok in raw:  # fold unary minus into the number that follows
        if tokens and tokens[-1] == "-" and re.fullmatch(r"\d+(?:\.\d+)?", tok) and (
                len(tokens) == 1 or tokens[-2] in "(+-*/"):
            tokens[-1] = "-" + tok
        else:
            tokens.append(tok)
    return tokens


def is_number(tok: str) -> bool:
    return re.fullmatch(r"-?\d+(?:\.\d+)?", tok) is not None


def fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.10g}"


def simplify_parens(tokens: list[str]) -> list[str]:
    """Drop parentheses that wrap a single number: '(' n ')' -> n."""
    changed = True
    while changed:
        changed = False
        for i in range(len(tokens) - 2):
            if tokens[i] == "(" and is_number(tokens[i + 1]) and tokens[i + 2] == ")":
                tokens = tokens[:i] + [tokens[i + 1]] + tokens[i + 3:]
                changed = True
                break
    return tokens


def next_operation(tokens: list[str]) -> dict | None:
    """The next binary operation to perform, honouring parentheses and precedence.

    Returns {"op": "add|sub|mul|div", "index": i, "left": a, "right": b}, where
    tokens[i] is the operator, or None when the expression is a single number.
    """
    tokens = simplify_parens(tokens)
    if len(tokens) == 1:
        return None
    # Innermost parenthesised group: the first ')' and the '(' that opens it.
    lo, hi = 0, len(tokens)
    if ")" in tokens:
        hi = tokens.index(")")
        lo = max(i for i in range(hi) if tokens[i] == "(") + 1
    for group in ("*/", "+-"):  # precedence, then left to right
        for i in range(lo, hi):
            if tokens[i] in group and len(tokens[i]) == 1:
                return {"op": OPS[tokens[i]], "index": i, "left": tokens[i - 1], "right": tokens[i + 1]}
    raise ValueError(f"Malformed expression: {' '.join(tokens)}")


def apply_result(tokens: list[str], index: int, result: str) -> list[str]:
    return simplify_parens(tokens[:index - 1] + [result] + tokens[index + 2:])
