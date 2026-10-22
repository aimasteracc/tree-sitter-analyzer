"""#1741：经导入对象调用的 JavaScript 函数（``import utils from './utils.js'; utils.findKey()``）。

axios 一类代码把模块的函数收进默认导出的对象字面量（``export default { findKey, ... }``），
调用方 ``import utils from '../utils.js'`` 后写 ``utils.findKey(...)``。原解析器只认无接收者
与 ``this`` 的调用，这类边全部是 ``unknown``：dogfood 第 10 轮 axios 的调用点召回 17/53，
36 个漏掉的调用点没有一个出现在任何证据字段里。

这里只在以下全部成立时绑定（否则返回 ``None``，交回原有级联，不猜）：

* 接收者是调用文件里的**默认导入**（``obj.m()``），或**命名空间导入**
  （``ns.m()`` 取具名导出，``ns.default.m()`` 取默认导出），说明符为相对路径且落在
  已索引的项目文件上；
* 目标模块的默认导出是对象字面量（直接写出，或 ``export default IDENT`` 指向同文件
  ``const IDENT = { ... }``），其中恰有一个成员名为 ``m``：简写 ``m``、``m: ident``，
  或经 ``...spread`` 展开的另一个默认导入（如 axios ``platform/index.js``）；
  命名空间的具名导出须是 ``export function m`` / ``export const m =`` / ``export { m }``；
* 成员最终指向一个顶层 ``function`` 定义（同文件，或沿导入继续找，最多 ``MAX_HOPS`` 跳）；
* 调用文件没有给 ``obj.m`` 赋值（``utils.findKey = fake`` 之后调用的就不是它了）。

读不到源码、对象里有计算键或重复成员、导出形状无法判定时一律不绑定。
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any

from ._typescript_imports import resolve_typescript_specifier

if TYPE_CHECKING:
    from ._imports import ImportEntry

#: 沿默认导出 / 再导出追踪的最大跳数（与 Python 再导出一致）。
MAX_HOPS = 4
#: 可读源码的上限；更大的文件（打包产物）不解析。
_MAX_SOURCE_BYTES = 2_000_000
_IDENT = r"[A-Za-z_$][\w$]*"
_IDENT_RE = re.compile(rf"^{_IDENT}$")
_EXPORT_DEFAULT_RE = re.compile(r"(?m)^[ \t]*export[ \t]+default[ \t]+")
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


class ObjectExportResolver:
    """按文件记忆源码与默认导出成员；一次索引构建内共享。"""

    def __init__(
        self,
        *,
        project_root: str | None,
        imports_by_file: dict[str, list[ImportEntry]],
        indexed_files: frozenset[str],
        file_symbols: dict[str, list[tuple[str, str, int]]],
        variables: dict[str, dict[str, list[tuple[int, int]]]] | None = None,
    ) -> None:
        self._root = project_root
        self._imports = imports_by_file
        self._indexed = indexed_files
        self._symbols = file_symbols
        #: ``const f = (…) => …`` 以 ``variable`` 入索引：``文件 -> 名 -> [(符号 id, 行)]``。
        self._variables = variables or {}
        self._text: dict[str, str | None] = {}
        self._members: dict[str, dict[str, list[str]] | None] = {}

    # ------------------------------------------------------------------ public
    def resolve(
        self, receiver: str, simple: str, caller_file: str
    ) -> tuple[int, str] | None:
        """``receiver.simple()`` 的 ``(符号 id, 定义文件)``；无法证明时为 None。"""
        if not self._root or not _IDENT_RE.match(simple):
            return None
        head, _, rest = receiver.partition(".")
        if not _IDENT_RE.match(head) or rest not in ("", "default"):
            return None
        entry = self._binding(caller_file, head)
        if entry is None:
            return None
        target = resolve_typescript_specifier(
            entry.module_path, caller_file, self._indexed
        )
        if not target:
            return None
        if self._assigned_in(caller_file, head, simple):
            return None
        if entry.is_star and rest == "":
            # ``import * as ns``：``ns.m()`` 是具名导出 ``m``。
            return self._named_export(target, simple, 0)
        if entry.is_star:
            # 命名空间的 ``ns.default.m()``。
            return self._default_member(target, simple, 0)
        if rest or not self._is_default_clause(caller_file, head):
            # ``import { obj }`` 与 ``import obj`` 在导入表里同形，须看源码区分。
            return None
        return self._default_member(target, simple, 0)

    # ----------------------------------------------------------------- binding
    def _binding(self, caller_file: str, local: str) -> ImportEntry | None:
        """``local`` 在调用文件中唯一的一条相对导入绑定（默认或命名空间）。"""
        found = [
            e
            for e in self._imports.get(caller_file, [])
            if e.local_name == local and e.is_relative
        ]
        if len(found) != 1:
            return None
        entry = found[0]
        if not entry.is_star and entry.alias_of:
            # ``import { a as local }`` 是具名导入，不是模块对象。
            return None
        return entry

    def _named_import_source(
        self, file_path: str, local: str
    ) -> tuple[str, str] | None:
        """``import { name as local }`` / ``import local from``：``(目标文件, 导出名)``。"""
        for e in self._imports.get(file_path, []):
            if e.local_name != local or not e.is_relative or e.is_star:
                continue
            target = resolve_typescript_specifier(
                e.module_path, file_path, self._indexed
            )
            if not target:
                return None
            return target, e.alias_of or local
        return None

    # ----------------------------------------------------------------- exports
    def _default_member(
        self, file_path: str, name: str, hops: int
    ) -> tuple[int, str] | None:
        if hops > MAX_HOPS:
            return None
        members = self._default_members(file_path)
        if members is None:
            return None
        values = members.get(name, [])
        spreads = members.get("...", [])
        if len(values) > 1:
            return None
        if len(values) == 1:
            return self._local_value(file_path, values[0], hops)
        # 不在字面量里：只能来自展开的另一个默认导入或命名空间导入，且只能有一个来源。
        found: list[tuple[int, str]] = []
        for spread in spreads:
            source = self._default_import_target(file_path, spread)
            if source is not None:
                hit = self._default_member(source, name, hops + 1)
            else:
                namespace = self._namespace_import_target(file_path, spread)
                if namespace is None:
                    return None  # 展开了无法追踪的对象：可能就含 ``name``。
                exports = self._named_export_map(namespace)
                if exports is None:
                    return None  # ``export *`` 或读不到：成员集合未知。
                hit = (
                    self._named_export(namespace, name, hops + 1)
                    if name in exports
                    else None
                )
                if name in exports and hit is None:
                    return None  # 来源确有该名字但无法定位定义：不猜。
            if hit is not None:
                found.append(hit)
        return found[0] if len(found) == 1 else None

    def _local_value(
        self, file_path: str, ident: str, hops: int
    ) -> tuple[int, str] | None:
        """``file_path`` 中名为 ``ident`` 的顶层函数，或沿具名导入找到的定义。"""
        sym = _function_id(self._symbols, file_path, ident)
        if sym is None:
            sym = self._function_variable_id(file_path, ident)
        if sym is not None:
            return sym, file_path
        source = self._named_import_source(file_path, ident)
        if source is None or hops >= MAX_HOPS:
            return None
        target, exported = source
        return self._named_export(target, exported, hops + 1)

    def _named_export(
        self, file_path: str, name: str, hops: int
    ) -> tuple[int, str] | None:
        exports = self._named_export_map(file_path)
        local = exports.get(name) if exports is not None else None
        if local is None:
            return None
        return self._local_value(file_path, local, hops)

    def _named_export_map(self, file_path: str) -> dict[str, str] | None:
        """具名导出 ``导出名 -> 本地名``；含 ``export *`` 或读不到源码时为 None。"""
        text = self._source(file_path)
        if text is None:
            return None
        return _named_exports(_strip_comments(text))

    def _namespace_import_target(self, file_path: str, local: str) -> str | None:
        for e in self._imports.get(file_path, []):
            if e.local_name == local and e.is_relative and e.is_star:
                return (
                    resolve_typescript_specifier(
                        e.module_path, file_path, self._indexed
                    )
                    or None
                )
        return None

    def _default_import_target(self, file_path: str, local: str) -> str | None:
        for e in self._imports.get(file_path, []):
            if (
                e.local_name == local
                and e.is_relative
                and not e.is_star
                and not e.alias_of
                and self._is_default_clause(file_path, local)
            ):
                return (
                    resolve_typescript_specifier(
                        e.module_path, file_path, self._indexed
                    )
                    or None
                )
        return None

    def _default_members(self, file_path: str) -> dict[str, list[str]] | None:
        """默认导出对象的成员：``名 -> [本地标识符]``，展开项记在 ``"..."`` 下。"""
        if file_path in self._members:
            return self._members[file_path]
        result = None
        text = self._source(file_path)
        if text is not None:
            body = _default_object_text(_strip_comments(text))
            if body is not None:
                result = _parse_members(body)
        self._members[file_path] = result
        return result

    # ------------------------------------------------------------------ source
    def _source(self, rel_path: str) -> str | None:
        if rel_path not in self._text:
            value: str | None = None
            try:
                full = os.path.join(str(self._root), rel_path)
                if os.path.getsize(full) <= _MAX_SOURCE_BYTES:
                    with open(full, encoding="utf-8") as handle:
                        value = handle.read()
            except (OSError, UnicodeDecodeError, TypeError, ValueError):
                value = None
            self._text[rel_path] = value
        return self._text[rel_path]

    def _function_variable_id(self, file_path: str, name: str) -> int | None:
        """唯一一个初值为函数 / 箭头函数的 ``const|let|var name`` 的符号 id。"""
        rows = self._variables.get(file_path, {}).get(name, [])
        if len(rows) != 1:
            return None
        sym_id, line = rows[0]
        text = self._source(file_path)
        if text is None:
            return None
        lines = text.splitlines()
        if not 0 < line <= len(lines):
            return None
        decl = lines[line - 1]
        pattern = (
            rf"^[ \t]*(?:export[ \t]+)?(?:const|let|var)[ \t]+{re.escape(name)}[ \t]*=[ \t]*"
            rf"(?:async[ \t]+)?(?:function\b|\([^)]*\)?[ \t]*(?:=>|$)|{_IDENT}[ \t]*=>)"
        )
        return sym_id if re.match(pattern, decl) else None

    def _is_default_clause(self, caller_file: str, local: str) -> bool:
        """``local`` 是 ``import local from`` / ``import local, { … } from`` 的默认绑定。"""
        text = self._source(caller_file)
        if text is None:
            return False
        pattern = rf"(?m)^[ \t]*import[ \t]+{re.escape(local)}[ \t]*(?:,|from\b)"
        return re.search(pattern, text) is not None

    def _assigned_in(self, caller_file: str, head: str, name: str) -> bool:
        """调用文件给 ``head.name`` 赋值；读不到源码按“已赋值”处理。"""
        text = self._source(caller_file)
        if text is None:
            return True
        pattern = (
            rf"(?<![\w$.]){re.escape(head)}[ \t]*\.[ \t]*{re.escape(name)}[ \t]*=(?!=)"
        )
        return re.search(pattern, text) is not None


def _function_id(
    symbols: dict[str, list[tuple[str, str, int]]], file_path: str, name: str
) -> int | None:
    ids = [
        sid
        for n, kind, sid in symbols.get(file_path, [])
        if n == name and kind == "function"
    ]
    return ids[0] if len(ids) == 1 else None


def _named_exports(text: str) -> dict[str, str] | None:
    """``导出名 -> 本地名``；``export * from`` 让集合不可知，返回 None。"""
    if re.search(r"(?m)^[ \t]*export[ \t]*\*", text):
        return None
    out: dict[str, str] = {}
    for name in re.findall(
        rf"(?m)^[ \t]*export[ \t]+(?:async[ \t]+)?(?:function\*?|const|let|var|class)[ \t]+({_IDENT})",
        text,
    ):
        out[name] = name
    for block in re.findall(r"(?m)^[ \t]*export[ \t]*\{([^}]*)\}", text):
        for part in block.split(","):
            item = part.strip()
            if not item:
                continue
            local, _, exported = item.partition(" as ")
            out[(exported or local).strip()] = local.strip()
    return out


def _strip_comments(text: str) -> str:
    return _LINE_COMMENT_RE.sub("", _BLOCK_COMMENT_RE.sub("", text))


def _default_object_text(text: str) -> str | None:
    """默认导出对象字面量的花括号内文本；导出不是对象（或无法判定）时为 None。"""
    matches = list(_EXPORT_DEFAULT_RE.finditer(text))
    if len(matches) != 1:
        return None
    rest = text[matches[0].end() :]
    if rest.startswith("{"):
        return _balanced(rest)
    ident = re.match(rf"({_IDENT})[ \t]*;?[ \t]*(?:\n|$)", rest)
    if ident is None:
        return None
    decl = list(
        re.finditer(
            rf"(?m)^[ \t]*(?:const|let|var)[ \t]+{re.escape(ident.group(1))}[ \t]*=[ \t]*",
            text,
        )
    )
    if len(decl) != 1:
        return None
    after = text[decl[0].end() :]
    return _balanced(after) if after.startswith("{") else None


def _balanced(text: str) -> str | None:
    """``text`` 以 ``{`` 开头时，与之配对的 ``}`` 之间的内容（跳过字符串）。"""
    depth = 0
    quote = ""
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "\"'`":
            quote = ch
        elif ch in "{([":
            depth += 1
        elif ch in "})]":
            depth -= 1
            if depth == 0:
                return text[1:i]
            if depth < 0:
                return None
        i += 1
    return None


def _split_top_level(body: str) -> list[str] | None:
    parts: list[str] = []
    depth = 0
    quote = ""
    start = 0
    i = 0
    while i < len(body):
        ch = body[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "\"'`":
            quote = ch
        elif ch in "{([":
            depth += 1
        elif ch in "})]":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(body[start:i])
            start = i + 1
        i += 1
    if depth != 0 or quote:
        return None
    parts.append(body[start:])
    return [p.strip() for p in parts if p.strip()]


def _parse_members(body: str) -> dict[str, list[str]] | None:
    """成员表；出现计算键（``[k]: v``）时整张表不可信，返回 None。"""
    parts = _split_top_level(body)
    if parts is None:
        return None
    members: dict[str, list[str]] = {}
    for part in parts:
        if part.startswith("..."):
            spread = part[3:].strip()
            if not _IDENT_RE.match(spread):
                return None
            members.setdefault("...", []).append(spread)
            continue
        if part.startswith("["):
            return None
        if _IDENT_RE.match(part):
            members.setdefault(part, []).append(part)
            continue
        pair = re.match(rf"^(['\"]?)({_IDENT})\1[ \t]*:[ \t]*(.+)$", part, re.DOTALL)
        if pair is not None:
            value = pair.group(3).strip()
            # 只有值是标识符时才能指向定义；其余（字面量、内联函数、表达式）记为空值。
            members.setdefault(pair.group(2), []).append(
                value if _IDENT_RE.match(value) else ""
            )
            continue
        method = re.match(rf"^(?:async[ \t]+)?\*?[ \t]*({_IDENT})[ \t]*\(", part)
        if method is not None:
            members.setdefault(method.group(1), []).append("")
            continue
        return None
    return members


def export_shape(source: str) -> dict[str, Any] | None:
    """范围回填的解析面（#1696）：默认导出对象的成员 / 展开，以及具名导出。

    这些形状决定 ``obj.m()`` 的解析却不产生符号；没有默认导出也没有具名导出时为 None。
    """
    text = _strip_comments(source)
    named = sorted(
        set(
            re.findall(
                rf"(?m)^[ \t]*export[ \t]+(?:async[ \t]+)?(?:function\*?|const|let|var)[ \t]+({_IDENT})",
                text,
            )
        )
        | {
            part.split(" as ")[-1].strip()
            for block in re.findall(r"(?m)^[ \t]*export[ \t]*\{([^}]*)\}", text)
            for part in block.split(",")
            if part.strip()
        }
    )
    has_default = _EXPORT_DEFAULT_RE.search(text) is not None
    if not has_default and not named:
        return None
    shape: dict[str, Any] = {"named": named}
    if has_default:
        body = _default_object_text(text)
        members = _parse_members(body) if body is not None else None
        shape["default"] = (
            None
            if members is None
            else {name: sorted(values) for name, values in sorted(members.items())}
        )
    return shape


def build_object_export_resolver(
    *,
    project_root: str | None,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    conn: Any = None,
) -> ObjectExportResolver:
    return ObjectExportResolver(
        project_root=project_root,
        imports_by_file=imports_by_file,
        indexed_files=frozenset(file_languages),
        file_symbols=file_symbols,
        variables=_js_variables(conn, file_languages),
    )


def _js_variables(
    conn: Any, file_languages: dict[str, str]
) -> dict[str, dict[str, list[tuple[int, int]]]]:
    """JS 文件里 ``variable`` 符号：``文件 -> 名 -> [(id, 行)]``；读取失败为空。"""
    if conn is None:
        return {}
    try:
        rows = conn.execute(
            "SELECT id, name, file_path, line FROM ast_symbol_rows WHERE kind = 'variable'"
        ).fetchall()
    except Exception:  # nosec B110 — 表缺失时退化为不绑定箭头函数。
        return {}
    out: dict[str, dict[str, list[tuple[int, int]]]] = {}
    for row in rows:
        file_path = row[2]
        if file_languages.get(file_path) not in ("javascript", "jsx"):
            continue
        out.setdefault(file_path, {}).setdefault(row[1], []).append(
            (int(row[0]), int(row[3] or 0))
        )
    return out


__all__ = ["MAX_HOPS", "ObjectExportResolver", "build_object_export_resolver"]
