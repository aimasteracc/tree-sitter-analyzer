#!/usr/bin/env python3
"""
Call Graph — Bidirectional function-level call tracking.

Builds a directed graph of function/method calls within a project using
Tree-sitter AST parsing. Supported languages are derived from
``function_extraction.SUPPORTED_LANGUAGES`` (see ``SUPPORTED_EXTS`` below),
not hardcoded here.

Key classes:
- CallGraph: Construct and query function-level call relationships
- FunctionRef: Qualified function reference (file, name, line, language)
"""

import gc
import os
import sqlite3
import time
from collections import defaultdict, deque
from collections.abc import Collection, Iterable, Iterator
from collections.abc import Set as AbstractSet
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from . import call_graph_incremental, call_graph_memo, call_graph_store
from .cache import graph_input_rows, index_file_facts
from .cached_edge_resolution import CachedEdgeResolver
from .cached_reexport_binding import PackageReexportBinder
from .call_graph_binding import RefIdentity, pick_caller_ref, ref_identity
from .call_graph_possible import PossibleEdgesMixin
from .call_graph_self_dispatch import SubclassIndex
from .callee_resolution import CalleeResolver
from .class_mro import Hierarchy, load_hierarchy, load_hierarchy_update
from .constants import EXCLUDE_DIRS as _EXCLUDE_DIRS
from .constants import JS_TS_MODULE_EXTS
from .core.parser import Parser, ParseResult
from .function_extraction import SUPPORTED_LANGUAGES as _FUNC_EXTRACTION_LANGUAGES
from .function_extraction import (
    walk_tree as _walk_tree,
)
from .import_extractors import walk_imports
from .languages.lang_extension_map import EXT_TO_LANG
from .module_scope_caller import MODULE_SCOPE, is_module_caller, module_caller_ref
from .project_graph import _language_from_ext

# Derived (not hardcoded) from EXT_TO_LANG — the project's single source
# of truth for ext->language — filtered to languages function_extraction
# actually knows how to walk. See function_extraction.SUPPORTED_LANGUAGES
# docstring for why a hardcoded copy of this set is a recurring bug class.
SUPPORTED_EXTS: frozenset[str] = frozenset(
    ext for ext, lang in EXT_TO_LANG.items() if lang in _FUNC_EXTRACTION_LANGUAGES
)

# _EXCLUDE_DIRS used to be a second, independently-maintained copy of
# constants.EXCLUDE_DIRS missing target/obj/vendor/Pods/DerivedData (Codex
# #1157 P1): once rust/csharp/php/swift files were admitted by SUPPORTED_EXTS
# above, this scanner started walking into their build/vendor directories,
# which can be enormous and made graph construction appear to hang. Import
# the canonical set instead of re-copying it.


class FunctionRef:
    """A qualified reference to a function/method in the project."""

    __slots__ = (
        "file_path",
        "name",
        "start_line",
        "end_line",
        "language",
        "receiver",
        "_hash",
    )

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
        # #1723：身份字段创建后不再改写；构图对每个引用要哈希上百万次，只算一次。
        self._hash = hash((file_path, name, start_line))

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
        return self._hash

    def __reduce__(self) -> tuple[Any, ...]:
        # 字符串哈希按进程随机化：反序列化时重新计算缓存的哈希。
        return (
            FunctionRef,
            (
                self.file_path,
                self.name,
                self.start_line,
                self.language,
                self.receiver,
                self.end_line,
            ),
        )

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
        if is_module_caller(self.name):
            d["scope"] = MODULE_SCOPE  # #1622：模块作用域伪调用方
        return d


class CallGraph(PossibleEdgesMixin):
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
        # #1559/#1560：无法区分的同名候选不成为边，只供安全类消费者过近似。
        self._init_possible_edges()
        self._call_edges: list[tuple[FunctionRef, FunctionRef, int]] = []
        # RFC-0038：仅经注解绑定的边的来源，键为 (调用方身份, 被调方身份)。
        self._edge_bindings: dict[tuple[RefIdentity, RefIdentity], dict[str, Any]] = {}
        self._plain_edges: set[tuple[RefIdentity, RefIdentity]] = set()
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

        all_files = self._iter_source_files(SUPPORTED_EXTS)

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
                # Key by name AND start line: same-named methods in different
                # classes (two ``execute`` defs) must keep BOTH spans for
                # _find_enclosing_func, or calls inside the earlier one get
                # mis-attributed to an unrelated preceding function (#638).
                file_funcs[f"{defn['name']}:{defn['start_line']}"] = ref

            per_file.append((rel_path, abs_path, language, file_funcs, calls))

        self._callee_resolver = CalleeResolver(
            functions_by_name=self._func_by_name,
            functions_by_file=self._func_by_file,
            name_to_source=self._imported_names,
        )

        # Pass 2: resolve calls against the fully-populated index.
        for rel_path, _abs_path, language, file_funcs, calls in per_file:
            for call in calls:
                # #1622：无外围函数的调用点归属 ``<module>`` 伪调用方，不再丢弃。
                caller_ref = self._find_enclosing_func(
                    file_funcs, call["line"]
                ) or module_caller_ref(rel_path, call["line"], language)

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

    def _iter_source_files(self, supported_exts: AbstractSet[str]) -> list[Path]:
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
            for ext in ("", ".py", *JS_TS_MODULE_EXTS):
                check = candidate + ext
                if check in rel_to_abs:
                    return check
                idx_path = str(Path(candidate) / "__init__.py")
                if idx_path in rel_to_abs:
                    return idx_path
        else:
            candidate = resolved_path
            for ext in ("", ".py", *JS_TS_MODULE_EXTS):
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
        """Find the function whose span contains the given line number.

        Returns the tightest-enclosing FunctionRef (smallest span), or None
        when the call is module-level (no function's range contains it).
        The former "nearest preceding function" fallback has been removed:
        that fallback misattributed module-level call sites to the last
        function before them, producing wrong-name edges (#648).
        """
        best: FunctionRef | None = None
        for ref in file_funcs.values():
            if ref.start_line <= call_line <= ref.end_line:
                if best is None or (
                    (ref.end_line - ref.start_line) < (best.end_line - best.start_line)
                ):
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
        seen: set[RefIdentity] = set()
        result: list[dict[str, Any]] = []
        for target in targets:
            for caller in self._callers.get(target, []):
                # #1596：按定义行区分同名调用方，qualified_name 无 receiver 时会合并。
                key = ref_identity(caller)
                if key not in seen:
                    seen.add(key)
                    result.append(caller.to_dict())
        return result

    def _record_edge_binding(
        self,
        caller: FunctionRef,
        callee: FunctionRef,
        binding: dict[str, Any] | None,
    ) -> None:
        """RFC-0038：记录边是否只经注解绑定；同一对之间有普通边时不再标注。"""
        key = (ref_identity(caller), ref_identity(callee))
        if binding is None:
            self._plain_edges.add(key)
            self._edge_bindings.pop(key, None)
        elif key not in self._plain_edges:
            self._edge_bindings.setdefault(key, binding)

    def edge_binding(
        self, caller: FunctionRef, callee: FunctionRef
    ) -> dict[str, Any] | None:
        """``caller -> callee`` 仅经注解绑定时返回其 ``receiver_binding``。"""
        return self._edge_bindings.get((ref_identity(caller), ref_identity(callee)))

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
        seen: set[RefIdentity] = set()
        result: list[dict[str, Any]] = []
        for target in targets:
            for callee in self._callees.get(target, []):
                key = ref_identity(callee)
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
        visited: set[tuple[RefIdentity, RefIdentity]] = set()
        queue: deque[tuple[FunctionRef, int]] = deque((t, 0) for t in targets)

        while queue:
            current, d = queue.popleft()
            if d >= depth:
                continue
            for callee in self._callees.get(current, []):
                key = (ref_identity(current), ref_identity(callee))  # #1619
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

    def all_call_edges(self) -> list[tuple["FunctionRef", "FunctionRef", int]]:
        """Return all call edges as (caller, callee, line) tuples.

        Returns an independent copy so callers can mutate the list without
        affecting the internal graph state.
        """
        return list(self.call_edges())

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
        seen_up: set[RefIdentity] = set()  # #1619：按身份去重
        seen_down: set[RefIdentity] = set()
        for func in funcs:
            for caller in self._callers.get(func, []):
                key = ref_identity(caller)
                if key not in seen_up:
                    seen_up.add(key)
                    upstream.append(caller.to_dict())
            for callee in self._callees.get(func, []):
                key = ref_identity(callee)
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
        *line_number* among *file_funcs*, or ``None`` when no function's
        range contains the line (e.g. module-level call sites).
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

    def iter_source_files(self, supported_exts: AbstractSet[str]) -> list["Path"]:
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
        persist: bool = False,
    ) -> None:
        super().__init__(project_root)
        self._cache = cache
        self._fallback = fallback
        # #1675：为真时把边解析结果落盘，供冷进程复用（只读 / 零写入路由保持 False）。
        self._persist = persist
        self._input_digest: str | None = None
        # #1723：增量更新的对齐依据与上次增量的统计（`call_graph_incremental`）。
        self._incremental: dict[str, Any] | None = None
        self._incremental_stats: dict[str, Any] = {}
        self._hierarchy_loader: _LazyHierarchy | None = None

    def build(self) -> None:
        if self._built:
            return

        if self._cache is not None:
            # #1657：构图一次分配数百万个对象，循环 GC 会反复扫描进程里已有的大堆
            # （长驻服务器还持有旧图与各类缓存）。构图期间暂停循环回收，实测省
            # 1.1–1.4 s；结束后（含异常）恢复原状态，引用计数回收不受影响。
            with _cyclic_gc_paused():
                self._build_from_cache()
        if not self._built and self._fallback:
            super().build()

    def close(self) -> None:
        if self._cache is not None and hasattr(self._cache, "close"):
            self._cache.close()

    def __del__(self) -> None:
        self.close()

    def _build_from_cache(self) -> None:
        if self._cache is not None and self._adopt_published_warm():
            return
        try:
            if self._cache is None:
                return
            # #1691：库文件 stat 证据未变时，上次算出的构图输入摘要与边数仍成立，
            # 不必为算摘要而读出全部调用边（落盘的边解析结果按摘要取用）。
            facts_stamp = _index_file_stamp(self._cache)
            known_input = _known_graph_input(facts_stamp)
            edge_source = (
                None
                if known_input is not None
                else graph_input_rows.read_edge_source(self._cache)
            )
            function_source = graph_input_rows.read_function_source(self._cache)
            imports_raw = self._cache.get_imports()
        except sqlite3.Error:
            if getattr(self._cache, "strict_sql_errors", False):
                raise
            return
        except Exception:
            return

        # #1657：包再导出与子类证据先于摘要加载（与惰性加载读同一批表，失败语义不变），
        # 摘要覆盖本次构图消费的全部输入；内容相同则直接复用已建好的图。
        reexport_binder = PackageReexportBinder(self._cache)
        subclasses = SubclassIndex(self._cache)
        root = str(self.project_root)
        digest: str | None
        if known_input is not None:
            digest, edge_count = known_input
        else:
            digest = graph_input_digest(
                edge_source, function_source, imports_raw, reexport_binder, subclasses
            )

            edge_count = _row_count(edge_source)
            if digest is not None:
                index_file_facts.record(
                    facts_stamp, _GRAPH_INPUT_FACT, [digest, edge_count]
                )
        self._input_digest = digest
        owned = False
        if digest is not None:
            state = call_graph_memo.lookup(root, digest)
            if state is not None:
                self._adopt_state(state)
                return
            # #1708：同一输入的构建已在进行（发布后的后台预构图）时等它完成并复用，
            # 不并行构建第二份；输入不同（另一个版本）的构建互不等待。
            pending = call_graph_memo.claim(root, digest)
            if pending is not None:
                pending.wait(_INFLIGHT_WAIT_SECONDS)
                state = call_graph_memo.lookup(root, digest)
                if state is not None:
                    self._adopt_state(state)
                    return
                pending = call_graph_memo.claim(root, digest)
            owned = pending is None
        # 原始行交给构图后由它释放（构图期间不在本帧多持有一份）。
        sources = [edge_source, function_source]
        del edge_source, function_source
        try:
            self._build_after_miss(
                root,
                digest,
                edge_count,
                sources,
                imports_raw,
                reexport_binder,
                subclasses,
            )
        finally:
            if owned and digest is not None:
                call_graph_memo.release(root, digest)

    def _adopt_published_warm(self) -> bool:
        """#1708：采用发布后后台预构图的结果（同一索引库、身份未变时），不再读行。

        同一库的预构图在途时先等它结束；身份与 ``index_bound_graph`` 保留内存图的
        规则相同（#1564）。不满足任一条件即返回 False，照常读行并按输入摘要判定。
        """
        from . import call_graph_warm

        root = str(self.project_root)
        digest = call_graph_warm.adopt(root, getattr(self._cache, "db_path", None))
        if digest is None:
            return False
        state = call_graph_memo.lookup(root, digest)
        if state is None:
            return False
        self._adopt_state(state)
        return True

    def _build_after_miss(
        self,
        root: str,
        digest: str | None,
        edge_count: int,
        sources: list[Any],
        imports_raw: Any,
        reexport_binder: PackageReexportBinder,
        subclasses: SubclassIndex,
    ) -> None:
        """内存记忆未命中后的构图：落盘结果重放或现场解析（#1675）。"""
        edge_source, function_source = sources
        sources.clear()
        # 输入已变：先释放本根的旧状态，构图期间内存里不同时保留两张图。
        call_graph_memo.discard(root)

        try:
            functions = graph_input_rows.materialize_functions(function_source)
        except Exception:
            return
        # #1675：冷进程先找同代码、同输入摘要下已存的边解析结果。
        stored = (
            call_graph_store.load(
                root,
                digest,
                functions=len(functions),
                edges=edge_count,
            )
            if digest is not None
            else None
        )
        # #1723：边 rowid 与被调名留作下一次刷新后增量更新的对齐依据。
        alignment = call_graph_incremental.alignment(edge_source)
        records = (
            self._build_from_inputs(
                [], functions, imports_raw, reexport_binder, subclasses, stored=stored
            )
            if stored is not None
            else None
        )
        if records is not None:
            del edge_source, function_source
        else:
            self._reset_graph_state()
            try:
                if edge_source is None:
                    # 摘要已知但没有可用的落盘结果：照常读边并现场解析。
                    edge_source = graph_input_rows.read_edge_source(self._cache)
                edges = graph_input_rows.materialize_edges(edge_source)
            except Exception:
                return
            # 原始行已转换完毕：构图期间不再同时持有两份边数据。
            del edge_source, function_source
            records = self._build_from_inputs(
                edges, functions, imports_raw, reexport_binder, subclasses
            )
            if self._built and self._persist and digest is not None and records:
                call_graph_store.save(root, digest, self._functions, records)
        if self._built:
            if alignment is None:
                # #1726：摘要已知、未读边行时，只在长驻进程里补读对齐依据。
                alignment = call_graph_incremental.alignment_from_index(self._cache)
            call_graph_incremental.remember(
                self, alignment, records, reexport_binder, subclasses
            )
        if self._built and digest is not None:
            call_graph_memo.store(root, digest, self._export_state())

    def _export_state(self) -> dict[str, Any]:
        """构图完成后的全部状态（不含缓存句柄与项目根），供内容相同的图复用。"""
        return {
            name: value
            for name, value in vars(self).items()
            if name not in _UNSHARED_STATE
        }

    def _adopt_state(self, state: dict[str, Any]) -> None:
        """采用内容相同的输入构建出的状态；构建完成后状态只读，可以共享。"""
        for name, value in state.items():
            setattr(self, name, value)

    def _build_from_inputs(
        self,
        edges: list[dict[str, Any]],
        functions: list[dict[str, Any]],
        imports_raw: dict[str, Any],
        reexport_binder: PackageReexportBinder,
        subclasses: SubclassIndex,
        stored: list[Any] | None = None,
    ) -> list[call_graph_store.EdgeRecord] | None:
        """构图；返回应用的边解析结果。

        ``stored`` 为已存的编码结果（#1675）时不再解析 ``edges``，解码失败返回
        None（图状态未完成，调用方须重置后照常构建）。
        """
        if not functions and not edges and stored is None:
            return None

        self._index_function_refs(
            FunctionRef(
                file_path=func["file"],
                name=func["name"],
                start_line=func["line"],
                language=func["language"],
                end_line=func.get("end_line", func["line"]),
                receiver=func.get("class"),
            )
            for func in functions
        )
        edge_resolver = self._make_edge_resolver(
            imports_raw, reexport_binder, subclasses
        )
        if stored is not None:
            try:
                records = call_graph_store.decode(stored, self._functions, FunctionRef)
            except (ValueError, TypeError):
                return None
        else:
            records = [
                _resolve_edge(self._func_by_name, edge_resolver, e) for e in edges
            ]
        # 现场解析与已存结果走同一个应用函数，两条路径构出的图状态相同。
        self._apply_edge_records(records)

        # #1657：构图内记忆只服务这一次构建；保留下来的裸名解析器不再带着它。
        edge_resolver.release_memos()
        self._built = True
        return records

    def _index_function_refs(self, refs: Iterable[FunctionRef]) -> None:
        """按读取顺序登记函数定义（#1723：增量更新复用同一登记）。"""
        for ref in refs:
            self._functions.append(ref)
            self._func_by_name[ref.name].append(ref)
            self._func_by_file[ref.file_path].append(ref)
            self._func_by_qualified[ref.qualified_name()] = ref

    def _make_edge_resolver(
        self,
        imports_raw: dict[str, Any],
        reexport_binder: PackageReexportBinder,
        subclasses: SubclassIndex,
        hierarchy_base: Hierarchy | None = None,
        hierarchy_files: Collection[str] = (),
    ) -> CachedEdgeResolver:
        """函数索引登记完毕后，构造本次构图的边解析器（全量与增量共用）。"""
        self._hierarchy_loader = _LazyHierarchy(
            self._cache, hierarchy_base, hierarchy_files
        )
        rel_files = {path for path, refs in self._func_by_file.items() if refs}
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
            for imp in import_texts:
                imp_text = imp["text"] if isinstance(imp, dict) else imp
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

        edge_resolver = CachedEdgeResolver(
            functions_by_name=self._func_by_name,
            functions_by_file=self._func_by_file,
            file_import_map=file_import_map,
            reexport_binder=reexport_binder,
            subclasses=subclasses,
            # #1657：函数与 import 索引此时已完整且不再变化，相同输入只解析一次。
            memoize=True,
            # #1677：继承调用的 MRO 只读取一次，且只在需要时读取。
            hierarchy=self._hierarchy_loader,
        )
        if self._callee_resolver is None:
            self._callee_resolver = edge_resolver.callee_resolver
        return edge_resolver

    def _apply_edge_records(self, records: list[call_graph_store.EdgeRecord]) -> None:
        """按边的读取顺序把解析结果写入调用图（#1675：现场与已存结果共用）。

        #1723：增量更新每次都重放全部结果，这里把属性查找提到循环之外（效果与逐条
        调用 ``_add_possible_edges`` 相同）。
        """
        callees, callers, call_edges = self._callees, self._callers, self._call_edges
        possible_callees, possible_callers = (
            self._possible_callees,
            self._possible_callers,
        )
        record_binding = self._record_edge_binding
        for record in records:
            if record is None:
                continue
            caller_ref, certain, possible, binding, line = record
            if possible:
                possible_callees[caller_ref].extend(possible)
                for candidate in possible:
                    possible_callers[candidate].append(caller_ref)
            for callee_ref in certain:
                callees[caller_ref].append(callee_ref)
                callers[callee_ref].append(caller_ref)
                call_edges.append((caller_ref, callee_ref, line))
                record_binding(caller_ref, callee_ref, binding)

    def _reset_graph_state(self) -> None:
        """丢弃未完成的构图状态（已存结果解码失败后照常重建前）。"""
        CallGraph.__init__(self, str(self.project_root))


#: #1708：等待同一输入的在途构建（发布后的后台预构图）的上限；超时后自行构建。
_INFLIGHT_WAIT_SECONDS = 600.0
#: 不随复用的图状态共享的属性：缓存句柄属于各自的图对象，项目根由构造参数给出。
_UNSHARED_STATE = frozenset(
    {"_cache", "_fallback", "_persist", "project_root", "_hierarchy_loader"}
)


def graph_input_digest(
    edge_source: Any,
    function_source: Any,
    imports_raw: Any,
    reexport_binder: PackageReexportBinder,
    subclasses: SubclassIndex,
) -> str | None:
    """构图全部输入的内容摘要（#1657）；#1723 的增量结果补算同一摘要。"""
    return call_graph_memo.input_digest(
        *graph_input_rows.source_digest_parts(edge_source),
        *graph_input_rows.source_digest_parts(function_source),
        imports_raw,
        # #1675：集合按值排序后再摘要，摘要跨进程稳定（落盘结果按它取用）。
        call_graph_memo.stable_form(reexport_binder.evidence()),
        call_graph_memo.stable_form(subclasses.evidence()),
    )


#: ``index_file_facts`` 中构图输入事实的名字：``[#1663 输入摘要, 调用边行数]``。
_GRAPH_INPUT_FACT = "call_graph_input"


def _index_file_stamp(cache: Any) -> tuple[Any, ...] | None:
    """缓存所读库文件的 stat 证据；缓存没有磁盘库连接（测试替身、内存快照）时为 None。"""
    getter = getattr(cache, "get_conn", None)
    if not callable(getter):
        return None
    try:
        return index_file_facts.evidence(index_file_facts.database_of(getter()))
    except Exception:  # noqa: BLE001 — 取不到证据只是不复用
        return None


def _known_graph_input(stamp: tuple[Any, ...] | None) -> tuple[str, int] | None:
    """库文件证据未变时记下的 ``(输入摘要, 边数)``；没有或格式不符为 None。"""
    value = index_file_facts.lookup(stamp, _GRAPH_INPUT_FACT)
    if (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str)
        and value[0]
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
        and value[1] >= 0
    ):
        return value[0], value[1]
    return None


def _row_count(source: Any) -> int:
    rows = getattr(source, "rows", source)
    return len(rows)


def _resolve_edge(
    func_by_name: dict[str, list[FunctionRef]],
    edge_resolver: CachedEdgeResolver,
    edge: dict[str, Any],
) -> call_graph_store.EdgeRecord:
    """一条边的解析结果；无法确定调用方时为 None（与修复前一样跳过）。"""
    caller_file = edge["caller_file"]
    caller_ref = _edge_caller_ref(func_by_name, edge, caller_file)
    if caller_ref is None:
        return None
    # #1559/#1560：优先采用持久化解析，模糊的裸名匹配不再扇出成边。
    targets = edge_resolver.resolve(edge, caller_file, caller_ref.receiver)
    return (
        caller_ref,
        targets.certain,
        targets.possible,
        targets.binding,
        edge.get("callee_line", 0),
    )


class _LazyHierarchy:
    """#1677：首次需要时从索引读取类层级；读取失败为空层级（没有 MRO 证据）。

    #1723：给出上一张图的层级 ``base`` 与解析范围内的文件时，只重读这些文件。
    """

    def __init__(
        self,
        cache: Any,
        base: Hierarchy | None = None,
        files: Collection[str] = (),
    ) -> None:
        self._cache = cache
        self._base = base
        self._files = files
        self.value: Hierarchy | None = None
        #: #1723：读取层级花费的秒数（增量统计用）。
        self.seconds = 0.0

    def __call__(self) -> Hierarchy:
        if self.value is None:
            started = time.perf_counter()
            try:
                conn = self._cache.get_conn()
                self.value = (
                    load_hierarchy_update(conn, self._base, self._files)
                    if self._base is not None
                    else load_hierarchy(conn)
                )
            except Exception:  # nosec B110 — 没有连接：没有 MRO 证据。
                self.value = Hierarchy()
            self.seconds = time.perf_counter() - started
        return self.value


@contextmanager
def _cyclic_gc_paused() -> Iterator[None]:
    """暂停循环垃圾回收；只在进入时处于开启状态才在退出时重新开启。"""
    was_enabled = gc.isenabled()
    if was_enabled:
        gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.enable()


def _edge_caller_ref(
    func_by_name: dict[str, list[FunctionRef]], edge: dict[str, Any], caller_file: str
) -> FunctionRef | None:
    """调用边的调用方：模块作用域调用点（#1622）为 ``<module>``，否则按 #1596 绑定。

    缺调用行的模块作用域边无法给出坐标，返回 None（与修复前一致地跳过）。
    """
    if not edge.get("caller_name"):
        call_line = int(edge.get("callee_line") or 0)
        if call_line < 1:
            return None
        return module_caller_ref(caller_file, call_line, edge.get("language") or "")
    # #1596：同文件同名的调用方按定义行区分，不再取第一个同名函数。
    return pick_caller_ref(
        func_by_name.get(edge["caller_name"], []),
        caller_file,
        int(edge.get("caller_line") or 0),
    )
