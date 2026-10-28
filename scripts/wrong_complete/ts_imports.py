"""TS / JS 的 ES 模块导入绑定（纯文本），供 token 判定器解析跨文件调用。

覆盖 #1764 / #1768 的形态：具名导入、``{ f as g }`` 改名导入、默认导入、
``import * as ns`` 命名空间导入，以及经 ``export { f } from`` / ``export * from``
的再导出链（最多 ``_MAX_HOPS`` 层）。只解析相对说明符；包说明符视为项目外。
"""

from __future__ import annotations

import posixpath
import re

from scripts.wrong_complete.sites import OTHER, POSSIBLE, TARGET, Site, Target
from scripts.wrong_complete.token_text import line_of

_MAX_HOPS = 16
_IMPORT = re.compile(
    r"\bimport\s+(?:type\s+)?(?P<clause>[^;]*?)\s+from\s+(?P<q>[\"'])(?P<spec>[^\"']+)(?P=q)"
)
_REEXPORT = re.compile(
    r"\bexport\s+(?:type\s+)?(?P<clause>\*|\*\s+as\s+[\w$]+|\{[^}]*\})\s*from\s*(?P<q>[\"'])(?P<spec>[^\"']+)(?P=q)"
)
_TS_EXTS = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")


class ImportTable:
    """全部文件的导入绑定：``{path: {local: (spec, imported)}}``。

    ``imported`` 为被导入的名字，默认导入为 ``"default"``，命名空间导入为 ``"*"``。
    """

    def __init__(self, codes: dict[str, str], sources: dict[str, str]) -> None:
        self.codes = codes
        self.sources = sources
        self.bindings: dict[str, dict[str, tuple[str, str]]] = {}
        for path, code in codes.items():
            table: dict[str, tuple[str, str]] = {}
            for match in _IMPORT.finditer(sources[path]):
                if code[match.start()] != "i":
                    continue
                _parse_clause(match.group("clause"), match.group("spec"), table)
            self.bindings[path] = table

    # ------------------------------------------------------------ 解析
    def resolve_spec(self, from_path: str, spec: str) -> str | None:
        """相对说明符 → 项目文件路径（含 ``.js`` → ``.ts`` 与 ``index``）。"""
        if not spec.startswith("."):
            return None
        base = posixpath.normpath(posixpath.join(posixpath.dirname(from_path), spec))
        stem, ext = posixpath.splitext(base)
        candidates = [base]
        candidates += [base + e for e in _TS_EXTS]
        if ext in _TS_EXTS:
            candidates += [stem + e for e in _TS_EXTS]
        candidates += [f"{base}/index{e}" for e in _TS_EXTS]
        for candidate in candidates:
            if candidate in self.sources:
                return candidate
        return None

    def exported_from(
        self, path: str, name: str, target: Target, hops: int = 0
    ) -> bool | None:
        """``path`` 导出的 ``name`` 是否就是目标；``None`` 表示无法判定。"""
        if hops > _MAX_HOPS:
            return None
        if path == target.file:
            return name == target.name or (
                name == "default" and self.is_default(target)
            )
        unknown = False
        for match in _REEXPORT.finditer(self.sources.get(path, "")):
            nxt = self.resolve_spec(path, match.group("spec"))
            clause = match.group("clause")
            mapped = _reexport_name(clause, name)
            if mapped is None:
                continue
            if nxt is None:
                unknown = True
                continue
            found = self.exported_from(nxt, mapped, target, hops + 1)
            if found:
                return True
            unknown = unknown or found is None
        return None if unknown else False

    def is_default(self, target: Target) -> bool:
        """目标是否是其文件的默认导出。"""
        text = self.sources.get(target.file, "")
        name = re.escape(target.name)
        return bool(
            re.search(
                rf"\bexport\s+default\s+(?:async\s+)?(?:function\s*\*?\s*)?{name}\b",
                text,
            )
        )

    # ------------------------------------------------------------ 判定
    def bare_target(
        self, path: str, local: str, target: Target
    ) -> tuple[str, str] | None:
        """裸调用 ``local(`` 的导入判定；``local`` 未被导入时返回 ``None``。"""
        binding = self.bindings.get(path, {}).get(local)
        if binding is None or binding[1] == "*":
            return None
        spec, imported = binding
        resolved = self.resolve_spec(path, spec)
        if resolved is None:
            return OTHER, "package_import"
        found = self.exported_from(resolved, imported, target)
        if found:
            return TARGET, "es_import"
        return (
            (POSSIBLE, "es_import_unknown")
            if found is None
            else (OTHER, "es_import_other")
        )

    def namespace_target(
        self, path: str, head: str, target: Target
    ) -> tuple[str, str] | None:
        """``head.name(`` 且 ``head`` 是命名空间导入时的判定。"""
        binding = self.bindings.get(path, {}).get(head)
        if binding is None or binding[1] != "*":
            return None
        resolved = self.resolve_spec(path, binding[0])
        if resolved is None:
            return OTHER, "package_namespace"
        found = self.exported_from(resolved, target.name, target)
        if found:
            return TARGET, "namespace_import"
        return (
            (POSSIBLE, "namespace_unknown")
            if found is None
            else (OTHER, "namespace_other")
        )

    def alias_calls(self, path: str, target: Target, java: bool) -> list[Site]:
        """经改名绑定（``{ f as g }`` / 默认导入）调用目标的点：``g(``。"""
        if java:
            return []
        code = self.codes[path]
        sites: list[Site] = []
        for local, (_spec, imported) in self.bindings.get(path, {}).items():
            if local == target.name or imported == "*":
                continue
            if imported != target.name and imported != "default":
                continue
            verdict = self.bare_target(path, local, target)
            if verdict is None or verdict[0] == OTHER:
                continue
            call = re.compile(rf"(?<![\w$.]){re.escape(local)}\s*\(")
            for match in call.finditer(code):
                line = line_of(code, match.start())
                sites.append(
                    Site(path, line, "call", verdict[0], f"alias:{verdict[1]}", "")
                )
        return sites


def _parse_clause(clause: str, spec: str, table: dict[str, tuple[str, str]]) -> None:
    """解析 ``import <clause> from spec`` 的子句。"""
    clause = clause.strip()
    named = re.search(r"\{([^}]*)\}", clause)
    if named:
        for part in named.group(1).split(","):
            part = part.strip().removeprefix("type ").strip()
            if not part:
                continue
            pieces = re.split(r"\s+as\s+", part)
            table[pieces[-1].strip()] = (spec, pieces[0].strip())
        clause = (clause[: named.start()] + clause[named.end() :]).strip(" ,")
    namespace = re.search(r"\*\s+as\s+([\w$]+)", clause)
    if namespace:
        table[namespace.group(1)] = (spec, "*")
        clause = (clause[: namespace.start()] + clause[namespace.end() :]).strip(" ,")
    if re.fullmatch(r"[\w$]+", clause or ""):
        table[clause] = (spec, "default")


def _reexport_name(clause: str, name: str) -> str | None:
    """再导出子句把对外的 ``name`` 映射到源模块里的哪个名字；不涉及则 ``None``。"""
    if clause == "*":
        return None if name == "default" else name
    if clause.startswith("*"):
        return None
    for part in clause.strip("{} ").split(","):
        pieces = re.split(r"\s+as\s+", part.strip())
        if pieces and pieces[-1].strip() == name:
            return pieces[0].strip()
    return None
