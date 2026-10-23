"""#1764：TypeScript 跨文件调用经导入绑定到定义（具名、命名空间与经 index.ts 的再导出）。

解析之前 TS 调用边只有 ``local`` / ``builtin`` / ``unknown``：导入的函数（``import { f }
from './m'``）、命名空间成员（``import * as ns``；``ns.f()``、``ns.sub.f()``）与导入的类的
静态成员（``Cls.m()``）都留在 ``unknown``。这里在抽取时记录每个 TS 文件的导入绑定与导出
形状（``symbols_json`` 的 ``ts_imports`` / ``ts_exports``，也是范围回填的解析面），解析时
沿相对说明符与再导出链找到定义。

只在能证明时绑定：

* 只看相对说明符（``./`` / ``../``）；包名（``zod/v4``、``react``）从不解析为项目文件。
* 默认导入（``import D from``）与 ``import type`` 不参与（默认导出的形状不由名字决定）。
* 导出必须能追到唯一的顶层函数（裸调用 / 命名空间调用）或唯一的类（``Cls.m()``）；
  ``export *`` 展开到多个同名定义、链过深或成环时不绑定。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ._typescript_imports import resolve_typescript_specifier

_IDENT = r"[A-Za-z_$][\w$]*"
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"(?m)(^|[^:\\'\"])//[^\n]*")
_SPEC = r"""(?P<q>['"])(?P<spec>[^'"]+)(?P=q)"""

_IMPORT_NAMED_RE = re.compile(
    rf"(?m)^[ \t]*import[ \t]+(?!type[ \t\{{])(?:{_IDENT}[ \t]*,[ \t]*)?\{{(?P<names>[^}}]*)\}}[ \t]*from[ \t]*{_SPEC}"
)
_IMPORT_NAMESPACE_RE = re.compile(
    rf"(?m)^[ \t]*import[ \t]+(?!type[ \t])(?:{_IDENT}[ \t]*,[ \t]*)?\*[ \t]*as[ \t]+(?P<local>{_IDENT})[ \t]*from[ \t]*{_SPEC}"
)
_EXPORT_FROM_RE = re.compile(
    rf"(?m)^[ \t]*export[ \t]+(?!type[ \t\{{])\{{(?P<names>[^}}]*)\}}[ \t]*from[ \t]*{_SPEC}"
)
_EXPORT_STAR_RE = re.compile(rf"(?m)^[ \t]*export[ \t]*\*[ \t]*from[ \t]*{_SPEC}")
_EXPORT_STAR_AS_RE = re.compile(
    rf"(?m)^[ \t]*export[ \t]*\*[ \t]*as[ \t]+(?P<local>{_IDENT})[ \t]*from[ \t]*{_SPEC}"
)
_EXPORT_DECL_RE = re.compile(
    # `export default function f` 导出的是 `default` 而不是 `f`，不计入。`export const f = () =>`
    # 在箭头函数常量建为函数（#1763）之前追不到函数符号，按"无法证明"处理。
    rf"(?m)^[ \t]*export[ \t]+(?!default\b)(?:declare[ \t]+)?(?:abstract[ \t]+)?"
    rf"(?:async[ \t]+)?(?P<kind>function\*?|class|const|let|var)[ \t]+(?P<name>{_IDENT})"
)
_EXPORT_LOCAL_RE = re.compile(
    r"(?m)^[ \t]*export[ \t]+(?!type[ \t\{])\{(?P<names>[^}]*)\}(?![ \t]*from)"
)

#: 再导出链的最大深度（防环、防病态 barrel）。
_MAX_HOPS = 8


def _strip_comments(text: str) -> str:
    return _LINE_COMMENT_RE.sub(r"\1", _BLOCK_COMMENT_RE.sub("", text))


def _items(names: str) -> list[tuple[str, str]]:
    """``{ a, b as c, type T }`` -> ``[(本地/导出名, 原名)]``；类型项跳过。"""
    out: list[tuple[str, str]] = []
    for raw in names.split(","):
        item = raw.strip()
        if not item or item.startswith("type "):
            continue
        original, _, alias = item.partition(" as ")
        original, alias = original.strip(), alias.strip()
        if re.fullmatch(_IDENT, original) and (
            not alias or re.fullmatch(_IDENT, alias)
        ):
            out.append((alias or original, original))
    return out


def import_bindings(source: str) -> dict[str, Any] | None:
    """文件的相对导入绑定：``{"named": {本地: [说明符, 原名]}, "namespace": {本地: 说明符}}``。"""
    text = _strip_comments(source)
    named: dict[str, list[str]] = {}
    namespace: dict[str, str] = {}
    for match in _IMPORT_NAMED_RE.finditer(text):
        for local, original in _items(match.group("names")):
            named[local] = [match.group("spec"), original]
    for match in _IMPORT_NAMESPACE_RE.finditer(text):
        namespace[match.group("local")] = match.group("spec")
    if not named and not namespace:
        return None
    return {
        "named": dict(sorted(named.items())),
        "namespace": dict(sorted(namespace.items())),
    }


def export_shape(source: str) -> dict[str, Any] | None:
    """文件的导出形状：本地声明 / 本地重命名、``export {…} from``、``export *``、``export * as``。"""
    text = _strip_comments(source)
    local: dict[str, str] = {}
    for match in _EXPORT_DECL_RE.finditer(text):
        local[match.group("name")] = match.group("name")
    for match in _EXPORT_LOCAL_RE.finditer(text):
        for exported, original in _items(match.group("names")):
            local[exported] = original
    from_: dict[str, list[str]] = {}
    for match in _EXPORT_FROM_RE.finditer(text):
        for exported, original in _items(match.group("names")):
            from_[exported] = [match.group("spec"), original]
    star = sorted({m.group("spec") for m in _EXPORT_STAR_RE.finditer(text)})
    star_as = {
        m.group("local"): m.group("spec") for m in _EXPORT_STAR_AS_RE.finditer(text)
    }
    if not (local or from_ or star or star_as):
        return None
    return {
        "local": dict(sorted(local.items())),
        "from": dict(sorted(from_.items())),
        "star": star,
        "namespace": dict(sorted(star_as.items())),
    }


@dataclass
class TypeScriptBindings:
    """解析时的只读视图：文件 -> 导入绑定 / 导出形状，以及共享的符号表。"""

    imports: dict[str, dict[str, Any]] = field(default_factory=dict)
    exports: dict[str, dict[str, Any]] = field(default_factory=dict)
    file_symbols: dict[str, list[tuple[str, str, int]]] = field(default_factory=dict)
    file_class_methods: dict[str, dict[str, dict[str, int]]] = field(
        default_factory=dict
    )
    indexed: frozenset[str] = frozenset()

    def _file(self, spec: str, importer: str) -> str:
        return resolve_typescript_specifier(spec, importer, self.indexed)

    def _unique(self, path: str, name: str, kind: str) -> int | None:
        ids = [
            sid
            for n, k, sid in self.file_symbols.get(path, [])
            if n == name and k == kind
        ]
        return ids[0] if len(ids) == 1 else None

    def _export(
        self, path: str, name: str, kind: str, hops: int = 0
    ) -> tuple[int, str] | None:
        """``path`` 导出的 ``name`` 追到的唯一定义 ``(符号 id, 文件)``；不能证明时 None。"""
        if hops > _MAX_HOPS or not path:
            return None
        shape = self.exports.get(path) or {}
        local = (shape.get("local") or {}).get(name)
        if local is not None:
            sid = self._unique(path, local, kind)
            return (sid, path) if sid is not None else None
        forwarded = (shape.get("from") or {}).get(name)
        if forwarded is not None:
            spec, original = forwarded
            return self._export(self._file(spec, path), original, kind, hops + 1)
        found = {
            hit
            for spec in shape.get("star") or []
            if (hit := self._export(self._file(spec, path), name, kind, hops + 1))
            is not None
        }
        return found.pop() if len(found) == 1 else None

    def _namespace_file(self, receiver: str, caller: str) -> str:
        """``ns`` / ``ns.sub`` 指向的文件（命名空间导入，再经 ``export * as``）。"""
        head, *rest = receiver.split(".")
        spec = ((self.imports.get(caller) or {}).get("namespace") or {}).get(head)
        if spec is None:
            return ""
        path = self._file(spec, caller)
        for segment in rest:
            nested = ((self.exports.get(path) or {}).get("namespace") or {}).get(
                segment
            )
            if nested is None:
                return ""
            path = self._file(nested, path)
            if not path:
                return ""
        return path

    def resolve(
        self, receiver: str, simple: str, caller: str
    ) -> tuple[int, str] | None:
        """``f()`` / ``ns.f()`` / ``ns.sub.f()`` / ``Cls.m()``（``Cls`` 为具名导入的类）。"""
        named = (self.imports.get(caller) or {}).get("named") or {}
        if not receiver:
            binding = named.get(simple)
            if binding is None:
                return None
            spec, original = binding
            return self._export(self._file(spec, caller), original, "function")
        if not re.fullmatch(rf"{_IDENT}(?:\.{_IDENT})*", receiver):
            return None
        target = self._namespace_file(receiver, caller)
        if target:
            return self._export(target, simple, "function")
        binding = named.get(receiver)
        if binding is None:
            return None
        spec, original = binding
        cls = self._export(self._file(spec, caller), original, "class")
        if cls is None:
            return None
        _sid, path = cls
        mid = ((self.file_class_methods.get(path) or {}).get(original) or {}).get(
            simple
        )
        return (mid, path) if mid is not None else None


def importers_of(
    imports: dict[str, dict[str, Any]],
    exports: dict[str, dict[str, Any]],
    indexed: frozenset[str],
) -> dict[str, set[str]]:
    """目标文件 -> 经相对导入或再导出依赖它的 TS 文件（范围回填的导入方闭包用）。"""
    out: dict[str, set[str]] = {}

    def add(spec: str, importer: str) -> None:
        target = resolve_typescript_specifier(spec, importer, indexed)
        if target and target != importer:
            out.setdefault(target, set()).add(importer)

    for importer, shape in imports.items():
        for spec, _original in (shape.get("named") or {}).values():
            add(spec, importer)
        for spec in (shape.get("namespace") or {}).values():
            add(spec, importer)
    for importer, shape in exports.items():
        for spec, _original in (shape.get("from") or {}).values():
            add(spec, importer)
        for spec in [
            *(shape.get("star") or []),
            *(shape.get("namespace") or {}).values(),
        ]:
            add(spec, importer)
    return out


__all__ = [
    "TypeScriptBindings",
    "export_shape",
    "import_bindings",
    "importers_of",
]
