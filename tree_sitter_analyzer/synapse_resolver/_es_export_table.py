"""#1764：一个 ES 模块（TS / JS）导出了什么——本地导出、再导出与 ``export *``。

``index.ts`` / ``external.ts`` 一类桶文件把名字从别的模块转出去：

* ``export { f, g as h } from './x'`` —— 具名再导出；
* ``export * from './x'`` —— 星号再导出（``default`` 不随之导出）；
* ``export * as ns from './x'`` —— 命名空间再导出。

``ExportTable.complete`` 为 False 表示文件里有无法判定导出名字的形式（``export =``、
解构导出、``module.exports``、带字符串名字的导出项……）；此时“某名字不在此文件导出”
无法证明，解析方不得据此在多个星号来源中认定唯一来源。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ._javascript_object_exports import _strip_comments

_IDENT = r"[A-Za-z_$][\w$]*"
_IDENT_RE = re.compile(rf"^{_IDENT}$")
_EXPORT_RE = re.compile(r"(?m)^[ \t]*export\b")
_SPEC = r"""(?P<quote>['"])(?P<spec>[^'"]+)(?P=quote)"""
_STAR_RE = re.compile(
    rf"^\s*(?:type\s+)?\*\s*(?:as\s+(?P<ns>{_IDENT})\s+)?from\s*{_SPEC}"
)
_STAR_STRING_NS_RE = re.compile(r"^\s*(?:type\s+)?\*\s*as\s*['\"]")
_BLOCK_RE = re.compile(r"^\s*(?:type\s+)?\{(?P<body>[^}]*)\}")
_FROM_RE = re.compile(rf"^\s*from\s*{_SPEC}")
_DEFAULT_RE = re.compile(r"^\s+default\b")
_DEFAULT_NAMED_RE = re.compile(
    rf"^\s+(?:async\s+)?function\b\s*\*?\s*(?P<fn>{_IDENT})?"
    rf"|^\s+(?:abstract\s+)?class\b\s*(?P<cls>{_IDENT})?"
    rf"|^\s+(?P<ident>{_IDENT})\s*;?[ \t]*(?:\n|$)"
)
_DECL_RE = re.compile(
    r"^\s+(?:declare\s+)?(?:async\s+)?"
    r"(?P<kw>function\s*\*?|(?:abstract\s+)?class|const\s+enum|enum|namespace|module"
    r"|interface|type|const|let|var)\s+"
    rf"(?P<name>{_IDENT})"
)
_DESTRUCTURED_RE = re.compile(r"^\s+(?:declare\s+)?(?:const|let|var)\s*[{\[]")
#: CommonJS 导出：名字集合无法从 ``export`` 语句得知。
_COMMONJS_RE = re.compile(r"(?m)^[ \t]*(?:module\.exports\b|exports\.[\w$]+[ \t]*=)")


@dataclass(frozen=True)
class ExportTable:
    """``local``：导出名 -> 本地标识符（匿名默认导出为 ``""``）；
    ``reexports``：导出名 -> ``(说明符, 被导入名)``，命名空间再导出的被导入名为 ``"*"``；
    ``stars``：``export * from`` 的说明符。"""

    local: dict[str, str] = field(default_factory=dict)
    reexports: dict[str, tuple[str, str]] = field(default_factory=dict)
    stars: tuple[str, ...] = ()
    complete: bool = True
    #: 默认导出的形态：``declaration``（``export default function/class``，具名或匿名）、
    #: ``ident``（``export default x`` / ``export { x as default }``）、``expression``
    #: （其余表达式）；没有默认导出为 ``""``。
    default_kind: str = ""


def parse_export_table(source: str) -> ExportTable:
    """解析一份源码的导出表（先去掉注释）。"""
    text = _strip_comments(source)
    local: dict[str, str] = {}
    reexports: dict[str, tuple[str, str]] = {}
    stars: list[str] = []
    kinds: list[str] = []
    complete = _COMMONJS_RE.search(text) is None
    for match in _EXPORT_RE.finditer(text):
        rest = text[match.end() :]
        if not _parse_one(rest, local, reexports, stars, kinds):
            complete = False
    default_kind = kinds[-1] if kinds else ("ident" if "default" in local else "")
    return ExportTable(local, reexports, tuple(stars), complete, default_kind)


def _parse_one(
    rest: str,
    local: dict[str, str],
    reexports: dict[str, tuple[str, str]],
    stars: list[str],
    kinds: list[str],
) -> bool:
    """解析 ``export`` 之后的一条语句；无法判定导出的名字时返回 False。"""
    star = _STAR_RE.match(rest)
    if star is not None:
        if star.group("ns"):
            reexports[star.group("ns")] = (star.group("spec"), "*")
        else:
            stars.append(star.group("spec"))
        return True
    if _STAR_STRING_NS_RE.match(rest):
        return False
    block = _BLOCK_RE.match(rest)
    if block is not None:
        source = _FROM_RE.match(rest[block.end() :])
        spec = source.group("spec") if source is not None else None
        return _parse_block(block.group("body"), spec, local, reexports)
    default = _DEFAULT_RE.match(rest)
    if default is not None:
        named = _DEFAULT_NAMED_RE.match(rest[default.end() :])
        ident = ""
        kind = "expression"
        if named is not None:
            ident = (
                named.group("fn") or named.group("cls") or named.group("ident") or ""
            )
            kind = "ident" if named.group("ident") else "declaration"
        local["default"] = ident
        kinds.append(kind)
        return True
    if _DESTRUCTURED_RE.match(rest):
        return False
    decl = _DECL_RE.match(rest)
    if decl is None:
        return False  # ``export =``、``export as namespace``、``export import x = …``
    name = decl.group("name")
    local[name] = name
    if decl.group("kw") in ("const", "let", "var"):
        return not _more_declarators(rest[decl.end() :])
    return True


def _parse_block(
    body: str,
    spec: str | None,
    local: dict[str, str],
    reexports: dict[str, tuple[str, str]],
) -> bool:
    ok = True
    for raw in body.split(","):
        item = raw.strip()
        if item.startswith("type "):
            item = item[len("type ") :].strip()
        if not item:
            continue
        inner, _, exported = (part.strip() for part in item.partition(" as "))
        exported = exported or inner
        if not _IDENT_RE.match(inner) or not _IDENT_RE.match(exported):
            ok = False  # 字符串名字（``"a-b"``）：名字集合不可知。
            continue
        if spec is None:
            local[exported] = inner
        else:
            reexports[exported] = (spec, inner)
    return ok


def _more_declarators(rest: str) -> bool:
    """``export const a = 1, b = 2``：同一行顶层逗号后还有声明。"""
    line = rest.split("\n", 1)[0]
    depth = 0
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
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
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            if re.match(rf"\s*{_IDENT}\s*(?:[=:,;]|$)", line[i + 1 :]):
                return True
        i += 1
    return False


__all__ = ["ExportTable", "parse_export_table"]
