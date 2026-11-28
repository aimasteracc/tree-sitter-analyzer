"""#1936：其他文件里的未解析同名调用不得在指定 ``file_path`` 时被静默丢弃。

指定 ``file_path`` 时，``unresolved_caller_sites`` 只保留目标（或解析结果）落在
声明文件里的边。未解析调用的占位目标却在**调用方自己的文件**里
（``Sub.swift:stored:3``），于是这条边既不计入 ``UNRESOLVED_INBOUND``，所在行又因
确有同名 CALLS 边而被非调用引用扫描跳过（#1622）——两边同时漏掉，答案成了假
``complete``。

TS/JS 经导入到达的调用由 #1764 补回；Python、Java、Kotlin 由导入与类型绑定，并由
callers gate 守护。其余语言无需导入即可跨文件调用：Swift / C# / Ruby / Scala / C++
里不带接收者调用继承来的成员，C# 分部类，Ruby 重新打开的类，Go 同包函数，
PHP / Lua / C 的全局函数。这些语言里，同语言其他文件中、调用方未被列出的未解析
同名调用就是开放调用点：答案至多为 ``incomplete`` / ``unknown``。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Collection, Sequence
from typing import Any

from ...graph.edge_store import _bound_to, _resolution_is_resolved

#: 跨文件调用须经导入或类型绑定、且由 callers gate 守护的语言：不在此补回。
GATED_LANGUAGES = frozenset(
    {"python", "javascript", "jsx", "typescript", "tsx", "java", "kotlin"}
)


def cross_file_unresolved_sites(
    cache: Any,
    name: str,
    file_path: str | None,
    *,
    listed: Sequence[dict[str, Any]],
    known: Sequence[dict[str, Any]],
    bound_targets: Collection[tuple[str, int]] | None = None,
) -> list[dict[str, Any]] | None:
    """``known`` 之外、其他文件中的未解析同名调用点；读取失败为 None。

    只看目标声明语言中不在 :data:`GATED_LANGUAGES` 的那些；调用方已列出
    （同文件、同起始行）的调用点不再计入。每个调用点与 ``unresolved_caller_sites``
    同形：``{file, line, caller, callee}``。
    """
    if not file_path or cache is None:
        return []
    wanted = file_path.replace("\\", "/")
    try:
        conn = cache.get_conn()
        languages = {
            str(row[0])
            for row in conn.execute(
                "SELECT DISTINCT language FROM ast_symbol_rows "
                "WHERE name = ? AND file_path = ?",
                (name, wanted),
            )
        } - GATED_LANGUAGES
        if not languages:
            return []
        cursor = conn.cursor()
        cursor.row_factory = sqlite3.Row
        rows = cursor.execute(
            "SELECT * FROM edges WHERE kind = 'calls' AND callee_name = ? "
            "AND file_path <> ?",
            (name, wanted),
        ).fetchall()
    except (sqlite3.Error, AttributeError, TypeError):
        return None
    seen = {(str(site.get("file")), int(site.get("line") or 0)) for site in known}
    callers = {(str(c.get("file")), int(c.get("line") or 0)) for c in listed}
    sites: list[dict[str, Any]] = []
    for row in rows:
        if str(row["language"] or "") not in languages:
            continue
        if _resolution_is_resolved(row) or _bound_to(row, bound_targets):
            continue
        site_file = str(row["file_path"] or "").replace("\\", "/")
        line = int(row["line"] or 0)
        caller = str(row["caller_name"] or "")
        if (site_file, line) in seen:
            continue
        if caller and (site_file, int(row["caller_line"] or 0)) in callers:
            continue
        seen.add((site_file, line))
        sites.append(
            {
                "file": site_file,
                "line": line,
                "caller": caller or "<module>",
                "callee": str(row["callee_full"] or name),
            }
        )
    return sites


__all__ = ["GATED_LANGUAGES", "cross_file_unresolved_sites"]
