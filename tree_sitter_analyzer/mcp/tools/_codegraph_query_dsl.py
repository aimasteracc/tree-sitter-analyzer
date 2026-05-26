"""Safe parser for the codegraph_query chain DSL."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any

_SUPPORTED_STEPS = {"search", "explore", "callers", "callees", "related", "take"}


@dataclass(frozen=True)
class _ChainStep:
    name: str
    args: list[Any]
    kwargs: dict[str, Any]


def parse_chain(query: str) -> list[_ChainStep]:
    """Parse a safe chained query into steps."""
    if "(" not in query:
        return [
            _ChainStep("explore", [query], {}),
            _ChainStep("related", [], {}),
        ]

    parts = _split_chain(query)
    steps = [_parse_step(part) for part in parts]
    if not steps:
        raise ValueError("query has no chain steps")
    return steps


def step_to_dict(step: _ChainStep) -> dict[str, Any]:
    return {"name": step.name, "args": step.args, "kwargs": step.kwargs}


def first_str(step: _ChainStep, *, required: bool) -> str:
    if step.args and isinstance(step.args[0], str):
        return step.args[0]
    query = step.kwargs.get("query")
    if isinstance(query, str):
        return query
    if required:
        raise ValueError(f"{step.name}() requires a string query")
    return ""


def first_int(step: _ChainStep, default: int) -> int:
    if step.args and isinstance(step.args[0], int):
        return step.args[0]
    return default


def int_kw(step: _ChainStep, name: str, default: int, cap: int) -> int:
    value = step.kwargs.get(name, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0, min(parsed, cap))


def bool_kw(step: _ChainStep, name: str, default: bool) -> bool:
    value = step.kwargs.get(name, default)
    return bool(value)


def _split_chain(query: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escape = False
    for idx, ch in enumerate(query):
        if escape:
            escape = False
            continue
        if ch == "\\" and quote:
            escape = True
            continue
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in {"'", '"'}:
            quote = ch
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("unbalanced ')' in query chain")
        elif ch == "." and depth == 0:
            parts.append(query[start:idx].strip())
            start = idx + 1
    if quote or depth != 0:
        raise ValueError("unbalanced quote or parentheses in query chain")
    parts.append(query[start:].strip())
    return [part for part in parts if part]


def _parse_step(part: str) -> _ChainStep:
    match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\((.*)\)", part, flags=re.S)
    if not match:
        raise ValueError(f"invalid chain step: {part!r}")
    name = match.group(1)
    if name not in _SUPPORTED_STEPS:
        raise ValueError(f"unsupported chain step: {name}")

    expr = ast.parse(f"_f({match.group(2)})", mode="eval")
    call = expr.body
    if not isinstance(call, ast.Call):
        raise ValueError(f"invalid chain step args: {part!r}")
    args = [_literal(node) for node in call.args]
    kwargs = {kw.arg: _literal(kw.value) for kw in call.keywords if kw.arg is not None}
    return _ChainStep(name=name, args=args, kwargs=kwargs)


def _literal(node: ast.AST) -> Any:
    value = ast.literal_eval(node)
    if isinstance(value, str | int | bool | float) or value is None:
        return value
    raise ValueError("chain arguments must be scalar literals")


__all__ = [
    "_ChainStep",
    "bool_kw",
    "first_int",
    "first_str",
    "int_kw",
    "parse_chain",
    "step_to_dict",
]
