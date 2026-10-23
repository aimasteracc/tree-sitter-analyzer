"""有界读取已记录源码清单的内部实现。"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable, Iterator
from typing import Protocol, cast


class _Cursor(Protocol):
    def fetchone(self) -> tuple[object, ...] | None: ...


class _Connection(Protocol):
    def set_progress_handler(
        self, handler: Callable[[], int] | None, steps: int
    ) -> object: ...

    def execute(self, query: str, params: tuple[int, ...] = ()) -> _Cursor: ...


def _read_admitted_count(
    connection: _Connection,
    *,
    check_deadline: Callable[[], None],
    row_budget: int,
    cell_byte_budget: int,
    total_byte_budget: int,
) -> int:
    """预检数据库声明的行数和字节上限。"""
    check_deadline()
    preflight = connection.execute(
        "SELECT COUNT(*), "
        "MAX(length(CAST(file_path AS BLOB))), "
        "MAX(length(CAST(content_hash AS BLOB))), "
        "MAX(length(CAST(language AS BLOB))), "
        "SUM(COALESCE(length(CAST(file_path AS BLOB)), ?) + "
        "COALESCE(length(CAST(content_hash AS BLOB)), ?) + "
        "COALESCE(length(CAST(language AS BLOB)), ?)) FROM ast_index",
        (total_byte_budget + 1,) * 3,
    ).fetchone()
    check_deadline()
    if preflight is None or len(preflight) != 5:
        raise OverflowError("SOURCE_INVENTORY_BUDGET")
    count, max_path, max_hash, max_language, total_bytes = preflight
    if not isinstance(count, int) or count < 0 or count > row_budget:
        raise OverflowError("SOURCE_INVENTORY_BUDGET")
    if count == 0:
        return count
    if (
        not isinstance(max_path, int)
        or not isinstance(max_hash, int)
        or not isinstance(max_language, int)
        or not isinstance(total_bytes, int)
    ):
        raise OverflowError("SOURCE_INVENTORY_BUDGET")
    if (
        max_path > cell_byte_budget
        or max_hash > cell_byte_budget
        or max_language > cell_byte_budget
        or total_bytes > total_byte_budget
    ):
        raise OverflowError("SOURCE_INVENTORY_BUDGET")
    return count


def _iter_payload_rows(
    cursor: _Cursor,
    *,
    admitted_count: int,
    check_deadline: Callable[[], None],
    cell_byte_budget: int,
    total_byte_budget: int,
) -> Iterator[tuple[str, str, str]]:
    """逐行复核预检后的载荷并规范化路径。"""
    previous_path: str | None = None
    fetched = charged_bytes = 0
    while True:
        check_deadline()
        row = cursor.fetchone()
        check_deadline()
        if row is None:
            break
        fetched += 1
        if fetched > admitted_count:
            raise OverflowError("SOURCE_INVENTORY_BUDGET")
        raw_path, content_hash, language = row
        if (
            not isinstance(raw_path, str)
            or not isinstance(content_hash, str)
            or not isinstance(language, str)
        ):
            raise ValueError("CORRUPT_INDEX")
        cell_bytes = tuple(
            len(value.encode("utf-8", "surrogatepass"))
            for value in (raw_path, content_hash, language)
        )
        charged_bytes += sum(cell_bytes)
        if (
            any(size > cell_byte_budget for size in cell_bytes)
            or charged_bytes > total_byte_budget
        ):
            raise OverflowError("SOURCE_INVENTORY_BUDGET")
        path = raw_path.replace("\\", "/") if os.name == "nt" else raw_path
        if path == previous_path:
            raise ValueError("SOURCE_INVENTORY_DUPLICATE_PATH")
        previous_path = path
        yield path, content_hash, language
    if fetched != admitted_count:
        raise ValueError("CORRUPT_INDEX")


def read_recorded_source_rows(
    connection: object,
    *,
    effective_deadline: float,
    monotonic: Callable[[], float],
    row_budget: int,
    cell_byte_budget: int,
    total_byte_budget: int,
) -> frozenset[tuple[str, str, str]]:
    """在截止时间和字节预算内读取数据库声明的源码清单。"""

    typed_connection = cast(_Connection, connection)

    def expired() -> int:
        return int(monotonic() > effective_deadline)

    def check_deadline() -> None:
        if monotonic() > effective_deadline:
            raise TimeoutError

    typed_connection.set_progress_handler(expired, 1_000)
    try:
        admitted_count = _read_admitted_count(
            typed_connection,
            check_deadline=check_deadline,
            row_budget=row_budget,
            cell_byte_budget=cell_byte_budget,
            total_byte_budget=total_byte_budget,
        )
        if admitted_count == 0:
            return frozenset()

        # 载荷查询重复单元格限制，避免预检后膨胀的值跨越 SQLite/Python 边界。
        cursor = typed_connection.execute(
            "SELECT "
            "CASE WHEN typeof(file_path)='text' AND length(CAST(file_path AS BLOB)) <= ? THEN file_path END, "
            "CASE WHEN typeof(content_hash)='text' AND length(CAST(content_hash AS BLOB)) <= ? THEN content_hash END, "
            "CASE WHEN typeof(language)='text' AND length(CAST(language AS BLOB)) <= ? THEN language END "
            "FROM ast_index ORDER BY file_path",
            (cell_byte_budget,) * 3,
        )
        # 生成器直接填充唯一保留的清单集合，避免额外排序副本。
        return frozenset(
            _iter_payload_rows(
                cursor,
                admitted_count=admitted_count,
                check_deadline=check_deadline,
                cell_byte_budget=cell_byte_budget,
                total_byte_budget=total_byte_budget,
            )
        )
    except sqlite3.OperationalError as exc:
        if monotonic() > effective_deadline or "interrupt" in str(exc).lower():
            raise TimeoutError from exc
        raise
    finally:
        typed_connection.set_progress_handler(None, 0)
