"""tree-sitter-analyzer 的统一、携带证据的查询语言 (RFC-0041)。

一套语法 (TQL 选择器 + 管道阶段)、一个 IR (:mod:`.ir`)、一个解析器
(:mod:`.parser`)、一个执行引擎 (:mod:`.engine`)。``answer`` 是
``search action=uql`` 与 ``--uql`` 共用的应用层入口。
"""

from __future__ import annotations

from typing import Any

from .backends import Backends, IndexBackends
from .errors import INVALID_TOOL_ARGUMENT, Err, QueryError
from .output import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    PageRequest,
    canonical,
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
    """解析、执行并投影一个查询；所有失败都以类型化 payload 返回。"""
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
        decoded = decode_cursor(cursor, canonical(query))
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
