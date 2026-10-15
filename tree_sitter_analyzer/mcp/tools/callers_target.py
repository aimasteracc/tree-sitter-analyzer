"""nav callers 的目标存在性：0 个调用方只有在目标确有定义时才可能是事实（#1606）。

dogfood 第 4 轮实测：``NoSuchClass._get_plugin``、``PluginManager._get_plugin``
（真实类，但未定义该方法）与 ``no_such_function_xyz`` 都答 ``complete, 0``——
旧检查用 ``rpartition`` 丢掉类限定，只要求裸方法名在索引中出现过。

本模块要求精确的（限定）目标解析到索引中的定义：

* 裸名：存在同名的定义行。
* ``Owner.name``：存在名为 ``Owner`` 的类型定义，且 ``name`` 的定义行位于其
  行范围之内；或 ``Owner`` 是声明 ``name`` 的文件的模块名。Go/Rust/C/C++ 的方法
  可在类型体之外以接收者声明，这些语言只要求同名类型存在。

解析不到定义时给出候选：定义了该方法的类（``Class.name``），或拼写相近的符号。
"""

from __future__ import annotations

import difflib
import os
import sqlite3
from dataclasses import dataclass
from typing import Any

#: 目标没有解析到任何已索引定义。
NOT_DEFINED_REASON = "SYMBOL_NOT_DEFINED"
#: 定义行无法读取，存在性未知。
UNCHECKED_REASON = "SYMBOL_DEFINITION_UNCHECKED"

#: 可作为方法所有者的定义种类。
_OWNER_KINDS = ("class", "interface", "struct", "enum", "trait", "record", "object")
#: 方法可在类型体之外（以接收者）声明的语言：只要求同名类型存在。
_DETACHED_METHOD_LANGUAGES = frozenset({"go", "rust", "c", "cpp"})
#: 响应中给出的候选上限。
_MATCHES_CAP = 5
#: 拼写相近候选的相似度下限（difflib 默认值）。
_SIMILARITY_CUTOFF = 0.6


@dataclass(frozen=True)
class TargetResolution:
    """``defined`` 为 None 表示读取失败；``close_matches`` 仅在未定义时非空。"""

    defined: bool | None
    close_matches: tuple[str, ...] = ()


def resolve_target(
    cache: Any, project_root: str, func_name: str, file_path: str | None
) -> TargetResolution:
    """判断精确目标是否解析到已索引定义；未解析时附带候选。"""
    owner, _sep, bare = func_name.rpartition(".")
    wanted_file = _relative(project_root, file_path)
    try:
        conn = cache.get_conn()
        rows = [
            (str(row[0]), int(row[1]), int(row[2]), str(row[3]))
            for row in conn.execute(
                "SELECT file_path, line, end_line, language FROM ast_symbol_rows "
                "WHERE name = ?",
                (bare,),
            )
        ]
        if wanted_file:
            rows = [row for row in rows if row[0] == wanted_file]
        if _defined(conn, rows, owner.rpartition(".")[2]):
            return TargetResolution(True)
        return TargetResolution(False, _close_matches(conn, bare, rows, owner))
    except (sqlite3.Error, AttributeError):
        return TargetResolution(None)


def _relative(project_root: str, file_path: str | None) -> str:
    """把调用方点名的文件统一为索引使用的相对 POSIX 路径。"""
    if not file_path:
        return ""
    path = file_path
    if os.path.isabs(path):
        try:
            path = os.path.relpath(path, project_root)
        except ValueError:
            return path.replace("\\", "/")
    return path.replace("\\", "/")


def _owner_rows(conn: Any, owner: str) -> list[tuple[str, int, int]]:
    marks = ",".join("?" * len(_OWNER_KINDS))
    return [
        (str(row[0]), int(row[1]), int(row[2]))
        for row in conn.execute(
            "SELECT file_path, line, end_line FROM ast_symbol_rows "  # nosec B608
            f"WHERE name = ? AND kind IN ({marks})",
            (owner, *_OWNER_KINDS),
        )
    ]


def _defined(conn: Any, rows: list[tuple[str, int, int, str]], owner: str) -> bool:
    """限定名要求定义位于所有者类型之内（或所有者是其模块名）。"""
    if not rows:
        return False
    if not owner:
        return True
    owners = _owner_rows(conn, owner)
    for path, line, _end, language in rows:
        if _module_name(path) == owner:
            return True
        if language in _DETACHED_METHOD_LANGUAGES and owners:
            return True
        if any(
            o_path == path and o_line <= line <= max(o_end, o_line)
            for o_path, o_line, o_end in owners
        ):
            return True
    return False


def _module_name(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def _close_matches(
    conn: Any, bare: str, rows: list[tuple[str, int, int, str]], owner: str
) -> tuple[str, ...]:
    """同名方法所在的类；没有同名定义时退回拼写相近的已索引符号名。"""
    if not rows:
        rows = [
            (str(row[0]), int(row[1]), int(row[2]), str(row[3]))
            for row in conn.execute(
                "SELECT file_path, line, end_line, language FROM ast_symbol_rows "
                "WHERE name = ?",
                (bare,),
            )
        ]
    if rows:
        return _owning_types(conn, bare, rows, owner)
    names = [
        str(row[0]) for row in conn.execute("SELECT DISTINCT name FROM ast_symbol_rows")
    ]
    similar = difflib.get_close_matches(
        bare, names, n=_MATCHES_CAP, cutoff=_SIMILARITY_CUTOFF
    )
    return tuple(similar)


def _owning_types(
    conn: Any, bare: str, rows: list[tuple[str, int, int, str]], owner: str
) -> tuple[str, ...]:
    """定义了 ``bare`` 的最内层类型名，形如 ``Class.bare``；不在类型内则为裸名。"""
    marks = ",".join("?" * len(_OWNER_KINDS))
    found: set[str] = set()
    for path, line, _end, _language in rows:
        enclosing = conn.execute(
            "SELECT name FROM ast_symbol_rows "  # nosec B608
            f"WHERE file_path = ? AND kind IN ({marks}) AND line <= ? "
            "AND end_line >= ? ORDER BY line DESC LIMIT 1",
            (path, *_OWNER_KINDS, line, line),
        ).fetchone()
        found.add(f"{enclosing[0]}.{bare}" if enclosing else bare)
    # 未限定的询问已经定义过，不会走到这里；限定名的候选排除用户写的那个。
    candidates = sorted(name for name in found if name != f"{owner}.{bare}")
    return tuple(candidates[:_MATCHES_CAP])


def not_defined_hint(func_name: str, resolution: TargetResolution) -> str:
    """未解析目标的提示：说明 0 不是证据，并点名候选与刷新命令。"""
    from .relation_freshness import REFRESH_COMMAND

    if resolution.defined is None:
        return (
            f"Whether {func_name!r} is defined in the index could not be read, so "
            "0 callers is not evidence of absence."
        )
    refresh = (
        f"if the symbol was added since the last index, run {REFRESH_COMMAND} first."
    )
    if resolution.close_matches:
        advice = (
            f"Close matches: {', '.join(resolution.close_matches)}. Retry with one "
            f"of them; {refresh}"
        )
    else:
        advice = f"No similarly named symbol is indexed; {refresh}"
    return (
        f"Symbol {func_name!r} is not in the index (no indexed definition "
        f"matches it), so 0 callers is not evidence of absence. {advice}"
    )
