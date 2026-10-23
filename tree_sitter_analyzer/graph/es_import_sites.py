"""#1764：经导入调用、却没能解析的 TS / JS 调用点，对每个同名目标都可见。

未解析的调用边只有一个占位目标：调用文件里的同名节点（``jwt.ts:verifying:183``）。
按定义文件筛选入边时（``_direct_callers``），这条边既不指向定义文件、也不出自定义文件，
于是从 ``unresolved_inbound_sites`` 里消失——hono ``verifying`` 唯一的真实调用
``await verifying(…)``（``src/utils/jwt/jwt.ts:183``）既不在调用方里，也不在任何证据
字段里；答复只因导入行算作非调用引用才没有成为错误的 ``complete``。

ES 模块里，另一个文件中的裸调用 ``f()`` 只能经导入绑定到达定义文件里的 ``f``，
``ns.f()`` 只能经导入的 ``ns``。所以这里补回的调用点是：调用文件导入了被调名
（或接收者的首段），边未解析，且两端都是 ES 模块语言。没有导入的同名调用
（局部变量、参数）不可能指向别的模块里的定义，不计入。
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable, Collection, Iterable
from typing import Any

#: ES 模块语言（与 ``languages_compatible`` 的 JS/TS 家族一致）。
ES_LANGUAGES = frozenset({"javascript", "jsx", "typescript", "tsx"})

_IMPORTED_SQL = (
    "SELECT 1 FROM ast_imports WHERE file_path = ? AND local_name = ? LIMIT 1"
)
_LANGUAGE_SQL = "SELECT language FROM ast_index WHERE file_path = ?"
_ROWS_SQL = (
    "SELECT * FROM edges WHERE kind = 'calls' AND callee_name = ? "
    "ORDER BY source_node_id, target_node_id, line"
)


def imported_unresolved_rows(
    conn: sqlite3.Connection,
    callee_name: str,
    callee_file: str,
    seen: Collection[int],
    *,
    is_resolved: Callable[[Any], bool],
    source_file: Callable[[Any], str],
) -> list[Any]:
    """未解析、调用文件经导入用到这个名字、且被定义文件筛选掉的 CALLS 行。"""
    if not callee_name or "." in callee_name or not callee_file:
        return []
    try:
        if _language(conn, callee_file) not in ES_LANGUAGES:
            return []
        rows = conn.execute(_ROWS_SQL, (callee_name,)).fetchall()
    except sqlite3.Error:
        return []
    out: list[Any] = []
    imported: dict[tuple[str, str], bool] = {}
    for row in _renamed_import_rows(conn, callee_name, callee_file):
        if row["id"] not in seen and not is_resolved(row):
            out.append(row)
    for row in rows:
        if row["id"] in seen or is_resolved(row):
            continue
        caller_file = source_file(row)
        if not caller_file or caller_file == callee_file:
            continue
        if str(_value(row, "language") or "") not in ES_LANGUAGES:
            continue
        head = _head(str(_value(row, "callee_full") or callee_name))
        key = (caller_file, head)
        if key not in imported:
            imported[key] = _imports(conn, caller_file, head)
        if imported[key]:
            out.append(row)
    return out


#: #1768：直接导入 ``callee_file`` 的文件里，以另一个本地名导入的绑定（改名的默认导入
#: ``import makeSig from './jws'``、``import { signer as s }``）。对它们未解析的裸调用
#: 可能就是 ``callee_file`` 默认导出 / 改名导出的那个函数。
_RENAMED_SQL = (
    "SELECT DISTINCT i.file_path, i.local_name, i.alias_of FROM edges m JOIN ast_imports i "
    "ON i.file_path = m.file_path AND m.target_node_id = 'module:' || i.module_path "
    "WHERE m.kind = 'imports' AND m.callee_resolved_file = ? AND i.is_star = 0 "
    "AND i.local_name <> '' AND i.local_name <> ?"
)
_LOCAL_CALLS_SQL = (
    "SELECT * FROM edges WHERE kind = 'calls' AND callee_name = ? AND file_path = ? "
    "AND callee_full = callee_name"
)


def _renamed_import_rows(
    conn: sqlite3.Connection, callee_name: str, callee_file: str
) -> list[Any]:
    """经改名导入调用、且没能解析的裸调用行（解析器绑定了的经 ``import_alias`` 可见）。"""
    try:
        bindings = conn.execute(_RENAMED_SQL, (callee_file, callee_name)).fetchall()
    except sqlite3.Error:
        return []
    exports: dict[str, Any] | None = None
    defined: set[str] = set()
    statements: dict[str, list[str]] = {}
    if bindings:
        try:
            exports = _export_shape(conn, callee_file)
            defined = _definitions(conn, callee_file)
        except sqlite3.Error:
            exports = None  # 读不到导出表：每个改名绑定都保留。
    try:
        return [
            row
            for file_path, local, alias_of in bindings
            if _may_reach(
                exports,
                defined,
                callee_name,
                str(local),
                str(alias_of or ""),
                _binding_form(conn, str(file_path), str(local), statements),
            )
            for row in conn.execute(_LOCAL_CALLS_SQL, (local, file_path)).fetchall()
        ]
    except sqlite3.Error:
        return []


def _may_reach(
    exports: dict[str, Any] | None,
    defined: set[str],
    callee_name: str,
    local: str,
    alias_of: str,
    form: str = "",
) -> bool:
    """导入 ``local``（原名 ``alias_of``）的绑定可能就是 ``callee_name``。

    只在声明文件的导出表能证明它指向别的函数 / 类声明（或不存在）时排除：
    ``import en from './en'`` 而默认导出是匿名函数，``en()`` 到不了 ``getTypeName``。
    导出指向变量（``const x = f; export { x }``）、表达式或未知来源时保留。
    """
    if exports is None or not isinstance(exports.get("locals"), dict):
        return True
    locals_: dict[str, str] = exports["locals"]
    reexported = {str(item[0]) for item in exports.get("reexports") or []}
    open_names = bool(exports.get("stars")) or not exports.get("complete", True)
    # ``form``：``default`` / ``named``（读自导入语句）；读不到时两种都算。
    if alias_of:
        candidates = [alias_of]
    elif form == "default":
        candidates = ["default"]
    elif form == "named":
        candidates = [local]
    else:
        candidates = [local, "default"]
    for exported in candidates:
        if exported in locals_:
            target = str(locals_[exported] or "")
            if target == callee_name:
                return True
            if exported == "default" and exports.get("default_kind") == "expression":
                return True
            functions = defined | set(exports.get("function_consts") or [])
            aliased = (exports.get("const_aliases") or {}).get(target)
            if aliased:
                # 一跳别名（``const __x = x``）：指向目标，或指向另一个声明。
                if aliased == callee_name or aliased not in functions:
                    return True
                continue
            if target and target not in functions:
                return True  # 变量或导入的别名：可能就是目标。
            continue
        if exported in reexported or (exported != "default" and open_names):
            return True
    return False


def _binding_form(
    conn: sqlite3.Connection,
    file_path: str,
    local: str,
    statements: dict[str, list[str]],
) -> str:
    """``local`` 在 ``file_path`` 的导入语句里是默认绑定还是具名绑定；读不到为 ``""``。

    导入表里 ``import x from`` 与 ``import { x } from`` 同形，只能看语句文本。
    """
    if file_path not in statements:
        statements[file_path] = _import_statements(conn, file_path)
    symbols = statements[file_path]
    default = re.compile(rf"^\s*import\s+(?:type\s+)?{re.escape(local)}\s*(?:,|from\b)")
    named = re.compile(rf"\{{[^}}]*(?<![\w$]){re.escape(local)}(?![\w$])[^}}]*\}}")
    forms = set()
    for text in symbols:
        if default.search(text):
            forms.add("default")
        elif named.search(text):
            forms.add("named")
    return forms.pop() if len(forms) == 1 else ""


def _import_statements(conn: sqlite3.Connection, file_path: str) -> list[str]:
    """``file_path`` 的导入语句文本；读不到为空（形态未知，两种都算）。"""
    try:
        row = conn.execute(
            "SELECT symbols_json FROM ast_index WHERE file_path = ?", (file_path,)
        ).fetchone()
        symbols = (json.loads(row[0] or "{}").get("symbols") or []) if row else []
    except (sqlite3.Error, TypeError, ValueError, AttributeError):
        return []
    return [
        str(s.get("text") or "")
        for s in symbols
        if isinstance(s, dict) and s.get("kind") == "import"
    ]


def _export_shape(conn: sqlite3.Connection, file_path: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT symbols_json FROM ast_index WHERE file_path = ?", (file_path,)
    ).fetchone()
    try:
        shape = json.loads(row[0] or "{}").get("js_exports") if row else None
    except (TypeError, ValueError, AttributeError):
        return None
    return shape if isinstance(shape, dict) else None


def _definitions(conn: sqlite3.Connection, file_path: str) -> set[str]:
    """``file_path`` 里函数与类声明的名字（导出指向它们时，目标不是别的名字）。"""
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM ast_symbol_rows WHERE file_path = ? "
            "AND kind IN ('function', 'class')",
            (file_path,),
        )
    }


def _head(callee_full: str) -> str:
    """``f`` -> ``f``；``z.core.f`` -> ``z``（接收者首段，即导入的绑定名）。"""
    return callee_full.split(".", 1)[0].split("(", 1)[0].strip()


def _imports(conn: sqlite3.Connection, file_path: str, local: str) -> bool:
    try:
        return conn.execute(_IMPORTED_SQL, (file_path, local)).fetchone() is not None
    except sqlite3.Error:
        return True  # 读不到导入表：保守地保留调用点。


def _language(conn: sqlite3.Connection, file_path: str) -> str:
    row = conn.execute(_LANGUAGE_SQL, (file_path,)).fetchone()
    return str(row[0] or "") if row is not None else ""


def _value(row: Any, key: str) -> Any:
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


def row_ids(rows: Iterable[Any]) -> set[int]:
    return {int(row["id"]) for row in rows}


__all__ = ["ES_LANGUAGES", "imported_unresolved_rows", "row_ids"]
