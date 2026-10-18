"""#1670：被调用的改名导入行何时可以不计为 ``bare`` 的非调用引用。

``from m import f as _f`` 这一行提到 ``f``，非调用引用门默认把它计为引用——
0 个调用方时必须如此（#1645：只被再导出的函数不能显示为死代码）。有调用方时，
只有当别名的每一次使用都已核对，导入行才只是绑定：

* 别名是私有名（``_`` 开头）：公开别名可能被其他模块经 ``pkg.alias`` 使用，
  这些位置不在本文件、也不在按 ``f`` 的扫描里；
* 本文件中别名的每一次出现都是解析到目标定义的调用边（``metadata.import_alias``
  指向 ``f``，``callee_resolved_file`` 是 ``f`` 的声明文件），且至少有一次；
* 没有别的文件导入这个别名，也没有别的文件以它为被调名（再导出）。

不满足时导入行保留为引用；别名在非调用位置的出现（回调传递、赋值、``__all__``
字符串）另外按别名点名，答复因此停在非 ``complete``，并能指向真正的位置。
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable, Collection
from collections.abc import Set as AbstractSet
from typing import Any

from .callers_import_bindings import alias_bindings

#: ``reference_lines(text, pattern, covered_call_lines)``：未被调用边覆盖的出现行。
ReferenceLines = Callable[[str, "re.Pattern[str]", AbstractSet[int]], list[int]]

_ALIAS_EDGES_SQL = (
    "SELECT line, metadata, callee_resolved_file FROM edges "
    "WHERE kind = 'calls' AND callee_name = ? AND file_path = ?"
)
_REEXPORT_IMPORT_SQL = (
    "SELECT 1 FROM ast_imports WHERE file_path <> ? "
    "AND (local_name = ? OR alias_of = ?) LIMIT 1"
)
_REEXPORT_CALL_SQL = (
    "SELECT 1 FROM edges WHERE kind = 'calls' AND callee_name = ? "
    "AND file_path <> ? LIMIT 1"
)


def alias_reference_check(
    cache: Any,
    rel_path: str,
    text: str,
    bare: str,
    declaration_files: Collection[str],
    reference_lines: ReferenceLines,
) -> tuple[frozenset[str], list[int]]:
    """返回 ``(可跳过导入行的别名, 需按别名点名的出现行)``；读取失败时都不跳过。"""
    masked: set[str] = set()
    extra: list[int] = []
    for alias, start, end in alias_bindings(text, bare):
        call_lines = _bound_alias_call_lines(
            cache, rel_path, alias, bare, declaration_files
        )
        pattern = re.compile(r"(?<![\w$])" + re.escape(alias) + r"(?![\w$])")
        uncovered = reference_lines(
            _blank_statement(text, start, end), pattern, call_lines or frozenset()
        )
        if uncovered:
            extra.extend(uncovered)
            continue
        if (
            call_lines
            and alias.startswith("_")
            and not _reexported(cache, rel_path, alias)
        ):
            masked.add(alias)
    return frozenset(masked), extra


def _blank_statement(text: str, start: int, end: int) -> str:
    """把导入语句替换为空白（保留换行与行号），别名在其中的出现不计。"""
    statement = re.sub(r"[^\n]", " ", text[start:end])
    return text[:start] + statement + text[end:]


def _bound_alias_call_lines(
    cache: Any,
    rel_path: str,
    alias: str,
    bare: str,
    declaration_files: Collection[str],
) -> frozenset[int] | None:
    """本文件中以别名调用、且经改名导入解析到 ``bare`` 声明文件的调用边所在行。"""
    try:
        rows = cache.get_conn().execute(_ALIAS_EDGES_SQL, (alias, rel_path)).fetchall()
    except (sqlite3.Error, AttributeError):
        return None
    lines: set[int] = set()
    for line, metadata, resolved_file in rows:
        if str(resolved_file or "") not in declaration_files:
            continue
        if _alias_name(metadata) == bare:
            lines.add(int(line or 0))
    return frozenset(lines)


def _alias_name(metadata: Any) -> str | None:
    if not metadata or "import_alias" not in str(metadata):
        return None
    try:
        parsed = json.loads(metadata)
    except (TypeError, ValueError):
        return None
    alias = parsed.get("import_alias") if isinstance(parsed, dict) else None
    name = alias.get("name") if isinstance(alias, dict) else None
    return str(name) if name else None


def _reexported(cache: Any, rel_path: str, alias: str) -> bool:
    """别的文件导入了这个别名，或以它为被调名；读取失败按“已再导出”处理。"""
    try:
        conn = cache.get_conn()
        imported = conn.execute(_REEXPORT_IMPORT_SQL, (rel_path, alias, alias)).fetchone()
        called = conn.execute(_REEXPORT_CALL_SQL, (alias, rel_path)).fetchone()
    except (sqlite3.Error, AttributeError):
        return True
    return imported is not None or called is not None


__all__ = ["alias_reference_check"]
