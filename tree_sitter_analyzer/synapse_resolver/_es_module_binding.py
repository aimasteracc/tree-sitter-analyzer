"""#1764：TS / JS 调用经 ES 模块导入绑定到另一个项目文件里的定义。

ts1 dogfood（hono、zod）里没有一条 TypeScript 调用边被持久化为 ``project``：导入
本身解析到了正确的文件，调用却全部停在 ``unknown``。这里按 ES 模块语义绑定：

* ``import { f } from './m'; f()`` 与 ``import { g as f } …; f()``（改名导入记下
  ``import_alias``，按真实名字查询时能看到这条边）；
* ``import f from './m'; f()``——默认导出是名为 ``f`` 的函数；
* ``import * as ns from './m'; ns.f()``，以及沿命名空间再导出走下去的
  ``z.core.flattenError()``；
* 目标模块是桶文件时沿 ``export { f } from``、``export * from``、``export * as ns from``
  找到真正的定义。

只绑定能证明的目标：

* 多个 ``export *`` 来源时，必须能证明其余来源都不导出这个名字（每个来源的导出表都
  完整可读）；两个来源给出不同定义时，按 ES 语义该名字不被导出，不绑定；
* 调用点用的名字须与定义的名字相同——改名只允许发生在调用文件自己的导入行上
  （``import { g as f }``，查询 ``g`` 时经 ``import_alias`` 找到这条边）。经再导出
  改了名（``export { g as f } from``）的调用不绑定，因为按 ``g`` 查询看不到它；
* 调用文件给接收者的成员赋值（``ns.f = fake``）或以同名变量遮蔽导入时不绑定。

其余一律返回 ``None``，交回原有的保守级联（``unknown``）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ._es_export_table import ExportTable, parse_export_table
from ._package_specifiers import PackageSpecifiers
from ._typescript_imports import resolve_typescript_specifier

if TYPE_CHECKING:
    from ._imports import ImportEntry
    from ._javascript_object_exports import ObjectExportResolver

#: 沿导入 / 再导出追踪的最大深度（zod 的测试到定义要经过 5 个桶文件）。
MAX_DEPTH = 16
_IDENT_RE = re.compile(r"^[A-Za-z_$][\w$]*$")
#: 调用可以指向的定义种类（``new T()`` 的被调方是类）；变量另从 ``variables`` 取。
_DEFINITION_KINDS = frozenset({"function", "class"})


@dataclass(frozen=True)
class Definition:
    symbol_id: int
    file: str
    name: str


@dataclass(frozen=True)
class Namespace:
    file: str


#: 名字确定不被导出。
ABSENT = "absent"
#: 无法判定（读不到源码、导出表不完整、来源有歧义、深度超限……）。
UNKNOWN = "unknown"

Found = Definition | Namespace | str


@dataclass(frozen=True)
class _Binding:
    kind: str  # "namespace" | "named" | "default"
    target: str
    imported: str
    line: int


class EsModuleBinder:
    """一次索引构建内共享：按文件记忆导出表与查找结果。"""

    def __init__(
        self,
        *,
        project_root: str | None,
        imports_by_file: dict[str, list[ImportEntry]],
        indexed_files: frozenset[str],
        file_symbols: dict[str, list[tuple[str, str, int]]],
        variables: dict[str, dict[str, list[tuple[int, int]]]],
        object_exports: ObjectExportResolver,
        class_methods: dict[str, dict[str, dict[str, int]]] | None = None,
    ) -> None:
        self._root = project_root
        #: 文件 -> 类 -> 方法 -> 符号 id（导入的类上的静态调用）。
        self._class_methods = class_methods or {}
        self._imports = imports_by_file
        self._indexed = indexed_files
        self._symbols = file_symbols
        self._variables = variables
        self._objects = object_exports
        self._packages = PackageSpecifiers(project_root, indexed_files)
        self._tables: dict[str, ExportTable | None] = {}
        self._found: dict[tuple[str, str], Found] = {}
        self._active: set[tuple[str, str]] = set()
        #: 遇到 ``export *`` 环的次数；环内算出的中间结果不记忆（只对环的入口成立）。
        self._cycles = 0
        self._bindings: dict[tuple[str, str], _Binding | None] = {}
        #: ``(文件, 接收者)`` -> 被赋值的成员名；读不到源码为 None。
        self._assignments: dict[tuple[str, str], frozenset[str] | None] = {}

    # ------------------------------------------------------------------ public
    def bind(
        self, receiver: str, simple: str, caller_file: str
    ) -> tuple[int, str, dict[str, Any] | None] | None:
        """``(符号 id, 定义文件, import_alias 来源)``；无法证明时为 None。"""
        if not self._root or not _IDENT_RE.match(simple):
            return None
        if not receiver:
            return self._bind_bare(simple, caller_file)
        segments = receiver.split(".")
        if not all(_IDENT_RE.match(s) for s in segments) or segments[0] in (
            "this",
            "super",
        ):
            return None
        return self._bind_member(segments, simple, caller_file)

    def module_file(self, specifier: str, from_file: str) -> str:
        """说明符指向的已索引项目文件（相对路径或项目自己的包）；否则 ``""``。"""
        return resolve_typescript_specifier(
            specifier, from_file, self._indexed
        ) or self._packages.resolve(specifier)

    # ----------------------------------------------------------------- binding
    def _bind_bare(
        self, simple: str, caller_file: str
    ) -> tuple[int, str, dict[str, Any] | None] | None:
        binding = self._binding(caller_file, simple)
        if (
            binding is None
            or binding.kind == "namespace"
            or self._shadowed(caller_file, simple)
        ):
            return None
        found = self.find(binding.target, binding.imported, 0)
        if not isinstance(found, Definition):
            return None
        if found.name == simple:
            return found.symbol_id, found.file, None
        # 改名导入（``import { g as f }``）、改名的默认导入（#1768：``import makeSig
        # from './jws'`` 而默认导出是 ``signer``）与再导出链上的改名：调用点的名字不是
        # 目标的名字，记下来源，按 ``signer`` 查询时经 ``import_alias`` 找到这条边。
        alias = {"local": simple, "name": found.name, "line": binding.line}
        return found.symbol_id, found.file, alias

    def _bind_member(
        self, segments: list[str], simple: str, caller_file: str
    ) -> tuple[int, str, dict[str, Any] | None] | None:
        head = segments[0]
        binding = self._binding(caller_file, head)
        if binding is None or self._shadowed(caller_file, head):
            return None
        if self._assigned(caller_file, ".".join(segments), simple):
            return None
        current: Found = (
            Namespace(binding.target)
            if binding.kind == "namespace"
            else self.find(binding.target, binding.imported, 0)
        )
        for segment in segments[1:]:
            if not isinstance(current, Namespace):
                current = UNKNOWN
                break
            current = self.find(current.file, segment, 0)
        if isinstance(current, Namespace):
            found = self.find(current.file, simple, 0)
            if isinstance(found, Definition) and found.name == simple:
                return found.symbol_id, found.file, None
            return None
        if isinstance(current, Definition):
            # ``Status.merge()`` 上导入的类：类自己定义的方法（继承来的不在这里）。
            methods = self._class_methods.get(current.file, {}).get(current.name, {})
            method = methods.get(simple)
            if method is not None:
                return method, current.file, None
        # 默认导出对象的成员（#1741 的 ``utils.findKey()``，``export default utils``
        # 指向 ``const utils = { … }`` 时上面得到的是变量），JS 与 TS 同形。
        bound = self._objects.resolve(".".join(segments), simple, caller_file)
        return (bound[0], bound[1], None) if bound is not None else None

    def _binding(self, file_path: str, local: str) -> _Binding | None:
        """``local`` 在 ``file_path`` 中唯一的导入绑定，且模块落在项目文件上。"""
        key = (file_path, local)
        if key not in self._bindings:
            self._bindings[key] = self._read_binding(file_path, local)
        return self._bindings[key]

    def _read_binding(self, file_path: str, local: str) -> _Binding | None:
        entries = [e for e in self._imports.get(file_path, []) if e.local_name == local]
        if len(entries) != 1:
            return None
        entry = entries[0]
        target = self.module_file(entry.module_path, file_path)
        if not target:
            return None
        if entry.is_star:
            return _Binding("namespace", target, "*", entry.line)
        if entry.alias_of:
            return _Binding("named", target, entry.alias_of, entry.line)
        if self._objects.is_default_clause(file_path, local):
            return _Binding("default", target, "default", entry.line)
        return _Binding("named", target, local, entry.line)

    # ----------------------------------------------------------------- exports
    def find(self, file_path: str, name: str, depth: int) -> Found:
        """``file_path`` 导出的 ``name`` 是什么。"""
        key = (file_path, name)
        if key in self._found:
            return self._found[key]
        if key in self._active:
            self._cycles += 1
            return ABSENT  # ``export *`` 环：这一支不提供新的名字。
        if depth > MAX_DEPTH:
            return UNKNOWN
        cycles = self._cycles
        self._active.add(key)
        try:
            result = self._find(file_path, name, depth)
        finally:
            self._active.discard(key)
        if self._cycles == cycles or not self._active:
            self._found[key] = result
        return result

    def _find(self, file_path: str, name: str, depth: int) -> Found:
        table = self._table(file_path)
        if table is None:
            return UNKNOWN
        if name in table.local:
            return self._local(file_path, table.local[name], depth)
        if name in table.reexports:
            spec, imported = table.reexports[name]
            target = self.module_file(spec, file_path)
            if not target:
                return UNKNOWN
            if imported == "*":
                return Namespace(target)
            return self.find(target, imported, depth + 1)
        if not table.complete:
            return UNKNOWN
        if name == "default":
            return ABSENT  # ``export *`` 不转出默认导出。
        hits: set[Definition | Namespace] = set()
        for spec in table.stars:
            target = self.module_file(spec, file_path)
            if not target:
                return UNKNOWN  # 外部包的 ``export *``：可能就含这个名字。
            found = self.find(target, name, depth + 1)
            if found == UNKNOWN:
                return UNKNOWN
            if found != ABSENT:
                hits.add(found)  # type: ignore[arg-type]
        if not hits:
            return ABSENT
        return hits.pop() if len(hits) == 1 else UNKNOWN

    def _local(self, file_path: str, ident: str, depth: int) -> Found:
        """``file_path`` 里名为 ``ident`` 的模块级绑定：导入、函数 / 类、变量。

        导入先于定义：模块级只能有一个 ``ident``，同名的定义只可能是嵌套作用域里的。
        """
        if not ident:
            return UNKNOWN
        binding = self._binding(file_path, ident)
        if binding is not None:
            if binding.kind == "namespace":
                return Namespace(binding.target)
            return self.find(binding.target, binding.imported, depth + 1)
        if any(e.local_name == ident for e in self._imports.get(file_path, [])):
            return UNKNOWN  # 导入了这个名字，但来源不在项目里或不唯一。
        ids = [
            sid
            for n, kind, sid in self._symbols.get(file_path, [])
            if n == ident and kind in _DEFINITION_KINDS
        ]
        ids += [sid for sid, _line in self._variables.get(file_path, {}).get(ident, [])]
        if ids:
            return Definition(min(ids), file_path, ident)
        return UNKNOWN

    def _table(self, file_path: str) -> ExportTable | None:
        if file_path not in self._tables:
            text = self._objects.source(file_path)
            self._tables[file_path] = (
                parse_export_table(text) if text is not None else None
            )
        return self._tables[file_path]

    # ------------------------------------------------------------------ guards
    def _shadowed(self, file_path: str, name: str) -> bool:
        """调用文件以同名变量遮蔽了导入（``const z = …``）。"""
        return bool(self._variables.get(file_path, {}).get(name))

    def _assigned(self, file_path: str, receiver: str, name: str) -> bool:
        """调用文件给 ``receiver.name`` 赋值；读不到源码按“已赋值”处理。"""
        key = (file_path, receiver)
        if key not in self._assignments:
            text = self._objects.source(file_path)
            if text is None:
                self._assignments[key] = None
            else:
                dotted = r"[ \t]*\.[ \t]*".join(
                    re.escape(p) for p in receiver.split(".")
                )
                pattern = (
                    rf"(?<![\w$.]){dotted}[ \t]*\.[ \t]*([A-Za-z_$][\w$]*)[ \t]*=(?!=)"
                )
                self._assignments[key] = frozenset(re.findall(pattern, text))
        assigned = self._assignments[key]
        return assigned is None or name in assigned


__all__ = [
    "ABSENT",
    "MAX_DEPTH",
    "UNKNOWN",
    "Definition",
    "EsModuleBinder",
    "Namespace",
]
