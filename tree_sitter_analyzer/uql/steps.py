"""Lexical layer shared by both dialects: split ``a(..).b(..)`` and parse args.

This is the one owner of step-level parsing (RFC-0041 §2). The legacy
``chain`` DSL (``mcp/tools/_codegraph_query_dsl.py``) and the unified
pipeline grammar both call it; neither re-splits query text. Arguments are
literal-only (``ast.literal_eval`` plus JS-style ``true/false/null``); user
input is never evaluated.

Messages are kept byte-identical to the pre-RFC-0041 chain parser because
existing callers and tests match on them.
"""

from __future__ import annotations

import ast
import re
from typing import Any

from .errors import (
    INVALID_ARGUMENT,
    INVALID_STEP,
    UNBALANCED,
    WRONG_SEPARATOR,
    Err,
    Ok,
    QueryError,
    Result,
)
from .ir import RawStep

MAX_STRING_ARG_LENGTH = 160
MAX_LIST_ARGS = 8

_STEP_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\((.*)\)", flags=re.S)

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

PIPE_MESSAGE = (
    "chain steps are separated by '.', not '|' — e.g. "
    "search('IndexShard').callers().  To search for a literal '|' "
    "(e.g. a type union), quote it: search('string | number')."
)


def has_unquoted_pipe(query: str) -> bool:
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


def pipe_error(query: str) -> QueryError:
    fixed = _replace_unquoted_pipes(query)
    return QueryError(
        WRONG_SEPARATOR,
        PIPE_MESSAGE,
        fragment="|",
        suggestion="Join steps with '.'",
        fixed_query=fixed,
    )


def _replace_unquoted_pipes(query: str) -> str:
    out: list[str] = []
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
            out.append(".")
            continue
        out.append(ch)
    return re.sub(r"\s*\.\s*", ".", "".join(out))


def split_steps(query: str) -> Result[list[str]]:
    """Split on top-level ``.`` (outside quotes and parentheses)."""
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
                return Err(
                    QueryError(
                        UNBALANCED,
                        "unbalanced ')' in query chain",
                        fragment=query[max(0, idx - 20) : idx + 1],
                        suggestion="Remove the extra ')' or add the matching '('.",
                    )
                )
        elif ch == "." and depth == 0:
            parts.append(query[start:idx].strip())
            start = idx + 1
    if quote or depth != 0:
        return Err(
            QueryError(
                UNBALANCED,
                "unbalanced quote or parentheses in query chain",
                suggestion="Close every quote and parenthesis.",
            )
        )
    parts.append(query[start:].strip())
    return Ok([part for part in parts if part])


def parse_step(
    part: str,
    *,
    index: int,
    allowed_kwargs: dict[str, frozenset[str]],
    unknown_step: Any,
) -> Result[RawStep]:
    """Parse one ``name(args)`` step.

    ``unknown_step(name, index, part)`` builds the dialect's error for a name
    outside ``allowed_kwargs`` (the two dialects word it differently).
    """
    match = _STEP_RE.fullmatch(part)
    if not match:
        return Err(
            QueryError(
                INVALID_STEP,
                f"invalid chain step: {part!r}",
                stage_index=index,
                fragment=part,
                suggestion="Write each step as name(args), e.g. callers().",
            )
        )
    name = match.group(1)
    if name not in allowed_kwargs:
        error: QueryError = unknown_step(name, index, part)
        return Err(error)
    try:
        expr = ast.parse(f"_f({match.group(2)})", mode="eval")
    except SyntaxError as exc:
        return Err(
            QueryError(
                INVALID_STEP,
                f"invalid chain step args: {part!r} ({exc.msg})",
                stage_index=index,
                fragment=part,
                suggestion="Arguments must be literals: 'text', 3, true, ['a', 'b'].",
            )
        )
    call = expr.body
    if not isinstance(call, ast.Call):
        return Err(
            QueryError(INVALID_STEP, f"invalid chain step args: {part!r}", index, part)
        )
    try:
        args = [literal(node) for node in call.args]
        kwargs: dict[str, Any] = {}
        for kw in call.keywords:
            if kw.arg is None:
                raise _ArgError(f"{name}() does not support **kwargs", None)
            if kw.arg not in allowed_kwargs[name]:
                allowed = ", ".join(sorted(allowed_kwargs[name])) or "(none)"
                raise _ArgError(
                    f"{name}() does not support keyword {kw.arg!r}",
                    f"Accepted keywords for {name}(): {allowed}.",
                    unknown=True,
                )
            kwargs[kw.arg] = literal(kw.value)
    except _ArgError as exc:
        from .errors import UNKNOWN_ARGUMENT

        return Err(
            QueryError(
                UNKNOWN_ARGUMENT if exc.unknown else INVALID_ARGUMENT,
                exc.message,
                stage_index=index,
                fragment=part,
                suggestion=exc.suggestion,
            )
        )
    except ValueError as exc:
        return Err(
            QueryError(
                INVALID_ARGUMENT,
                str(exc),
                stage_index=index,
                fragment=part,
                suggestion="Arguments must be literals: 'text', 3, true, ['a', 'b'].",
            )
        )
    return Ok(RawStep(name=name, args=args, kwargs=kwargs))


class _ArgError(Exception):
    def __init__(self, message: str, suggestion: str | None, unknown: bool = False):
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion
        self.unknown = unknown


def literal(node: ast.AST) -> Any:
    """A literal argument value; raises ``ValueError`` for anything else."""
    # Accept bare true/false/null (any case) before literal_eval, which rejects
    # them as undefined names.
    if isinstance(node, ast.Name) and node.id.lower() in _JS_BARE_LITERALS:
        return _JS_BARE_LITERALS[node.id.lower()]
    value = ast.literal_eval(node)
    if isinstance(value, str):
        if len(value) > MAX_STRING_ARG_LENGTH:
            raise ValueError(f"string arguments must be <= {MAX_STRING_ARG_LENGTH}")
        return value
    if isinstance(value, list):
        if len(value) > MAX_LIST_ARGS:
            raise ValueError(f"list arguments must contain <= {MAX_LIST_ARGS} items")
        if not all(isinstance(item, str) for item in value):
            raise ValueError("list arguments must contain only strings")
        if any(len(item) > MAX_STRING_ARG_LENGTH for item in value):
            raise ValueError(f"string arguments must be <= {MAX_STRING_ARG_LENGTH}")
        return value
    if isinstance(value, int | bool | float) or value is None:
        return value
    raise ValueError("chain arguments must be scalar literals")
