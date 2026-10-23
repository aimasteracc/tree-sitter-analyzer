"""#1670：被调用的改名导入行何时可以不计为 ``bare`` 的非调用引用。

``from m import f as _f`` 这一行提到 ``f``，非调用引用门默认把它计为引用——
0 个调用方时必须如此（#1645：只被再导出的函数不能显示为死代码）。有调用方时，
只有当别名的每一次使用都已核对，导入行才只是绑定：

* 别名是私有名（``_`` 开头）：公开别名可能被其他模块经 ``pkg.alias`` 使用，
  这些位置不在本文件、也不在按 ``f`` 的扫描里；
* 本文件中别名的每一次出现都是解析到目标定义的调用边（``metadata.import_alias``
  指向 ``f``，``callee_resolved_file`` 是 ``f`` 的声明文件），且至少有一次；
* 别名没有被再导出：没有别的文件导入这个别名，没有别的文件经模块属性
  （``owner._f()``）调用它，扫描到的别的文件里也没有提到它。

#1709：别的文件**自己**绑定同名别名（``from .other import g as _f``，或也直接
``from .core import f as _f``）不是再导出——它的出现由它自己的导入行核对。此前
任何同名的导入或调用都被当作再导出，只被调用的别名因此永远停在 ``incomplete``。

不满足时导入行保留为引用；别名在非调用位置的出现（回调传递、赋值、``__all__``
字符串），以及再导出的使用位置（别的文件的导入行、模块属性调用），另外按别名
点名，答复因此停在非 ``complete``，并能指向真正的位置。
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable, Collection, Mapping
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
#: 别的文件中提到别名的导入行（导入的就是别名，或把别名改名导入）。
_REEXPORT_IMPORT_SQL = (
    "SELECT file_path, line, local_name, alias_of FROM ast_imports "
    "WHERE file_path <> ? AND (local_name = ? OR alias_of = ?) AND is_star = 0 "
    "ORDER BY file_path, line"
)
#: 别的文件中以别名为被调名的调用边。
_REEXPORT_CALL_SQL = (
    "SELECT file_path, line, callee_full, metadata FROM edges "
    "WHERE kind = 'calls' AND callee_name = ? AND file_path <> ? "
    "ORDER BY file_path, line"
)
#: 文件自己对别名的绑定：把别的名字改名为它，或定义同名符号。
_OWN_IMPORT_SQL = (
    "SELECT 1 FROM ast_imports WHERE file_path = ? AND local_name = ? "
    "AND alias_of <> '' AND alias_of <> ? LIMIT 1"
)
_OWN_DEFINITION_SQL = (
    "SELECT 1 FROM ast_symbol_rows WHERE file_path = ? AND name = ? "
    "AND kind IN ('function', 'method', 'class', 'variable', 'constant') LIMIT 1"
)
#: 不可能是模块对象的接收者。
_INSTANCE_QUALIFIERS = ("self.", "cls.", "super().")


@dataclass(frozen=True)
class AliasCheck:
    """``alias_reference_check`` 的结果。"""

    #: 导入行可跳过的别名。
    masked: frozenset[str]
    #: 本文件中需按别名点名的出现行。
    lines: list[int]
    #: 别的文件中需按别名点名的位置 ``{file, line, alias}``（再导出的使用）。
    foreign: list[dict[str, Any]]


def alias_reference_check(
    cache: Any,
    rel_path: str,
    text: str,
    bare: str,
    declaration_files: Collection[str],
    reference_lines: ReferenceLines,
    hit_texts: Mapping[str, str] | None = None,
) -> AliasCheck:
    """别名的导入行能否跳过、哪些出现须点名；读取失败时都不跳过。

    ``hit_texts`` 为本次扫描读到的其余同语言文件（已去除注释与普通字符串），
    用来发现它们对别名的非调用使用。
    """
    masked: set[str] = set()
    extra: list[int] = []
    foreign: list[dict[str, Any]] = []
    for alias, start, end in alias_bindings(text, bare):
        call_lines = _bound_alias_call_lines(
            cache, rel_path, alias, bare, declaration_files
        )
        pattern = re.compile(r"(?<![\w$])" + re.escape(alias) + r"(?![\w$])")
        uncovered = reference_lines(
            _blank_statement(text, start, end), pattern, call_lines or frozenset()
        )
        extra.extend(uncovered)
        reexport = _reexport_sites(cache, rel_path, alias, bare)
        mentions = _mention_sites(
            cache,
            rel_path,
            alias,
            bare,
            declaration_files,
            hit_texts or {},
            reference_lines,
        )
        if reexport is None or mentions is None:
            continue
        sites, blocked = reexport
        foreign.extend(sites)
        foreign.extend(mentions)
        if (
            call_lines
            and not uncovered
            and alias.startswith("_")
            and not blocked
            and not mentions
        ):
            masked.add(alias)
    return AliasCheck(frozenset(masked), extra, foreign)


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


def _reexport_sites(
    cache: Any, rel_path: str, alias: str, bare: str
) -> tuple[list[dict[str, Any]], bool] | None:
    """别的文件对别名的再导出使用：``(须点名的位置, 是否存在再导出)``；读取失败为 None。

    * 导入行：导入的名字就是别名（``from .a import _f``、``from .a import _f as g``）；
      把别的名字改名为同一个别名（``from .other import g as _f``）是那个文件自己的绑定；
    * 模块属性调用（``owner._f()``）：接收者可能是本文件的模块对象。已经解析到 ``bare``
      的调用已列为调用方，不再重复点名，但同样说明别名被再导出。
    不带接收者的同名调用由所在文件自己的导入或定义绑定，在那里核对。
    """
    try:
        conn = cache.get_conn()
        imports = conn.execute(
            _REEXPORT_IMPORT_SQL, (rel_path, alias, alias)
        ).fetchall()
        calls = conn.execute(_REEXPORT_CALL_SQL, (alias, rel_path)).fetchall()
    except (sqlite3.Error, AttributeError):
        return None
    sites: list[dict[str, Any]] = [
        {"file": str(file_path), "line": int(line or 0), "alias": alias}
        for file_path, line, local_name, alias_of in imports
        if (alias_of or local_name) == alias
    ]
    blocked = bool(sites)
    for file_path, line, callee_full, metadata in calls:
        full = str(callee_full or "")
        if "." not in full or full.startswith(_INSTANCE_QUALIFIERS):
            continue
        blocked = True
        if _alias_name(metadata) != bare:
            sites.append(
                {"file": str(file_path), "line": int(line or 0), "alias": alias}
            )
    return sites, blocked


def _mention_sites(
    cache: Any,
    rel_path: str,
    alias: str,
    bare: str,
    declaration_files: Collection[str],
    hit_texts: Mapping[str, str],
    reference_lines: ReferenceLines,
) -> list[dict[str, Any]] | None:
    """扫描到的别的文件里对别名的出现（文件自己绑定同名别名的除外）；读取失败为 None。

    调用边已解析到 ``bare`` 的出现不计；其余（导入行、回调、属性读取、字符串）都是
    经本文件的模块属性或再导出到达别名的使用。
    """
    pattern = re.compile(r"(?<![\w$])" + re.escape(alias) + r"(?![\w$])")
    sites: list[dict[str, Any]] = []
    for other, text in sorted(hit_texts.items()):
        if other == rel_path or alias not in text:
            continue
        own = _binds_own(cache, other, alias)
        if own is None:
            return None
        if own:
            continue
        covered = _bound_alias_call_lines(cache, other, alias, bare, declaration_files)
        if covered is None:
            return None
        sites.extend(
            {"file": other, "line": line, "alias": alias}
            for line in reference_lines(text, pattern, covered)
        )
    return sites


def _binds_own(cache: Any, file_path: str, alias: str) -> bool | None:
    """``file_path`` 自己绑定 ``alias``（改名导入别的名字，或定义同名符号）。"""
    try:
        conn = cache.get_conn()
        imported = conn.execute(_OWN_IMPORT_SQL, (file_path, alias, alias)).fetchone()
        defined = conn.execute(_OWN_DEFINITION_SQL, (file_path, alias)).fetchone()
    except (sqlite3.Error, AttributeError):
        return None
    return imported is not None or defined is not None


__all__ = ["AliasCheck", "alias_reference_check"]
