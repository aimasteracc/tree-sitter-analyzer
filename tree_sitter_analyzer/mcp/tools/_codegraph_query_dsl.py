"""Safe parser for the codegraph_query chain DSL."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any

_MAX_QUERY_LENGTH = 4096
_MAX_STEPS = 20
_MAX_LIST_ARGS = 8
_MAX_STRING_ARG_LENGTH = 160
_SUPPORTED_STEPS = {
    "search",
    "semantic",
    "explore",
    "callers",
    "callees",
    "related",
    "filter",
    "where",
    "exclude",
    "not",
    "has",
    "take",
    "sort",
    "include",
    "with",
    "uml",
    "answer",
}
_FILTER_KWARGS = frozenset(
    {
        "name",
        "kind",
        "file",
        "path",
        "language",
        "test",
        "generated",
        "regex",
        "case",
    }
)
_ALLOWED_KWARGS: dict[str, frozenset[str]] = {
    "search": frozenset({"query", "limit"}),
    "semantic": frozenset({"query", "limit"}),
    "explore": frozenset({"query", "max_files", "max_symbols", "include_code"}),
    "callers": frozenset({"depth", "limit"}),
    "callees": frozenset({"depth", "limit"}),
    "related": frozenset({"depth", "limit"}),
    "filter": _FILTER_KWARGS,
    "where": _FILTER_KWARGS,
    "exclude": _FILTER_KWARGS,
    "not": _FILTER_KWARGS,
    "has": _FILTER_KWARGS | frozenset({"callers", "callees", "depth", "limit"}),
    "take": frozenset({"limit"}),
    "sort": frozenset({"by", "desc"}),
    "include": frozenset(
        {
            "source",
            "callers",
            "callees",
            "complexity",
            "health",
            "risk",
            "affected_tests",
            "max_files",
            "max_symbols",
            "include_code",
            "limit",
        }
    ),
    "with": frozenset(
        {
            "source",
            "callers",
            "callees",
            "complexity",
            "health",
            "risk",
            "affected_tests",
            "max_files",
            "max_symbols",
            "include_code",
            "limit",
        }
    ),
    "uml": frozenset({"direction", "limit", "max_edges"}),
    "answer": frozenset({"compact"}),
}


@dataclass(frozen=True)
class _ChainStep:
    name: str
    args: list[Any]
    kwargs: dict[str, Any]


def _has_unquoted_pipe(query: str) -> bool:
    """True when ``query`` has a ``|`` outside any single/double-quoted span.

    A top-level pipe is a wrong-separator attempt (#574); a pipe inside a
    quoted arg — ``search('string | number')`` — is legitimate search text.
    """
    in_single = in_double = escaped = False
    for ch in query:
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "|" and not in_single and not in_double:
            return True
    return False


def parse_chain(query: str) -> list[_ChainStep]:
    """Parse a safe chained query into steps."""
    if len(query) > _MAX_QUERY_LENGTH:
        raise ValueError(f"query exceeds {_MAX_QUERY_LENGTH} characters")
    # #574: '|' is the natural-but-wrong separator agents reach for. Without
    # this it falls to the no-paren fallback — explore("A | B").related() — and
    # silently returns a wrong result with no diagnostic. Reject an UNQUOTED
    # '|' (separator position) loudly; a '|' inside a quoted arg is legitimate
    # search text (TS unions, type hints — Codex P2 on the first cut).
    if _has_unquoted_pipe(query):
        raise ValueError(
            "chain steps are separated by '.', not '|' — e.g. "
            "search('IndexShard').callers().  To search for a literal '|' "
            "(e.g. a type union), quote it: search('string | number')."
        )
    if "(" not in query:
        return [
            _ChainStep("explore", [query], {}),
            _ChainStep("related", [], {}),
        ]

    parts = _split_chain(query)
    if len(parts) > _MAX_STEPS:
        raise ValueError(f"query exceeds {_MAX_STEPS} chain steps")
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


def string_args(step: _ChainStep, *, required: bool) -> list[str]:
    values: list[str] = []
    if step.args:
        first = step.args[0]
        if isinstance(first, str):
            values = [first]
        elif isinstance(first, list):
            values = first
    query = step.kwargs.get("query")
    if isinstance(query, str):
        values = [query]
    elif isinstance(query, list):
        values = query
    values = [value for value in values if isinstance(value, str) and value.strip()]
    if required and not values:
        raise ValueError(f"{step.name}() requires a string query")
    return values


def first_int(step: _ChainStep, default: int) -> int:
    if step.args and isinstance(step.args[0], int):
        return step.args[0]
    limit_value = step.kwargs.get("limit")
    if isinstance(limit_value, int):
        return limit_value
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
    kwargs: dict[str, Any] = {}
    for kw in call.keywords:
        if kw.arg is None:
            raise ValueError(f"{name}() does not support **kwargs")
        if kw.arg not in _ALLOWED_KWARGS[name]:
            raise ValueError(f"{name}() does not support keyword {kw.arg!r}")
        kwargs[kw.arg] = _literal(kw.value)
    return _ChainStep(name=name, args=args, kwargs=kwargs)


# JS/JSON-style bare words LLM agents naturally write in this jQuery-style DSL.
# Python's ast.literal_eval only knows True/False/None, so ``answer(compact=true)``
# would otherwise blow up with a cryptic "malformed node or string" error and
# push the agent off the cheap one-call chain back onto slow multi-call paths.
_JS_BARE_LITERALS: dict[str, Any] = {
    "true": True,
    "false": False,
    "null": None,
    "none": None,
}


def _literal(node: ast.AST) -> Any:
    # Accept bare true/false/null (any case) before literal_eval, which rejects
    # them as undefined names.
    if isinstance(node, ast.Name) and node.id.lower() in _JS_BARE_LITERALS:
        return _JS_BARE_LITERALS[node.id.lower()]
    value = ast.literal_eval(node)
    if isinstance(value, str):
        if len(value) > _MAX_STRING_ARG_LENGTH:
            raise ValueError(f"string arguments must be <= {_MAX_STRING_ARG_LENGTH}")
        return value
    if isinstance(value, list):
        if len(value) > _MAX_LIST_ARGS:
            raise ValueError(f"list arguments must contain <= {_MAX_LIST_ARGS} items")
        if not all(isinstance(item, str) for item in value):
            raise ValueError("list arguments must contain only strings")
        if any(len(item) > _MAX_STRING_ARG_LENGTH for item in value):
            raise ValueError(f"string arguments must be <= {_MAX_STRING_ARG_LENGTH}")
        return value
    if isinstance(value, int | bool | float) or value is None:
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
    "string_args",
]
