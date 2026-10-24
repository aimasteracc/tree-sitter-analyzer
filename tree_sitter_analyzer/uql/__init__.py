"""Unified, evidence-carrying query language for tree-sitter-analyzer (RFC-0041).

One grammar (TQL selectors + pipeline stages), one IR (:mod:`.ir`), one
parser (:mod:`.parser`), one engine (:mod:`.engine`). ``answer`` is the
application-layer entry point shared by ``search action=uql`` and ``--uql``.
"""

from __future__ import annotations

from typing import Any

from .backends import Backends, IndexBackends
from .errors import INVALID_TOOL_ARGUMENT, Err, QueryError
from .output import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    PageRequest,
    check_generation,
    decode_cursor,
    error_payload,
    project,
)
from .parser import parse_chain, parse_query

DETAIL_LEVELS = ("compact", "full")


def _tool_error(message: str, query: Any) -> dict[str, Any]:
    return error_payload(QueryError(INVALID_TOOL_ARGUMENT, message), query)


async def answer(arguments: dict[str, Any], backends: Backends) -> dict[str, Any]:
    """Parse, execute and project one query; every failure is a typed payload."""
    query_text = arguments.get("query")
    limit = arguments.get("limit", DEFAULT_LIMIT)
    if isinstance(limit, float) and limit.is_integer():
        limit = int(limit)
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= MAX_LIMIT
    ):
        return _tool_error(f"limit must be an integer 1..{MAX_LIMIT}", query_text)
    detail = arguments.get("detail", "compact")
    if detail not in DETAIL_LEVELS:
        return _tool_error("detail must be 'compact' or 'full'", query_text)
    parsed = parse_query(query_text)
    if isinstance(parsed, Err):
        return error_payload(parsed.error, query_text)
    query = parsed.value
    page = PageRequest()
    cursor = arguments.get("cursor")
    if cursor is not None:
        decoded = decode_cursor(cursor, query.text)
        if isinstance(decoded, Err):
            return error_payload(decoded.error, query_text)
        page = decoded.value
    from .engine import run

    executed = await run(query, backends)
    if isinstance(executed, Err):
        return error_payload(executed.error, query_text)
    execution = executed.value
    total_rows = sum(len(g.rows) for g in execution.groups)
    if page.offset > total_rows:
        return error_payload(
            QueryError(
                "UQL_INVALID_CURSOR",
                "cursor offset is past the end of the answer",
                suggestion="Re-run the query without cursor.",
            ),
            query_text,
        )
    generation = None
    if page.cursor_given or total_rows > limit:
        generation = backends.generation()
    checked = check_generation(page, generation)
    if isinstance(checked, Err):
        return error_payload(checked.error, query_text)
    return project(
        execution,
        limit=limit,
        page=page,
        generation=generation,
        extra_gap=checked.value,
        detail=str(detail),
    )


__all__ = [
    "DETAIL_LEVELS",
    "Backends",
    "IndexBackends",
    "answer",
    "parse_chain",
    "parse_query",
]
