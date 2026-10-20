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
from dataclasses import dataclass
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
#: 别的文件以别名为被调名、解析只停在本文件（文件已知、符号未知）的调用边。
_MODULE_ATTRIBUTE_SQL = (
    "SELECT file_path, line, callee_full, metadata FROM edges "
    "WHERE kind = 'calls' AND callee_name = ? AND file_path <> ? "
    "AND callee_resolved_file = ? ORDER BY file_path, line"
)
_REEXPORT_CALL_SQL = (
    "SELECT 1 FROM edges WHERE kind = 'calls' AND callee_name = ? "
    "AND file_path <> ? LIMIT 1"
)


@dataclass(frozen=True)
class AliasCheck:
    """``alias_reference_check`` 的结果。"""

    #: 导入行可跳过的别名。
    masked: frozenset[str]
    #: 本文件中需按别名点名的出现行。
    lines: list[int]
    #: #1705：别的文件经本文件的模块属性调用别名、却未解析到目标的位置。
    foreign: list[dict[str, Any]]


def alias_reference_check(
    cache: Any,
    rel_path: str,
    text: str,
    bare: str,
    declaration_files: Collection[str],
    reference_lines: ReferenceLines,
) -> AliasCheck:
    """别名的导入行能否跳过、哪些别名出现须点名；读取失败时都不跳过。"""
    masked: set[str] = set()
    extra: list[int] = []
    foreign: list[dict[str, Any]] = []
    for alias, start, end in alias_bindings(text, bare):
        foreign.extend(_module_attribute_sites(cache, rel_path, alias, bare))
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
    return AliasCheck(frozenset(masked), extra, foreign)


def _module_attribute_sites(
    cache: Any, rel_path: str, alias: str, bare: str
) -> list[dict[str, Any]]:
    """#1705：``owner.alias()`` 只解析到本文件（属性被重新绑定、模块别名不唯一等）的位置。

    这些调用可能经本文件的改名导入到达 ``bare``，却不在调用方列表里；以别名点名，
    而不是只给出导入行。读取失败返回空（导入行本身仍是引用，答复不会是 complete）。
    """
    try:
        rows = (
            cache.get_conn()
            .execute(_MODULE_ATTRIBUTE_SQL, (alias, rel_path, rel_path))
            .fetchall()
        )
    except (sqlite3.Error, AttributeError):
        return []
    return [
        {"file": str(file_path), "line": int(line or 0), "alias": alias}
        for file_path, line, callee_full, metadata in rows
        if "." in str(callee_full or "") and _alias_name(metadata) != bare
    ]


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
        imported = conn.execute(
            _REEXPORT_IMPORT_SQL, (rel_path, alias, alias)
        ).fetchone()
        called = conn.execute(_REEXPORT_CALL_SQL, (alias, rel_path)).fetchone()
    except (sqlite3.Error, AttributeError):
        return True
    return imported is not None or called is not None


__all__ = ["AliasCheck", "alias_reference_check"]
