#!/usr/bin/env python3
"""
Call Graph — Bidirectional function-level call tracking.

Builds a directed graph of function/method calls within a project using
Tree-sitter AST parsing. Supports Python, JavaScript, TypeScript, Java,
Go, and C/C++.

Key classes:
- CallGraph: Construct and query function-level call relationships
- FunctionRef: Qualified function reference (file, name, line, language)
"""

import os
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from .callee_resolution import CalleeResolver
from .core.parser import Parser, ParseResult
from .function_extraction import (
    walk_tree as _walk_tree,
)
from .import_extractors import walk_imports
from .project_graph import _language_from_ext

_EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "htmlcov",
    ".cache",
    ".eggs",
    ".idea",
    ".vscode",
    ".claude",
}


class FunctionRef:
    """A qualified reference to a function/method in the project."""

    __slots__ = ("file_path", "name", "start_line", "end_line", "language", "receiver")

    def __init__(
        self,
        file_path: str,
        name: str,
        start_line: int,
        language: str,
        receiver: str | None = None,
        end_line: int | None = None,
    ) -> None:
        self.file_path = file_path
        self.name = name
        self.start_line = start_line
        self.end_line = end_line if end_line is not None else start_line
        self.language = language
        self.receiver = receiver

    def qualified_name(self) -> str:
        if self.receiver:
            return f"{self.file_path}:{self.receiver}.{self.name}"
        return f"{self.file_path}:{self.name}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FunctionRef):
            return NotImplemented
        return (
            self.file_path == other.file_path
            and self.name == other.name
            and self.start_line == other.start_line
        )

    def __hash__(self) -> int:
        return hash((self.file_path, self.name, self.start_line))

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "file": self.file_path,
            "name": self.name,
            "line": self.start_line,
            "end_line": self.end_line,
            "language": self.language,
        }
        if self.receiver:
            d["receiver"] = self.receiver
        return d


class CallGraph:
    """
    Project-level function call graph.

    Nodes: FunctionRef objects representing function/method definitions.
    Edges: A -> B means function A calls function B.

    The call graph supports bidirectional queries:
    - callers_of(func_name): who calls this function?
    - callees_of(func_name): what does this function call?
    """

    def __init__(self, project_root: str) -> None:
        self.project_root = Path(project_root).resolve()
        self._functions: list[FunctionRef] = []
        self._func_by_name: dict[str, list[FunctionRef]] = defaultdict(list)
        self._func_by_qualified: dict[str, FunctionRef] = {}
        self._func_by_file: dict[str, list[FunctionRef]] = defaultdict(list)
        self._callees: dict[FunctionRef, list[FunctionRef]] = defaultdict(list)
        self._callers: dict[FunctionRef, list[FunctionRef]] = defaultdict(list)
        self._call_edges: list[tuple[FunctionRef, FunctionRef, int]] = []
        self._built = False
        self._file_imports: dict[str, dict[str, str]] = {}
        self._file_module_map: dict[str, str] = {}
        self._imported_names: dict[str, dict[str, str]] = {}
        self._module_to_file: dict[str, str] = {}
        self._callee_resolver: CalleeResolver | None = None

    def build(self) -> None:
        """Scan the project and build the call graph."""
        if self._built:
            return

        supported_exts = {
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".java",
            ".go",
            ".c",
            ".cpp",
            ".cc",
            ".cxx",
        }

        all_files = self._iter_source_files(supported_exts)

        rel_to_abs: dict[str, str] = {}
        for f in all_files:
            try:
                rel = str(f.relative_to(self.project_root))
                rel_to_abs[rel] = str(f)
            except ValueError:
                continue

        parser = Parser()

        # Two-pass build so cross-file call resolution doesn't depend on
        # filesystem iteration order. Pass 1 indexes every file's defs into
        # ``self._func_by_name`` / ``_func_by_qualified``; Pass 2 then walks
        # the saved calls and resolves them against a now-complete index.
        # Previously the def-add and call-resolve ran in the same loop body,
        # so file A calling into file B would silently drop the edge when A
        # was iterated first — macOS APFS happens to iterate ``main.py``
        # last in test fixtures so it passed there, while Linux ext4 +
        # Windows hit the trap. Tracked across PR #133.
        per_file: list[
            tuple[str, str, str, dict[str, FunctionRef], list[dict[str, Any]]]
        ] = []

        for rel_path, abs_path in rel_to_abs.items():
            language = _language_from_ext(rel_path)
            if language is None:
                continue

            result: ParseResult = parser.parse_file(abs_path, language)
            if not result.success or result.tree is None:
                continue

            source = result.source_code
            tree = result.tree

            definitions, calls = _walk_tree(tree.root_node, source, language)

            imports: list[dict[str, Any]] = []
            walk_imports(tree.root_node, source, language, imports)
            self._collect_import_map(rel_path, imports, rel_to_abs)

            file_funcs: dict[str, FunctionRef] = {}
            for defn in definitions:
                ref = FunctionRef(
                    file_path=rel_path,
                    name=defn["name"],
                    start_line=defn["start_line"],
                    language=language,
                    receiver=defn.get("class"),
                    end_line=defn.get("end_line", defn["start_line"]),
                )
                self._functions.append(ref)
                self._func_by_name[defn["name"]].append(ref)
                self._func_by_file[rel_path].append(ref)
                qname = ref.qualified_name()
                self._func_by_qualified[qname] = ref
                file_funcs[defn["name"]] = ref

            per_file.append((rel_path, abs_path, language, file_funcs, calls))

        self._callee_resolver = CalleeResolver(
            functions_by_name=self._func_by_name,
            functions_by_file=self._func_by_file,
            name_to_source=self._imported_names,
        )

        # Pass 2: resolve calls against the fully-populated index.
        for rel_path, _abs_path, _language, file_funcs, calls in per_file:
            for call in calls:
                caller_ref = self._find_enclosing_func(file_funcs, call["line"])
                if caller_ref is None:
                    continue

                callee_refs = self._resolve_callee(call, rel_path, rel_to_abs)

                for callee_ref in callee_refs:
                    self._callees[caller_ref].append(callee_ref)
                    self._callers[callee_ref].append(caller_ref)
                    self._call_edges.append((caller_ref, callee_ref, call["line"]))

        self._build_module_to_file_map(rel_to_abs)
        self._built = True

    def _is_excluded(self, path: Path) -> bool:
        try:
            rel_parts = path.relative_to(self.project_root).parts
        except ValueError:
            rel_parts = path.parts
        return any(part in _EXCLUDE_DIRS or part.startswith(".") for part in rel_parts)

    def _iter_source_files(self, supported_exts: set[str]) -> list[Path]:
        """Return source files while pruning generated and hidden work dirs."""
        files: list[Path] = []
        for root, dirs, names in os.walk(self.project_root):
            dirs[:] = [
                name
                for name in dirs
                if name not in _EXCLUDE_DIRS and not name.startswith(".")
            ]
            for name in names:
                if name.startswith("."):
                    continue
                if Path(name).suffix.lower() in supported_exts:
                    files.append(Path(root) / name)
        return files

    def _collect_import_map(
        self,
        rel_path: str,
        imports: list[dict[str, Any]],
        rel_to_abs: dict[str, str],
    ) -> None:
        name_to_source: dict[str, str] = {}
        for imp in imports:
            resolved = imp.get("resolved_path", "")
            names = imp.get("names", [])
            is_relative = imp.get("is_relative", False)
            target_file = self._resolve_import_path(
                rel_path, resolved, is_relative, rel_to_abs
            )
            if target_file:
                for name in names:
                    name_to_source[name] = target_file
        if name_to_source:
            self._imported_names[rel_path] = name_to_source

    def _resolve_import_path(
        self,
        source_rel: str,
        resolved_path: str,
        is_relative: bool,
        rel_to_abs: dict[str, str],
    ) -> str:
        if not resolved_path:
            return ""
        if is_relative:
            source_dir = str(Path(source_rel).parent)
            candidate = str(Path(source_dir) / resolved_path)
            for ext in ("", ".py", ".js", ".ts", ".jsx", ".tsx"):
                check = candidate + ext
                if check in rel_to_abs:
                    return check
                idx_path = str(Path(candidate) / "__init__.py")
                if idx_path in rel_to_abs:
                    return idx_path
        else:
            candidate = resolved_path
            for ext in ("", ".py", ".js", ".ts", ".jsx", ".tsx"):
                check = candidate + ext
                if check in rel_to_abs:
                    return check
                idx_path = str(Path(candidate) / "__init__.py")
                if idx_path in rel_to_abs:
                    return idx_path
        return ""

    def _build_module_to_file_map(self, rel_to_abs: dict[str, str]) -> None:
        for rel_path in rel_to_abs:
            p = Path(rel_path)
            stem = p.stem
            if stem == "__init__":
                module_name = str(p.parent).replace("/", ".").replace("\\", ".")
            else:
                module_name = (
                    str(p.with_suffix("")).replace("/", ".").replace("\\", ".")
                )
            self._module_to_file[module_name] = rel_path

    def _find_enclosing_func(
        self,
        file_funcs: dict[str, FunctionRef],
        call_line: int,
    ) -> FunctionRef | None:
        """Find the function that contains the given line number.

        Uses both start_line and end_line for accurate range containment.
        Falls back to closest start_line when end_line is unreliable.
        """
        best: FunctionRef | None = None
        for ref in file_funcs.values():
            if ref.start_line <= call_line <= ref.end_line:
                if best is None or (
                    (ref.end_line - ref.start_line) < (best.end_line - best.start_line)
                ):
                    best = ref
        if best is not None:
            return best
        for ref in file_funcs.values():
            if ref.start_line <= call_line:
                if best is None or ref.start_line > best.start_line:
                    best = ref
        return best

    def _resolve_callee(
        self,
        call: dict[str, Any],
        source_rel: str,
        rel_to_abs: dict[str, str],
    ) -> list[FunctionRef]:
        name = call["name"]
        if self._callee_resolver is None:
            self._callee_resolver = CalleeResolver(
                functions_by_name=self._func_by_name,
                functions_by_file=self._func_by_file,
                name_to_source=self._imported_names,
            )
        return [
            ref
            for ref, _confidence in self._callee_resolver.resolve_items(
                name,
                source_rel,
            )
        ]

    def callers_of(
        self, func_name: str, file_path: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Find all functions that call the given function.

        Args:
            func_name: Name of the target function
            file_path: Optional file path to disambiguate overloaded functions

        Returns:
            List of caller FunctionRef dicts
        """
        self.build()
        targets = self._resolve_targets(func_name, file_path)
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for target in targets:
            for caller in self._callers.get(target, []):
                key = caller.qualified_name()
                if key not in seen:
                    seen.add(key)
                    result.append(caller.to_dict())
        return result

    def callees_of(
        self, func_name: str, file_path: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Find all functions called by the given function.

        Args:
            func_name: Name of the source function
            file_path: Optional file path to disambiguate overloaded functions

        Returns:
            List of callee FunctionRef dicts
        """
        self.build()
        targets = self._resolve_targets(func_name, file_path)
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for target in targets:
            for callee in self._callees.get(target, []):
                key = callee.qualified_name()
                if key not in seen:
                    seen.add(key)
                    result.append(callee.to_dict())
        return result

    def call_chain(
        self, func_name: str, file_path: str | None = None, depth: int = 5
    ) -> list[dict[str, Any]]:
        """
        Trace the full call chain from a function (callees, transitively).

        Args:
            func_name: Starting function name
            file_path: Optional file to disambiguate
            depth: Maximum depth to traverse

        Returns:
            List of dicts with 'caller', 'callee', 'depth' keys
        """
        self.build()
        targets = self._resolve_targets(func_name, file_path)
        result: list[dict[str, Any]] = []
        visited: set[str] = set()
        queue: deque[tuple[FunctionRef, int]] = deque((t, 0) for t in targets)

        while queue:
            current, d = queue.popleft()
            if d >= depth:
                continue
            for callee in self._callees.get(current, []):
                key = f"{current.qualified_name()}->{callee.qualified_name()}"
                if key not in visited:
                    visited.add(key)
                    result.append(
                        {
                            "caller": current.to_dict(),
                            "callee": callee.to_dict(),
                            "depth": d + 1,
                        }
                    )
                    queue.append((callee, d + 1))
        return result

    def all_functions(self) -> list[dict[str, Any]]:
        """Return all discovered functions."""
        self.build()
        return [f.to_dict() for f in self._functions]

    def call_edges(self) -> list[tuple["FunctionRef", "FunctionRef", int]]:
        """Return all discovered call edges as (caller, callee, line) tuples.

        Public accessor for the internal ``_call_edges`` list.  Prefer this
        over accessing ``_call_edges`` directly so callers are not coupled to
        the private attribute name.
        """
        self.build()
        return self._call_edges

    def function_refs(self) -> list["FunctionRef"]:
        """Return all discovered functions as ``FunctionRef`` objects.

        Unlike :meth:`all_functions` (which returns serialised ``dict``
        records), this returns the live ``FunctionRef`` instances needed for
        graph-walk algorithms such as dead-code analysis.
        """
        self.build()
        return self._functions

    def callee_refs_of(self, func: "FunctionRef") -> list["FunctionRef"]:
        """Return callees of *func* as ``FunctionRef`` objects.

        Unlike :meth:`callees_of` (which accepts a name string and returns
        serialised ``dict`` records), this accepts a live ``FunctionRef``
        and returns live objects — needed for graph-walk algorithms such as
        dead-code analysis.  Returns an empty list for unknown *func*.
        """
        self.build()
        return list(self._callees.get(func, []))

    def caller_refs_of(self, func: "FunctionRef") -> list["FunctionRef"]:
        """Return callers of *func* as ``FunctionRef`` objects.

        Unlike :meth:`callers_of` (which accepts a name string and returns
        serialised ``dict`` records), this accepts a live ``FunctionRef``
        and returns live objects — needed for graph-walk algorithms such as
        dead-code analysis.  Returns an empty list for unknown *func*.
        """
        self.build()
        return list(self._callers.get(func, []))

    def all_function_refs(self) -> list["FunctionRef"]:
        """Return all discovered FunctionRef objects (not serialised dicts).

        Use ``all_functions()`` when you need JSON-serialisable dicts.
        Use this method when you need to walk the adjacency maps returned
        by ``callers_map()`` / ``callees_map()``.
        """
        self.build()
        return list(self._functions)

    def callers_map(self) -> dict["FunctionRef", list["FunctionRef"]]:
        """Return a shallow copy of the caller adjacency map.

        Keys are callee FunctionRefs; values are lists of their callers.
        Mutating the returned dict does not affect internal state.
        """
        self.build()
        return dict(self._callers)

    def callees_map(self) -> dict["FunctionRef", list["FunctionRef"]]:
        """Return a shallow copy of the callee adjacency map.

        Keys are caller FunctionRefs; values are lists of their callees.
        Mutating the returned dict does not affect internal state.
        """
        self.build()
        return dict(self._callees)

    def functions_by_file(self) -> dict[str, list["FunctionRef"]]:
        """Return a shallow copy of the file → FunctionRef list mapping."""
        self.build()
        return dict(self._func_by_file)

    def resolve_targets(
        self, func_name: str, file_path: str | None = None
    ) -> list["FunctionRef"]:
        """Public alias for _resolve_targets() — resolve name to FunctionRef(s).

        Accepts the same forms as the private method:
        - bare name: ``"foo"``
        - qualified: ``"ClassName.method"``
        - file-scoped: ``func_name="foo", file_path="src/bar.py"``
        """
        self.build()
        return self._resolve_targets(func_name, file_path)

    def functions_in_file(self, file_path: str) -> list[dict[str, Any]]:
        """Return all functions defined in the given file."""
        self.build()
        return [f.to_dict() for f in self._func_by_file.get(file_path, [])]

    def function_refs_in_file(self, file_path: str) -> list["FunctionRef"]:
        """Return raw :class:`FunctionRef` objects for functions in *file_path*.

        Unlike :meth:`functions_in_file` (which serialises to dicts), this
        returns the live objects so callers can pass them to ``caller_refs_of``
        / ``callee_refs_of`` without an extra lookup.
        """
        self.build()
        return list(self._func_by_file.get(file_path, []))

    def file_impact(self, file_path: str) -> dict[str, Any]:
        """Analyze call-graph impact of changes to a file.

        Returns functions defined in the file, their callers (who depends
        on this file), and their callees (what this file depends on).
        """
        self.build()
        funcs = self._func_by_file.get(file_path, [])
        upstream: list[dict[str, Any]] = []
        downstream: list[dict[str, Any]] = []
        seen_up: set[str] = set()
        seen_down: set[str] = set()
        for func in funcs:
            for caller in self._callers.get(func, []):
                key = caller.qualified_name()
                if key not in seen_up:
                    seen_up.add(key)
                    upstream.append(caller.to_dict())
            for callee in self._callees.get(func, []):
                key = callee.qualified_name()
                if key not in seen_down:
                    seen_down.add(key)
                    downstream.append(callee.to_dict())
        return {
            "file": file_path,
            "function_count": len(funcs),
            "upstream_count": len(upstream),
            "downstream_count": len(downstream),
            "upstream": upstream,
            "downstream": downstream,
        }

    def summary(self) -> dict[str, Any]:
        """Return call graph summary statistics."""
        self.build()
        return {
            "function_count": len(self._functions),
            "call_edge_count": len(self._call_edges),
            "file_count": len({f.file_path for f in self._functions}),
        }

    def resolve_targets(
        self, func_name: str, file_path: str | None = None
    ) -> list["FunctionRef"]:
        """Public alias for :meth:`_resolve_targets`.

        Resolves a function name (and optional file path) to the matching
        :class:`FunctionRef` objects in the call graph.  See
        :meth:`_resolve_targets` for the full semantics.
        """
        return self._resolve_targets(func_name, file_path)

    # ------------------------------------------------------------------
    # Public aliases for internal helper methods (exposed for testing and
    # external tooling).  The private implementations remain unchanged.
    # ------------------------------------------------------------------

    @property
    def is_built(self) -> bool:
        """Return True after :meth:`build` has been called at least once."""
        return bool(self._built)

    def find_enclosing_func(
        self,
        file_funcs: dict,
        line_number: int,
    ) -> "FunctionRef | None":
        """Public alias for :meth:`_find_enclosing_func`.

        Returns the tightest-enclosing :class:`FunctionRef` for the given
        *line_number* among *file_funcs*, or ``None`` if the line falls
        before all known function starts.
        """
        return self._find_enclosing_func(file_funcs, line_number)

    def resolve_callee(
        self,
        call: dict,
        current_file: str,
        imports: dict,
    ) -> list["FunctionRef"]:
        """Public alias for :meth:`_resolve_callee`.

        Returns the list of :class:`FunctionRef` objects that *call* resolves
        to.  See :meth:`_resolve_callee` for full resolution semantics.
        """
        return self._resolve_callee(call, current_file, imports)

    def is_excluded(self, path: "Path") -> bool:
        """Public alias for :meth:`_is_excluded`.

        Returns ``True`` if *path* should be excluded from analysis
        (hidden directories, __pycache__, node_modules, etc.).
        """
        return self._is_excluded(path)

    def iter_source_files(self, supported_exts: set) -> list["Path"]:
        """Public alias for :meth:`_iter_source_files`.

        Yields source files under the project root whose suffix is in
        *supported_exts*, skipping excluded directories.
        """
        return self._iter_source_files(supported_exts)

    def _resolve_targets(
        self, func_name: str, file_path: str | None = None
    ) -> list[FunctionRef]:
        """Resolve a function name (and optional file) to FunctionRef(s).

        Accepts three shapes for ``func_name``:

        - bare name ``foo`` — returns every ``FunctionRef`` named ``foo``
        - qualified ``Class.method`` — returns only refs whose receiver
          equals ``Class`` AND whose bare name is ``method``. Falls back
          to the bare-name list when no receiver matches, so callers that
          pass dotted names (e.g. ``utils.helper`` from JS) keep working.
        - ``file:func`` via the explicit ``file_path`` argument.
        """
        if file_path:
            qname = f"{file_path}:{func_name}"
            ref = self._func_by_qualified.get(qname)
            if ref:
                return [ref]

        # Qualified ``Class.method`` lookup: rsplit on the last dot and
        # require an exact receiver match before falling back. We only
        # treat the dotted form as qualified when neither half is empty
        # so plain names (``.foo`` etc.) keep their literal lookup.
        if "." in func_name:
            receiver, _, suffix = func_name.rpartition(".")
            if receiver and suffix:
                bare_candidates = self._func_by_name.get(suffix, [])
                receiver_matches = [
                    c for c in bare_candidates if c.receiver == receiver
                ]
                if receiver_matches:
                    if file_path:
                        same = [c for c in receiver_matches if c.file_path == file_path]
                        return same if same else receiver_matches
                    return receiver_matches

        candidates = self._func_by_name.get(func_name, [])
        if file_path:
            same = [c for c in candidates if c.file_path == file_path]
            return same if same else candidates
        return candidates


class CachedCallGraph(CallGraph):
    """
    CallGraph built from pre-indexed AST cache (SQLite).

    Instead of re-parsing every file, reads function definitions and call
    edges from the ASTCache SQLite database. Falls back to full parse when
    the cache is empty or unavailable.

    CodeGraph parity: like CodeGraph's pre-indexed call graph, queries are
    instant after initial indexing.
    """

    def __init__(
        self,
        project_root: str,
        cache: Any | None = None,
        fallback: bool = True,
    ) -> None:
        super().__init__(project_root)
        self._cache = cache
        self._fallback = fallback

    def build(self) -> None:
        if self._built:
            return

        if self._cache is not None:
            self._build_from_cache()
        if not self._built and self._fallback:
            super().build()

    def close(self) -> None:
        if self._cache is not None and hasattr(self._cache, "close"):
            self._cache.close()

    def __del__(self) -> None:
        self.close()

    def _build_from_cache(self) -> None:
        try:
            if self._cache is None:
                return
            edges = self._cache.get_call_edges()
            functions = self._cache.get_functions()
            imports_raw = self._cache.get_imports()
        except Exception:
            return

        if not functions and not edges:
            return

        rel_files: set[str] = set()
        for func in functions:
            ref = FunctionRef(
                file_path=func["file"],
                name=func["name"],
                start_line=func["line"],
                language=func["language"],
                end_line=func.get("end_line", func["line"]),
                receiver=func.get("class"),
            )
            self._functions.append(ref)
            self._func_by_name[func["name"]].append(ref)
            self._func_by_file[func["file"]].append(ref)
            qname = ref.qualified_name()
            self._func_by_qualified[qname] = ref
            rel_files.add(func["file"])

        module_to_file: dict[str, str] = {}
        for rel in rel_files:
            p = Path(rel)
            stem = p.stem
            if stem == "__init__":
                mod = str(p.parent).replace("/", ".").replace("\\", ".")
            else:
                mod = str(p.with_suffix("")).replace("/", ".").replace("\\", ".")
            module_to_file[mod] = rel

        file_import_map: dict[str, dict[str, str]] = {}
        for file_path, import_texts in imports_raw.items():
            name_map: dict[str, str] = {}
            for imp_text in import_texts:
                parts = imp_text.split()
                if len(parts) >= 4 and parts[0] == "from":
                    mod_name = parts[1]
                    imported_names = [n.strip(",") for n in parts[3:] if n != "import"]
                    target_file = module_to_file.get(mod_name, "")
                    if target_file:
                        for name in imported_names:
                            name_map[name] = target_file
                elif len(parts) >= 2 and parts[0] == "import":
                    mod_name = parts[1].split(".")[0]
                    target_file = module_to_file.get(mod_name, "")
                    if target_file:
                        name_map[mod_name] = target_file
            if name_map:
                file_import_map[file_path] = name_map

        for edge in edges:
            caller_file = edge["caller_file"]
            caller_candidates = self._func_by_name.get(edge["caller_name"], [])
            caller_ref = None
            for c in caller_candidates:
                if c.file_path == caller_file:
                    caller_ref = c
                    break
            if caller_ref is None and caller_candidates:
                caller_ref = caller_candidates[0]
            if caller_ref is None:
                continue

            if self._callee_resolver is None:
                self._callee_resolver = CalleeResolver(
                    functions_by_name=self._func_by_name,
                    functions_by_file=self._func_by_file,
                    name_to_source=file_import_map,
                )

            resolved = [
                ref
                for ref, _confidence in self._callee_resolver.resolve_items(
                    edge["callee_name"],
                    caller_file,
                )
            ]

            for callee_ref in resolved:
                self._callees[caller_ref].append(callee_ref)
                self._callers[callee_ref].append(caller_ref)
                self._call_edges.append(
                    (caller_ref, callee_ref, edge.get("callee_line", 0))
                )

        self._built = True
