#!/usr/bin/env python3
"""
File-level Import Dependency Graph — cache-backed file dependency analysis.

Builds a directed graph of file-to-file import dependencies from the
pre-indexed AST cache. Enables:
  - Reverse dependency lookup: "who imports this file?"
  - Forward dependency lookup: "what does this file import?"
  - File-level blast radius: "if I change X, which files are affected?"
  - Circular dependency detection
  - Module coupling analysis

CodeGraph parity: equivalent to CodeGraph's file-dependency-graph feature.
Extends P0 AST cache with a new graph dimension beyond the function-level
call graph.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_PY_FROM_IMPORT_RE = re.compile(
    r"^from\s+(?P<module>[a-zA-Z_][\w.]*)(?:\s+import\s+)"
)
_PY_BARE_IMPORT_RE = re.compile(
    r"^import\s+(?P<module>[a-zA-Z_][\w.]*)"
)
_PY_RELATIVE_IMPORT_RE = re.compile(
    r"^from\s+(?P<dots>\.{1,})(?P<module>\w[\w.]*)\s+import"
)

_JS_REQUIRE_RE = re.compile(
    r"""require\s*\(\s*['"](?P<path>\..*?)['"]\s*\)"""
)
_JS_ESM_IMPORT_RE = re.compile(
    r"""import\s+.*?\s+from\s+['"](?P<path>\..*?)['"]"""
)

_PY_STDLIB_PREFIXES = frozenset(
    {
        "os", "sys", "re", "json", "math", "time", "datetime", "pathlib",
        "collections", "itertools", "functools", "typing", "abc", "io",
        "hashlib", "logging", "subprocess", "threading", "multiprocessing",
        "asyncio", "dataclasses", "enum", "copy", "glob", "fnmatch",
        "traceback", "inspect", "importlib", "unittest", "argparse",
        "configparser", "tempfile", "shutil", "textwrap", "string",
        "struct", "pickle", "sqlite3", "csv", "xml", "html", "http",
        "urllib", "email", "socket", "ssl", "select",
        "signal", "mmap", "ctypes", "queue", "heapq", "bisect",
        "array", "weakref", "types", "contextlib", "operator",
        "numbers", "decimal", "fractions", "random", "statistics",
        "pprint", "locale", "gettext", "base64", "binascii", "codecs",
        "difflib", "linecache", "tokenize", "dis", "platform", "errno",
        "atexit", "warnings", "gc", "resource", "posixpath", "ntpath",
        "genericpath", "stat", "filecmp", "tarfile", "zipfile", "gzip",
        "bz2", "lzma", "zlib", "secrets", "uuid", "pdb", "profile",
        "timeit", "tracemalloc", "venv", "site", "code", "codeop",
        "compileall", "py_compile", "symtable", "parser", "ast",
        "builtins", "__future__", "_thread",
    }
)


@dataclass
class ImportEdge:
    source_file: str
    target_file: str
    import_text: str
    line: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source_file,
            "target": self.target_file,
            "import": self.import_text,
            "line": self.line,
        }


@dataclass
class ImportGraphResult:
    edges: list[ImportEdge] = field(default_factory=list)
    file_count: int = 0
    edge_count: int = 0
    cycles: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_count": self.file_count,
            "edge_count": self.edge_count,
            "edges": [e.to_dict() for e in self.edges],
            "cycles": self.cycles,
        }


def _resolve_python_import(
    import_text: str,
    source_file: str,
    project_files: set[str],
    project_root: str,
) -> str | None:
    """Resolve a Python import statement to a project-relative file path."""
    rel_src = os.path.relpath(source_file, project_root) if os.path.isabs(source_file) else source_file

    m = _PY_RELATIVE_IMPORT_RE.match(import_text)
    if m:
        num_dots = len(m.group("dots"))
        module = m.group("module")
        src_dir = os.path.dirname(rel_src)
        for _ in range(num_dots - 1):
            src_dir = os.path.dirname(src_dir)
        parts = module.split(".") if module else []
        candidate = os.path.join(src_dir, *parts) if parts else src_dir
        for suffix in (".py", os.path.join("__init__.py", "")):
            if suffix.endswith(os.sep):
                test = candidate + os.sep + "__init__.py"
            else:
                test = candidate + suffix
            test = os.path.normpath(test)
            if test in project_files:
                return test
        test_pkg = os.path.join(candidate, "__init__.py")
        test_pkg = os.path.normpath(test_pkg)
        if test_pkg in project_files:
            return test_pkg
        return None

    m = _PY_FROM_IMPORT_RE.match(import_text)
    if not m:
        m = _PY_BARE_IMPORT_RE.match(import_text)
    if not m:
        return None

    module = m.group("module")
    top_level = module.split(".")[0]
    if top_level in _PY_STDLIB_PREFIXES:
        return None

    parts = module.split(".")
    candidate = os.path.join(*parts) + ".py"
    candidate = os.path.normpath(candidate)
    if candidate in project_files:
        return candidate

    candidate_pkg = os.path.join(*parts, "__init__.py")
    candidate_pkg = os.path.normpath(candidate_pkg)
    if candidate_pkg in project_files:
        return candidate_pkg

    return None


def _resolve_js_import(
    import_text: str,
    source_file: str,
    project_files: set[str],
    project_root: str,
) -> str | None:
    """Resolve a JS/TS require/import to a project-relative file path."""
    rel_src = os.path.relpath(source_file, project_root) if os.path.isabs(source_file) else source_file
    src_dir = os.path.dirname(rel_src)

    m = _JS_REQUIRE_RE.search(import_text) or _JS_ESM_IMPORT_RE.search(import_text)
    if not m:
        return None

    req_path = m.group("path")
    candidate = os.path.normpath(os.path.join(src_dir, req_path))

    for suffix in ("", ".js", ".ts", ".jsx", ".tsx", "/index.js", "/index.ts"):
        test = candidate + suffix
        test = os.path.normpath(test)
        if test in project_files:
            return test
    return None


class ImportGraph:
    """
    File-level import dependency graph built from cached AST data.

    Uses the pre-indexed AST cache's import data to build a directed graph
    of file-to-file dependencies. Resolves Python dotted imports and
    JS/TS relative imports to actual project files.
    """

    def __init__(self, project_root: str) -> None:
        self.project_root = os.path.abspath(project_root)
        self._edges: list[ImportEdge] = []
        self._forward: dict[str, list[ImportEdge]] = {}
        self._reverse: dict[str, list[ImportEdge]] = {}
        self._project_files: set[str] = set()
        self._built = False

    def build(self) -> ImportGraphResult:
        """Build the import graph from AST cache data."""
        if self._built:
            return self._make_result()

        from .ast_cache import ASTCache

        try:
            cache = ASTCache(self.project_root)
        except Exception:
            logger.warning("Failed to open AST cache for import graph")
            return ImportGraphResult()

        try:
            imports_by_file = cache.get_imports()
        finally:
            cache.close()

        self._project_files = set(imports_by_file.keys())

        for source_file, imports in imports_by_file.items():
            if not isinstance(imports, list):
                continue
            for imp_text in imports:
                if not isinstance(imp_text, str):
                    continue
                resolved = self._resolve_import(imp_text, source_file)
                if resolved is None or resolved == source_file:
                    continue
                edge = ImportEdge(
                    source_file=source_file,
                    target_file=resolved,
                    import_text=imp_text,
                    line=0,
                )
                self._edges.append(edge)
                self._forward.setdefault(source_file, []).append(edge)
                self._reverse.setdefault(resolved, []).append(edge)

        self._built = True
        return self._make_result()

    def _resolve_import(self, import_text: str, source_file: str) -> str | None:
        if import_text.startswith("from ") or import_text.startswith("import "):
            return _resolve_python_import(
                import_text, source_file, self._project_files, self.project_root
            )
        if "require(" in import_text or "from '" in import_text or 'from "' in import_text:
            return _resolve_js_import(
                import_text, source_file, self._project_files, self.project_root
            )
        return None

    def _make_result(self) -> ImportGraphResult:
        return ImportGraphResult(
            edges=list(self._edges),
            file_count=len(self._project_files),
            edge_count=len(self._edges),
            cycles=self._detect_cycles(),
        )

    def dependents_of(self, file_path: str) -> list[dict[str, Any]]:
        """Find all files that import the given file (reverse deps)."""
        if not self._built:
            self.build()
        rel = os.path.relpath(os.path.abspath(file_path), self.project_root) if os.path.isabs(file_path) else file_path
        edges = self._reverse.get(rel, [])
        return [e.to_dict() for e in edges]

    def dependencies_of(self, file_path: str) -> list[dict[str, Any]]:
        """Find all files that the given file imports (forward deps)."""
        if not self._built:
            self.build()
        rel = os.path.relpath(os.path.abspath(file_path), self.project_root) if os.path.isabs(file_path) else file_path
        edges = self._forward.get(rel, [])
        return [e.to_dict() for e in edges]

    def blast_radius(self, file_path: str, max_depth: int = 10) -> dict[str, Any]:
        """Compute transitive reverse deps — all files affected by changing this file."""
        if not self._built:
            self.build()
        rel = os.path.relpath(os.path.abspath(file_path), self.project_root) if os.path.isabs(file_path) else file_path
        visited: set[str] = set()
        frontier = [rel]
        depth_map: dict[str, int] = {rel: 0}

        while frontier:
            current = frontier.pop(0)
            if current in visited:
                continue
            visited.add(current)
            current_depth = depth_map.get(current, 0)
            if current_depth >= max_depth:
                continue
            for edge in self._reverse.get(current, []):
                dep = edge.source_file
                if dep not in visited:
                    depth_map[dep] = current_depth + 1
                    frontier.append(dep)

        affected = visited - {rel}
        depth_sorted = sorted(affected, key=lambda f: (depth_map.get(f, 0), f))
        return {
            "file": rel,
            "direct_dependents": len(self._reverse.get(rel, [])),
            "transitive_dependents": len(affected),
            "affected_files": [
                {"file": f, "depth": depth_map.get(f, 0)}
                for f in depth_sorted
            ],
        }

    def _detect_cycles(self) -> list[list[str]]:
        """Detect import cycles using DFS."""
        cycles: list[list[str]] = []
        visited: set[str] = set()
        in_stack: set[str] = set()
        path: list[str] = []

        def _dfs(node: str) -> None:
            if len(cycles) >= 20:
                return
            visited.add(node)
            in_stack.add(node)
            path.append(node)

            for edge in self._forward.get(node, []):
                target = edge.target_file
                if target in in_stack:
                    idx = path.index(target)
                    cycle = path[idx:] + [target]
                    cycles.append(list(cycle))
                elif target not in visited:
                    _dfs(target)

            path.pop()
            in_stack.discard(node)

        for node in sorted(self._project_files):
            if node not in visited:
                _dfs(node)

        return cycles

    def summary(self) -> dict[str, Any]:
        """Return summary statistics."""
        if not self._built:
            self.build()
        fan_out = {f: len(e) for f, e in self._forward.items() if e}
        fan_in = {f: len(e) for f, e in self._reverse.items() if e}
        return {
            "file_count": self._project_files and len(self._project_files) or 0,
            "edge_count": len(self._edges),
            "files_with_imports": len(fan_out),
            "files_imported_by_others": len(fan_in),
            "cycle_count": len(self._detect_cycles()),
            "most_imported": sorted(fan_in.items(), key=lambda x: -x[1])[:10],
            "most_importing": sorted(fan_out.items(), key=lambda x: -x[1])[:10],
        }
