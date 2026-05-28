#!/usr/bin/env python3
"""
Symbol Definition Resolver — Go-to-definition and find-all-references.

Uses the pre-indexed AST cache (SQLite + FTS5 + symbol_rows + call_edges)
to resolve symbol names to their definition locations and find all
references across the project. CodeGraph parity for go-to-def navigation.

Key capabilities:
- resolve_definition: Find where a symbol is defined (go-to-definition)
- find_references: Find all usage sites of a symbol across the project
- Qualified name resolution: Handle module.Class.method dotted paths
- Import-aware: Track symbols through import chains
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from .codegraph_query_backend import CodeGraphQueryBackend

logger = logging.getLogger(__name__)

_DEFINITION_KINDS = frozenset({"function", "class", "method", "variable"})

_REFERENCE_KINDS = frozenset({"function", "class", "method", "variable"})


@dataclass
class DefinitionLocation:
    file: str
    name: str
    kind: str
    line: int
    end_line: int
    language: str
    confidence: float = 1.0
    context: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "file": self.file,
            "name": self.name,
            "kind": self.kind,
            "line": self.line,
            "end_line": self.end_line,
            "language": self.language,
            "confidence": round(self.confidence, 2),
        }
        if self.context:
            d["context"] = self.context
        return d


@dataclass
class ReferenceLocation:
    file: str
    name: str
    kind: str
    line: int
    end_line: int
    language: str
    reference_type: str = "usage"

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "name": self.name,
            "kind": self.kind,
            "line": self.line,
            "end_line": self.end_line,
            "language": self.language,
            "reference_type": self.reference_type,
        }


@dataclass
class ResolveResult:
    symbol: str
    definitions: list[DefinitionLocation] = field(default_factory=list)
    references: list[ReferenceLocation] = field(default_factory=list)
    resolved_via: str = "cache"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "definition_count": len(self.definitions),
            "reference_count": len(self.references),
            "definitions": [d.to_dict() for d in self.definitions],
            "references": [r.to_dict() for r in self.references],
            "resolved_via": self.resolved_via,
        }


def _parse_qualified_name(symbol: str) -> tuple[list[str], str]:
    parts = symbol.split(".")
    return parts, parts[-1]


def _build_import_map(cache: Any) -> dict[str, list[Any]]:
    """Import entries may be `str` (module path) or `dict` (qualified import).

    Caller code branches on `isinstance(imp, str)` to handle both shapes.
    """
    conn = cache._get_conn()
    rows = conn.execute(
        "SELECT file_path, imports_json, language FROM ast_index"
    ).fetchall()
    import_map: dict[str, list[Any]] = {}
    for row in rows:
        imports = json.loads(row["imports_json"])
        if imports:
            import_map[row["file_path"]] = imports
    return import_map


def _build_module_to_file_map(cache: Any) -> dict[str, str]:
    conn = cache._get_conn()
    rows = conn.execute("SELECT file_path, language FROM ast_index").fetchall()
    module_map: dict[str, str] = {}
    for row in rows:
        fp = row["file_path"]
        parts = fp.replace(os.sep, "/")
        if parts.endswith(".py"):
            parts = parts[:-3]
        elif parts.endswith(".js"):
            parts = parts[:-3]
        elif parts.endswith(".ts"):
            parts = parts[:-3]
        elif parts.endswith(".java"):
            parts = parts[:-5]
        elif parts.endswith(".go"):
            parts = parts[:-3]
        else:
            continue
        module_name = parts.replace("/", ".")
        module_map[module_name] = fp
        short_name = parts.rsplit("/", 1)[-1] if "/" in parts else parts
        if short_name not in module_map:
            module_map[short_name] = fp
    return module_map


def _definition_location(item: dict[str, Any]) -> DefinitionLocation:
    return DefinitionLocation(
        file=str(item.get("file", "")),
        name=str(item.get("name", "")),
        kind=str(item.get("kind", "")),
        line=int(item.get("line", 0) or 0),
        end_line=int(item.get("end_line", 0) or 0),
        language=str(item.get("language", "")),
        confidence=float(item.get("confidence", 1.0) or 1.0),
        context=str(item.get("context", "")),
    )


class SymbolResolver:
    """Resolve symbol definitions and find references using the AST cache.

    Core engine for CodeGraph go-to-definition and find-all-references.
    Leverages the pre-indexed AST cache for instant lookups without
    re-parsing any source files.
    """

    def __init__(self, cache: Any) -> None:
        self._cache = cache
        self._definition_backend = CodeGraphQueryBackend(cache)
        self._import_map: dict[str, list[Any]] | None = None
        self._module_to_file: dict[str, str] | None = None

    def resolve(self, symbol: str) -> ResolveResult:
        parts, short_name = _parse_qualified_name(symbol)
        result = ResolveResult(symbol=symbol)
        result.definitions = self._find_definitions(parts, short_name)
        return result

    def find_references(self, symbol: str) -> ResolveResult:
        parts, short_name = _parse_qualified_name(symbol)
        result = ResolveResult(symbol=symbol)
        result.definitions = self._find_definitions(parts, short_name)
        result.references = self._find_references(symbol, short_name)
        return result

    def _find_definitions(
        self, parts: list[str], short_name: str
    ) -> list[DefinitionLocation]:
        definitions: list[DefinitionLocation] = []
        if len(parts) > 1:
            definitions = self._resolve_qualified(parts, short_name)
        if not definitions:
            definitions = self._resolve_simple(short_name)
        if not definitions:
            definitions = self._resolve_from_imports(short_name)
        return definitions

    def _resolve_simple(self, name: str) -> list[DefinitionLocation]:
        return [
            _definition_location(item)
            for item in self._definition_backend.resolve_definitions(name)
        ]

    def _resolve_qualified(
        self, parts: list[str], short_name: str
    ) -> list[DefinitionLocation]:
        candidates = self._resolve_simple(short_name)
        if len(parts) < 2 or not candidates:
            return candidates
        parent_name = parts[-2]
        filtered: list[DefinitionLocation] = []
        for c in candidates:
            if self._is_child_of(c, parent_name):
                c.confidence = 1.0
                filtered.append(c)
        if not filtered:
            for c in candidates:
                file_parts = c.file.replace(os.sep, "/").split("/")
                if parent_name in file_parts:
                    c.confidence = 0.7
                    filtered.append(c)
        return filtered if filtered else candidates

    def _is_child_of(self, location: DefinitionLocation, parent_name: str) -> bool:
        conn = self._cache._get_conn()
        row = conn.execute(
            "SELECT symbols_json FROM ast_index WHERE file_path = ?",
            (location.file,),
        ).fetchone()
        if row is None:
            return False
        symbols = json.loads(row["symbols_json"])
        for sym in symbols.get("symbols", []):
            if (
                sym.get("name") == location.name
                and sym.get("kind") in _DEFINITION_KINDS
            ):
                for child in sym.get("children", []):
                    if child.get("name") == parent_name:
                        return True
                if sym.get("parent") == parent_name:
                    return True
        row2 = conn.execute(
            """SELECT r2.name, r2.kind, r2.line, r2.end_line
               FROM ast_symbol_rows r1
               JOIN ast_symbol_rows r2 ON r1.file_path = r2.file_path
               WHERE r1.name = ? AND r1.file_path = ?
                 AND r2.name = ? AND r2.kind = 'class'
                 AND r2.line <= r1.line AND r2.end_line >= r1.line""",
            (location.name, location.file, parent_name),
        ).fetchone()
        return row2 is not None

    def _resolve_from_imports(self, name: str) -> list[DefinitionLocation]:
        if self._import_map is None:
            self._import_map = _build_import_map(self._cache)
        if self._module_to_file is None:
            self._module_to_file = _build_module_to_file_map(self._cache)
        for _file_path, imports in self._import_map.items():
            for imp in imports:
                if isinstance(imp, str):
                    if imp.split(".")[-1] == name:
                        module_name = imp
                        if module_name in self._module_to_file:
                            source_file = self._module_to_file[module_name]
                            defs = self._find_defs_in_file(source_file, name)
                            if defs:
                                for d in defs:
                                    d.confidence = 0.8
                                return defs
                    continue
                imported_names = imp.get("names", [])
                if isinstance(imported_names, list):
                    for iname in imported_names:
                        if isinstance(iname, str) and iname.split(".")[-1] == name:
                            source_module = imp.get("module", "")
                            if source_module and source_module in self._module_to_file:
                                source_file = self._module_to_file[source_module]
                                defs = self._find_defs_in_file(source_file, name)
                                if defs:
                                    for d in defs:
                                        d.confidence = 0.8
                                    return defs
                elif (
                    isinstance(imported_names, str)
                    and imported_names.split(".")[-1] == name
                ):
                    source_module = imp.get("module", "")
                    if source_module and source_module in self._module_to_file:
                        source_file = self._module_to_file[source_module]
                        defs = self._find_defs_in_file(source_file, name)
                        if defs:
                            for d in defs:
                                d.confidence = 0.8
                            return defs
        return []

    def _find_defs_in_file(self, file_path: str, name: str) -> list[DefinitionLocation]:
        conn = self._cache._get_conn()
        rows = conn.execute(
            """SELECT name, kind, file_path, language, line, end_line
               FROM ast_symbol_rows
               WHERE file_path = ? AND name = ? AND kind IN ('function', 'class', 'method')
               ORDER BY line""",
            (file_path, name),
        ).fetchall()
        results: list[DefinitionLocation] = []
        for row in rows:
            results.append(
                DefinitionLocation(
                    file=row["file_path"],
                    name=row["name"],
                    kind=row["kind"],
                    line=row["line"],
                    end_line=row["end_line"],
                    language=row["language"],
                )
            )
        if not results:
            row = conn.execute(
                "SELECT symbols_json, language FROM ast_index WHERE file_path = ?",
                (file_path,),
            ).fetchone()
            if row:
                symbols = json.loads(row["symbols_json"])
                for sym in symbols.get("symbols", []):
                    if sym.get("name") == name and sym.get("kind") in _DEFINITION_KINDS:
                        results.append(
                            DefinitionLocation(
                                file=file_path,
                                name=name,
                                kind=sym["kind"],
                                line=sym.get("line", 0),
                                end_line=sym.get("end_line", 0),
                                language=row["language"],
                                confidence=0.9,
                            )
                        )
        return results

    def _find_references(self, symbol: str, short_name: str) -> list[ReferenceLocation]:
        references: list[ReferenceLocation] = []
        seen: set[tuple[str, int]] = set()
        conn = self._cache._get_conn()
        try:
            rows = conn.execute(
                """SELECT callee_name, callee_full, caller_name, caller_file,
                          caller_line, file_path, language
                   FROM ast_call_edges
                   WHERE callee_name = ?""",
                (short_name,),
            ).fetchall()
            for row in rows:
                key = (row["caller_file"], row["caller_line"])
                if key not in seen:
                    seen.add(key)
                    references.append(
                        ReferenceLocation(
                            file=row["caller_file"],
                            name=row["caller_name"],
                            kind="function",
                            line=row["caller_line"],
                            end_line=row["caller_line"],
                            language=row["language"],
                            reference_type="call_site",
                        )
                    )
        except sqlite3.OperationalError:
            pass
        import_refs = self._find_import_references(short_name)
        for ref in import_refs:
            key = (ref.file, ref.line)
            if key not in seen:
                seen.add(key)
                references.append(ref)
        return references

    def _find_import_references(self, name: str) -> list[ReferenceLocation]:
        if self._import_map is None:
            self._import_map = _build_import_map(self._cache)
        refs: list[ReferenceLocation] = []
        for file_path, imports in self._import_map.items():
            for imp in imports:
                if isinstance(imp, str):
                    if imp.split(".")[-1] == name:
                        refs.append(
                            ReferenceLocation(
                                file=file_path,
                                name=name,
                                kind="import",
                                line=0,
                                end_line=0,
                                language="",
                                reference_type="import",
                            )
                        )
                    continue
                imported_names = imp.get("names", [])
                if isinstance(imported_names, list):
                    for iname in imported_names:
                        if isinstance(iname, str) and iname.split(".")[-1] == name:
                            refs.append(
                                ReferenceLocation(
                                    file=file_path,
                                    name=name,
                                    kind="import",
                                    line=imp.get("line", 0),
                                    end_line=imp.get("line", 0),
                                    language="",
                                    reference_type="import",
                                )
                            )
        return refs
