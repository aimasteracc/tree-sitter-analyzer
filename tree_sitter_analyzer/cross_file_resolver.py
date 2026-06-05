#!/usr/bin/env python3
"""
Cross-File Symbol Resolution — Import-aware call edge resolution.

Builds structured import-to-definition mappings from the pre-indexed AST cache
to resolve bare function names in call edges to their actual definition files.

Solves the core CodeGraph gap: callers/callees tools currently show empty
caller names when the enclosing function detection fails, and cross-file
callees are resolved to the wrong file because import chains are not followed.

Key class:
- CrossFileResolver: Structured import parsing + cross-file symbol resolution
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .callee_resolution import CalleeResolver

logger = logging.getLogger(__name__)

_PY_FROM_IMPORT_RE = re.compile(r"^from\s+([\w.]+)\s+import\s+(.+)$", re.MULTILINE)
_PY_IMPORT_RE = re.compile(r"^import\s+([\w.]+)", re.MULTILINE)
_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+.*?from\s+['"](.+?)['"]|require\s*\(\s*['"](.+?)['"]\s*\))""",
    re.MULTILINE,
)
_JAVA_IMPORT_RE = re.compile(r"^import\s+([\w.]+);", re.MULTILINE)
_GO_IMPORT_RE = re.compile(r'"([^"]+)"', re.MULTILINE)


def _alias_name(s: str) -> str:
    """Extract the local alias from 'name as alias', or return the stripped name."""
    return s.strip().split(" as ")[-1].strip()


@dataclass
class ImportEntry:
    source_file: str
    module_path: str
    imported_names: list[str]
    is_relative: bool = False
    language: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "module_path": self.module_path,
            "imported_names": self.imported_names,
            "is_relative": self.is_relative,
            "language": self.language,
        }


@dataclass
class FunctionDef:
    name: str
    file: str
    line: int
    end_line: int
    language: str
    parent_class: str | None = None

    @property
    def key(self) -> str:
        return f"{self.file}:{self.name}:{self.line}"


@dataclass
class ResolvedEdge:
    caller_name: str
    caller_file: str
    caller_line: int
    callee_name: str
    callee_file: str
    callee_line: int
    callee_resolved_file: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "caller_name": self.caller_name,
            "caller_file": self.caller_file,
            "caller_line": self.caller_line,
            "callee_name": self.callee_name,
            "callee_file": self.callee_file,
            "callee_line": self.callee_line,
            "confidence": round(self.confidence, 2),
        }
        if self.callee_resolved_file:
            d["callee_resolved_file"] = self.callee_resolved_file
        return d


class CrossFileResolver:
    """Resolve cross-file symbol references using indexed AST cache data.

    Three-phase resolution:
    1. Build module-to-file map from indexed file paths
    2. Parse structured imports from import text strings
    3. Resolve callee names to definition files using import chains
    """

    def __init__(self, cache: Any) -> None:
        self._cache = cache
        self._module_to_file: dict[str, str] = {}
        self._functions_by_name: dict[str, list[FunctionDef]] = {}
        self._functions_by_file: dict[str, list[FunctionDef]] = {}
        self._imports_by_file: dict[str, list[ImportEntry]] = {}
        self._name_to_source: dict[str, dict[str, str]] = {}
        self._callee_resolver: CalleeResolver | None = None
        self._built = False

    def build(self) -> None:
        if self._built:
            return
        self._build_module_map()
        self._build_function_index()
        self._build_import_index()
        self._build_name_resolution_map()
        self._callee_resolver = CalleeResolver(
            functions_by_name=self._functions_by_name,
            functions_by_file=self._functions_by_file,
            name_to_source=self._name_to_source,
        )
        self._built = True

    def resolve_callee(
        self,
        callee_name: str,
        source_file: str,
    ) -> list[tuple[str, float]]:
        """Resolve a callee name to likely definition files.

        Returns list of (file_path, confidence) tuples sorted by confidence.
        """
        self.build()
        if self._callee_resolver is None:
            return []
        return self._callee_resolver.resolve_files(
            callee_name,
            source_file,
            include_unmatched_import=True,
        )

    def find_caller_function(
        self,
        call_line: int,
        source_file: str,
    ) -> tuple[str, int]:
        """Find the enclosing function for a call at the given line.

        Returns (function_name, function_start_line) or ("", 0).
        """
        self.build()
        funcs = self._functions_by_file.get(source_file, [])
        best: FunctionDef | None = None
        for func in funcs:
            if func.line <= call_line <= func.end_line:
                if best is None or (func.end_line - func.line) < (
                    best.end_line - best.line
                ):
                    best = func
        if best is not None:
            return best.name, best.line
        for func in funcs:
            if func.line <= call_line:
                if best is None or func.line > best.line:
                    best = func
        if best is not None:
            return best.name, best.line
        return "", 0

    def resolve_call_edges(self) -> list[ResolvedEdge]:
        """Re-resolve all call edges with improved cross-file resolution."""
        self.build()
        raw_edges = self._cache.get_call_edges()
        resolved: list[ResolvedEdge] = []
        for edge in raw_edges:
            caller_file = edge["caller_file"]
            caller_name = edge["caller_name"]
            caller_line = edge["caller_line"]
            callee_name = edge["callee_name"]
            callee_line = edge.get("callee_line", 0)

            if not caller_name:
                caller_name, caller_line = self.find_caller_function(
                    edge.get("callee_line", 0) or caller_line, caller_file
                )
                if not caller_name:
                    cn, cl = self.find_caller_function(callee_line, caller_file)
                    if cn:
                        caller_name = cn
                        caller_line = cl

            callee_candidates = self.resolve_callee(callee_name, caller_file)
            callee_resolved = callee_candidates[0][0] if callee_candidates else ""

            confidence = 1.0
            if callee_candidates:
                confidence = callee_candidates[0][1]
            if not caller_name:
                confidence *= 0.5

            resolved.append(
                ResolvedEdge(
                    caller_name=caller_name,
                    caller_file=caller_file,
                    caller_line=caller_line,
                    callee_name=callee_name,
                    callee_file=edge.get("file_path", ""),
                    callee_line=callee_line,
                    callee_resolved_file=callee_resolved,
                    confidence=confidence,
                )
            )
        return resolved

    def _build_module_map(self) -> None:
        conn = self._cache.get_conn()
        rows = conn.execute("SELECT file_path, language FROM ast_index").fetchall()
        for row in rows:
            fp = row["file_path"]
            lang = row["language"]
            self._register_module_path(fp, lang)

    def _register_module_path(self, fp: str, language: str) -> None:
        parts = fp.replace(os.sep, "/")
        if language == "python":
            if parts.endswith("/__init__.py"):
                mod = parts.removesuffix("/__init__.py").replace("/", ".")
                self._module_to_file[mod] = fp
            elif parts.endswith(".py"):
                mod = parts[:-3].replace("/", ".")
                self._module_to_file[mod] = fp
                short = parts.rsplit("/", 1)[-1][:-3]
                if short not in self._module_to_file:
                    self._module_to_file[short] = fp
        elif language in ("javascript", "typescript"):
            for ext in (".js", ".jsx", ".ts", ".tsx"):
                if parts.endswith(ext):
                    ext_len = len(ext)
                    mod = parts[:-ext_len].replace("/", ".")
                    self._module_to_file[mod] = fp
                    short = parts.rsplit("/", 1)[-1][:-ext_len]
                    if short not in self._module_to_file:
                        self._module_to_file[short] = fp
                    break
        elif language == "java":
            if parts.endswith(".java"):
                short = parts.rsplit("/", 1)[-1][:-5]
                if short not in self._module_to_file:
                    self._module_to_file[short] = fp
        elif language == "go":
            if parts.endswith(".go"):
                short = parts.rsplit("/", 1)[-1][:-3]
                if short not in self._module_to_file:
                    self._module_to_file[short] = fp

    def _build_function_index(self) -> None:
        conn = self._cache.get_conn()
        rows = conn.execute(
            "SELECT file_path, symbols_json, language FROM ast_index"
        ).fetchall()
        for row in rows:
            fp = row["file_path"]
            lang = row["language"]
            symbols = json.loads(row["symbols_json"])
            for sym in symbols.get("symbols", []):
                if sym.get("kind") not in ("function", "method"):
                    continue
                func = FunctionDef(
                    name=sym["name"],
                    file=fp,
                    line=sym.get("line", 0),
                    end_line=sym.get("end_line", sym.get("line", 0)),
                    language=lang,
                    parent_class=sym.get("class"),
                )
                self._functions_by_name.setdefault(func.name, []).append(func)
                self._functions_by_file.setdefault(fp, []).append(func)

    def _build_import_index(self) -> None:
        conn = self._cache.get_conn()
        rows = conn.execute(
            "SELECT file_path, imports_json, language FROM ast_index"
        ).fetchall()
        for row in rows:
            fp = row["file_path"]
            lang = row["language"]
            imports_raw: list[str] = json.loads(row["imports_json"])
            entries: list[ImportEntry] = []
            for imp_text in imports_raw:
                parsed = self._parse_import(imp_text, fp, lang)
                if parsed:
                    entries.append(parsed)
            if entries:
                self._imports_by_file[fp] = entries

    def _parse_import(
        self, text: str, source_file: str, language: str
    ) -> ImportEntry | None:
        text = text.strip()
        if not text:
            return None
        if language == "python":
            return self._parse_python_import(text, source_file, language)
        elif language in ("javascript", "typescript"):
            return self._parse_js_import(text, source_file, language)
        elif language == "java":
            return self._parse_java_import(text, source_file, language)
        return None

    def _parse_python_import(
        self, text: str, source_file: str, language: str
    ) -> ImportEntry | None:
        m = _PY_FROM_IMPORT_RE.match(text)
        if m:
            module = m.group(1)
            names_str = m.group(2)
            names = [n.strip().split(" as ")[0].strip() for n in names_str.split(",")]
            names = [n for n in names if n and n != "*"]
            return ImportEntry(
                source_file=source_file,
                module_path=module,
                imported_names=names,
                is_relative=module.startswith("."),
                language=language,
            )
        m = _PY_IMPORT_RE.match(text)
        if m:
            module = m.group(1)
            short = module.split(".")[-1]
            return ImportEntry(
                source_file=source_file,
                module_path=module,
                imported_names=[short],
                is_relative=False,
                language=language,
            )
        return None

    def _parse_js_import(
        self, text: str, source_file: str, language: str
    ) -> ImportEntry | None:
        m = _JS_IMPORT_RE.search(text)
        if m:
            module = m.group(1) or m.group(2) or ""
            if not module:
                return None
            names: list[str] = []
            import_match = re.match(r"import\s+(?:\{([^}]+)\}|(\w+))", text)
            if import_match:
                if import_match.group(1):
                    names = [_alias_name(n) for n in import_match.group(1).split(",")]
                elif import_match.group(2):
                    names = [import_match.group(2)]
            if module.startswith("."):
                return ImportEntry(
                    source_file=source_file,
                    module_path=module,
                    imported_names=names,
                    is_relative=True,
                    language=language,
                )
            return ImportEntry(
                source_file=source_file,
                module_path=module,
                imported_names=names,
                is_relative=False,
                language=language,
            )
        return None

    def _parse_java_import(
        self, text: str, source_file: str, language: str
    ) -> ImportEntry | None:
        m = _JAVA_IMPORT_RE.match(text)
        if m:
            fqn = m.group(1)
            short = fqn.split(".")[-1]
            is_star = short == "*"
            names = [] if is_star else [short]
            return ImportEntry(
                source_file=source_file,
                module_path=fqn,
                imported_names=names,
                is_relative=False,
                language=language,
            )
        return None

    def _build_name_resolution_map(self) -> None:
        for source_file, entries in self._imports_by_file.items():
            name_map: dict[str, str] = {}
            for entry in entries:
                target_file = self._resolve_module_to_file(
                    entry.module_path,
                    entry.is_relative,
                    source_file,
                )
                if not target_file:
                    continue
                for name in entry.imported_names:
                    if name not in name_map:
                        name_map[name] = target_file
            if name_map:
                self._name_to_source[source_file] = name_map

    def _resolve_module_to_file(
        self,
        module_path: str,
        is_relative: bool,
        source_file: str,
    ) -> str:
        if module_path in self._module_to_file:
            return self._module_to_file[module_path]

        parts = module_path.split(".")
        for i in range(len(parts), 0, -1):
            partial = ".".join(parts[:i])
            if partial in self._module_to_file:
                return self._module_to_file[partial]

        if is_relative and source_file:
            source_dir = str(Path(source_file).parent)
            candidate = source_dir + "/" + module_path.lstrip("./").replace(".", "/")
            for ext in ("", ".py", ".js", ".ts", "/__init__.py"):
                check = candidate + ext
                if check in self._module_to_file:
                    return self._module_to_file[check]
                for _key, val in self._module_to_file.items():
                    if val == check:
                        return val

        return ""
