"""
Project-level dependency graph generation and analysis.

Builds a directed graph of file dependencies using Tree-sitter AST parsing.
Supports Python, JavaScript, and TypeScript import/require statement extraction.

Key classes:
- DependencyGraph: Construct and query a project's dependency graph
- BlastRadius: Impact analysis (forward/reverse dependency traversal)
"""

import os
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .constants import EXCLUDE_DIRS
from .core.parser import Parser, ParseResult
from .import_extractors import (
    walk_imports,
)
from .symbol_extractors import extract_top_level_defs_from_file


@dataclass(frozen=True)
class SymbolFanIn:
    """Result type for :meth:`DependencyGraph.symbol_in_degree`.

    ``file_count`` is the primary signal — distinct importing files,
    deduplicated. ``importer_files`` carries the same set as a sorted
    deterministic tuple so callers can render evidence lists without
    re-querying. ``defining_files`` records every project file that
    defines a symbol by this name; ``ambiguous`` is the convenience
    flag for the >1-definition case (P4 will demote confidence when
    set).
    """

    symbol: str
    file_count: int
    importer_files: tuple[str, ...]
    defining_files: tuple[str, ...]
    ambiguous: bool


def _language_from_ext(file_path: str) -> str | None:
    """Guess language from file extension.

    Thin re-export of :func:`tree_sitter_analyzer._lang_extension_map.language_from_ext`
    — see that module for the canonical ext→language mapping and the
    history of why duplicating this dict in two files was a multi-month
    silent bug (Swift/Kotlin/Ruby/PHP/C# silently dropped — fixed
    2026-05-24).
    """
    from .languages.lang_extension_map import language_from_ext

    return language_from_ext(file_path)


def _resolve_relative_import(module_path: str, current_file_rel: str) -> str | None:
    """
    Resolve a relative Python import ('.utils', '..pkg.sub') to a relative file path.

    Returns None if the import is not project-internal.

    Note: Only the ``.py`` (file-module) candidate is returned here.
    Package-module resolution (``<rest>/__init__.py``) is performed by
    ``DependencyGraph._resolve_to_project_file`` because it requires the
    set of project nodes to decide which candidate actually exists.
    Returning the ``.py`` form keeps the public helper's contract stable
    for callers that only care about the file-module shape.
    """
    if not module_path.startswith("."):
        return None  # absolute import → external or stdlib

    # Count leading dots
    dots = 0
    for ch in module_path:
        if ch == ".":
            dots += 1
        else:
            break

    current_dir = Path(current_file_rel).parent
    # Navigate up
    target_dir = current_dir
    for _ in range(dots - 1):
        target_dir = target_dir.parent

    # Convert module path to file path
    module_rest = module_path[dots:]  # e.g., "utils" or "models.user"
    if not module_rest:
        # Bare dots-only ``module_path`` (e.g. "." or ".."). The
        # extractor always pairs dots with a submodule name before
        # calling us, so this branch should not be hit in practice.
        # Return None to signal "no file-module candidate".
        return None
    module_file = module_rest.replace(".", "/") + ".py"

    resolved = target_dir / module_file
    return str(resolved).replace("\\", "/")


def _relative_init_candidate(module_path: str, current_file_rel: str) -> str | None:
    """Return the ``__init__.py`` (package-module) candidate for a relative import.

    Mirrors ``_resolve_relative_import`` but returns the path that would
    resolve when the imported name names a package rather than a single
    file. Used by the resolver to fall back when the ``.py`` form does
    not exist in the project.
    """
    if not module_path.startswith("."):
        return None

    dots = 0
    for ch in module_path:
        if ch == ".":
            dots += 1
        else:
            break

    current_dir = Path(current_file_rel).parent
    target_dir = current_dir
    for _ in range(dots - 1):
        target_dir = target_dir.parent

    module_rest = module_path[dots:]
    if not module_rest:
        candidate = target_dir / "__init__.py"
    else:
        candidate = target_dir / module_rest.replace(".", "/") / "__init__.py"
    return str(candidate).replace("\\", "/")


def _relative_anchor_init(module_path: str, current_file_rel: str) -> str | None:
    """Return the ancestor package's ``__init__.py`` for a relative import.

    This is the fallback Python uses when ``from . import name`` (or
    ``from .. import name``) names neither a sub-module file nor a
    sub-package — in that case the import binds the attribute ``name``
    that the ancestor package's ``__init__.py`` defines.

    For ``from .x.y import …`` with ``N`` leading dots, the anchor
    package is the directory you reach by walking up ``N-1`` levels
    from the current file. Strips any sub-module path because the
    fallback always targets the anchor itself, not the deeper sub-path.
    """
    if not module_path.startswith("."):
        return None

    dots = 0
    for ch in module_path:
        if ch == ".":
            dots += 1
        else:
            break

    current_dir = Path(current_file_rel).parent
    target_dir = current_dir
    for _ in range(dots - 1):
        target_dir = target_dir.parent

    return str(target_dir / "__init__.py").replace("\\", "/")


def _project_rel_join(source_rel: str, module_path: str) -> str:
    """Join project-relative imports with stable POSIX separators.

    DependencyGraph nodes are project-relative POSIX paths even on Windows.
    Using ``Path`` here lets the host OS leak ``\\`` into resolver candidates,
    so keep import resolution in PurePosixPath space.
    """
    source_dir = PurePosixPath(source_rel.replace("\\", "/")).parent
    return str(source_dir / module_path).replace("\\", "/")


def extract_imports_from_file(
    file_path: str, language: str | None = None
) -> list[dict[str, Any]]:
    """
    Extract import statements from a single source file.

    Args:
        file_path: Path to the source file
        language: Programming language (auto-detected if None)

    Returns:
        List of import dicts with keys: module_name, resolved_path, names, is_relative
    """
    if language is None:
        language = _language_from_ext(file_path)
    if language is None:
        return []

    try:
        parser = Parser()
        result: ParseResult = parser.parse_file(file_path, language)
    except Exception:
        return []

    if not result.success or result.tree is None:
        return []

    source = result.source_code
    tree = result.tree
    imports: list[dict[str, Any]] = []

    # Walk AST to find import nodes
    walk_imports(tree.root_node, source, language, imports)

    return imports


# ============================================================
# Per-language import resolvers (r37bi)
# ============================================================


def _resolve_python_import(
    module: str, source_rel: str, nodes: set[str], is_relative: bool
) -> str | None:
    """Python import → package/__init__.py or module.py."""
    if is_relative:
        init_candidate = _relative_init_candidate(module, source_rel)
        if init_candidate and init_candidate in nodes:
            return init_candidate
        file_candidate = _resolve_relative_import(module, source_rel)
        if file_candidate and file_candidate in nodes:
            return file_candidate
        # ``from . import name`` fallback to ancestor's ``__init__.py``.
        anchor_init = _relative_anchor_init(module, source_rel)
        if anchor_init and anchor_init in nodes:
            return anchor_init
        return file_candidate  # legacy: return file form even if absent
    # Absolute import — package form takes precedence (matches CPython).
    init_candidate_abs = module.replace(".", "/") + "/__init__.py"
    if init_candidate_abs in nodes:
        return init_candidate_abs
    file_candidate_abs = module.replace(".", "/") + ".py"
    if file_candidate_abs in nodes:
        return file_candidate_abs
    return None


def _resolve_js_ts_import(
    module: str, source_rel: str, nodes: set[str], is_relative: bool
) -> str | None:
    """JS/TS import → ``./foo`` resolved to file/index w/ common extensions."""
    if not is_relative:
        return None
    candidate_raw = _project_rel_join(source_rel, module)
    for ext in (".js", ".ts", ".jsx", ".tsx", "/index.js", "/index.ts"):
        candidate = candidate_raw + ext
        if candidate in nodes:
            return candidate
    if candidate_raw in nodes:
        return candidate_raw
    return None


def _resolve_go_import(
    module: str, source_rel: str, nodes: set[str], is_relative: bool
) -> str | None:
    """Go relative imports — extension probe similar to JS."""
    if not is_relative:
        return None
    candidate_raw = _project_rel_join(source_rel, module)
    if candidate_raw in nodes:
        return candidate_raw
    for ext in (".go", "/index.go"):
        candidate = candidate_raw + ext
        if candidate in nodes:
            return candidate
    return None


def _resolve_rust_import(
    module: str, source_rel: str, nodes: set[str], is_relative: bool
) -> str | None:
    """Rust relative imports — strip crate/super/self, replace ``::`` with ``/``."""
    if not is_relative:
        return None
    path_parts = (
        module.replace("crate::", "").replace("super::", "").replace("self::", "")
    )
    path = path_parts.replace("::", "/")
    candidate = _project_rel_join(source_rel, path)
    if candidate in nodes:
        return candidate
    for ext in (".rs", "/mod.rs", "/lib.rs"):
        candidate_with_ext = candidate + ext
        if candidate_with_ext in nodes:
            return candidate_with_ext
    return None


def _resolve_c_cpp_import(
    module: str, source_rel: str, nodes: set[str], is_relative: bool
) -> str | None:
    """C/C++ ``#include "foo.h"`` → relative to source dir."""
    candidate = _project_rel_join(source_rel, module)
    if candidate in nodes:
        return candidate
    return None


def _resolve_java_import(
    module: str, source_rel: str, nodes: set[str], is_relative: bool
) -> str | None:
    """Java import → ``com.foo.Bar`` to ``com/foo/Bar.java``."""
    candidate = module.replace(".", "/") + ".java"
    if candidate in nodes:
        return candidate
    return None


# r37bi: per-language dispatch table replaces the 6-branch if/elif chain
# inside ``_resolve_to_project_file``. Adding a new language is now a one-
# line dict entry + a focused resolver.
_IMPORT_RESOLVERS: dict[str, Callable[[str, str, set[str], bool], str | None]] = {
    "python": _resolve_python_import,
    "javascript": _resolve_js_ts_import,
    "typescript": _resolve_js_ts_import,
    "go": _resolve_go_import,
    "rust": _resolve_rust_import,
    "c": _resolve_c_cpp_import,
    "cpp": _resolve_c_cpp_import,
    "java": _resolve_java_import,
}


# ============================================================
# DependencyGraph
# ============================================================


class DependencyGraph:
    """
    Project-level dependency graph.

    Nodes: relative file paths (from project root).
    Edges: A → B means file A imports/depends on file B.

    Attributes:
        project_root: The root directory of the project
        _nodes: Set of relative file paths
        _edges: Set of (from_file, to_file) tuples
        _deps: Dict mapping file → set of files it depends on
        _dependents: Dict mapping file → set of files that depend on it
        _cache_key: Content hash for cache invalidation
    """

    _global_cache: dict[str, "DependencyGraph"] = {}

    def __new__(cls, project_root: str) -> "DependencyGraph":
        # Use cache keyed by project_root + mtime
        key = cls._cache_key_for(project_root)
        if key is not None and key in cls._global_cache:
            return cls._global_cache[key]

        instance = super().__new__(cls)
        cls._global_cache[key or project_root] = instance
        return instance

    def __init__(self, project_root: str) -> None:
        if hasattr(self, "_initialized") and self._initialized:  # type: ignore[has-type]
            return

        self.project_root = Path(project_root).resolve()
        self._nodes: set[str] = set()
        self._edges: set[tuple[str, str]] = set()
        self._deps: dict[str, set[str]] = defaultdict(set)
        self._dependents: dict[str, set[str]] = defaultdict(set)

        # PR-0.2: symbol-level fan-in index.
        # ``_symbol_importers[name]`` = set of files that import a symbol
        # with that name (deduplicated). Powers ``symbol_in_degree()``.
        # ``_symbol_def_files[name]`` = set of files that define a symbol
        # with that name. Lets the same query disambiguate when multiple
        # files define a homonymous symbol.
        # ``_symbol_importer_targets`` = which definition file each
        # importer actually resolved to, for the ``defining_file=`` kwarg.
        self._symbol_importers: dict[str, set[str]] = defaultdict(set)
        self._symbol_def_files: dict[str, set[str]] = defaultdict(set)
        self._symbol_importer_targets: dict[tuple[str, str], set[str]] = defaultdict(
            set
        )

        self._initialized = True

        self._build()

    @staticmethod
    def _cache_key_for(project_root: str) -> str | None:
        """Generate a cache key based on project source-file fingerprint.

        Uses ``compute_graph_fingerprint`` (file_count + max_mtime_ns of all
        source files) instead of the project-root directory mtime alone.
        Directory mtime only flips on file add/remove, so modifying a file
        in place previously left a stale graph cached forever.

        Cost: ~10ms on a 1300-file repo — fast enough to call on every
        ``DependencyGraph(root)`` construction.
        """
        try:
            os.stat(project_root)
        except OSError:
            return None
        from .cache.fingerprint import compute_graph_fingerprint

        fp = compute_graph_fingerprint(project_root)
        return f"{project_root}:{fp.file_count}:{fp.max_mtime_ns}"

    # Shared exclude set (incl. C#/Java/Rust build dirs) — constants.EXCLUDE_DIRS
    _EXCLUDE_DIRS = EXCLUDE_DIRS

    def _is_excluded(self, path: Path) -> bool:
        """Check if a path is inside an excluded directory."""
        try:
            rel_parts = path.relative_to(self.project_root).parts
        except ValueError:
            rel_parts = path.parts
        return any(
            part in self._EXCLUDE_DIRS or part.startswith(".") for part in rel_parts
        )

    def _iter_source_files(self, supported_exts: set[str]) -> list[Path]:
        """Return source files while pruning generated and hidden work dirs."""
        files: list[Path] = []
        for root, dirs, names in os.walk(self.project_root):
            dirs[:] = [
                name
                for name in dirs
                if name not in self._EXCLUDE_DIRS and not name.startswith(".")
            ]
            for name in names:
                if name.startswith("."):
                    continue
                if Path(name).suffix.lower() in supported_exts:
                    files.append(Path(root) / name)
        return files

    def _build(self) -> None:
        """Scan project directory and build the dependency graph."""
        supported_exts = {
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".java",
            ".go",
            ".rs",
            ".c",
            ".cpp",
            ".cc",
            ".cxx",
            ".h",
            ".hpp",
            ".hxx",
        }

        # Collect all source files (excluding generated/dependency dirs)
        all_files = self._iter_source_files(supported_exts)

        # Build relative path mapping
        rel_to_abs: dict[str, str] = {}
        for f in all_files:
            try:
                rel = str(f.relative_to(self.project_root)).replace("\\", "/")
                rel_to_abs[rel] = str(f)
                self._nodes.add(rel)
            except ValueError:
                continue

        # Parse each file and extract imports + top-level definitions.
        # The symbol index lives alongside the file-edge index — same
        # walk, no extra IO cost on the import side. See PR-0.2 design
        # in .recon/pr-0-2-design.md for the rationale.
        for rel_path, abs_path in rel_to_abs.items():
            language = _language_from_ext(rel_path)
            if language is None:
                continue

            # Populate _symbol_def_files BEFORE the import pass so the
            # ambiguity check in symbol_in_degree() is meaningful even
            # if no other file imports this symbol yet.
            for name in extract_top_level_defs_from_file(abs_path, language):
                self._symbol_def_files[name].add(rel_path)

            raw_imports = extract_imports_from_file(abs_path, language)
            for imp in raw_imports:
                resolved = self._resolve_to_project_file(imp, rel_path, rel_to_abs)
                if resolved and resolved in self._nodes:
                    self._edges.add((rel_path, resolved))
                    self._deps[rel_path].add(resolved)
                    self._dependents[resolved].add(rel_path)

                    # Symbol-level fan-in: every named import becomes a
                    # (symbol, importer) pair. Guards:
                    #  (a) ``resolved in self._nodes`` (already true here)
                    #  (b) skip empty names (JS bare imports yield [])
                    #  (c) skip submodule-as-name imports: ``from . import
                    #      sub`` lists ``sub`` in ``names`` AND resolves to
                    #      ``sub.py`` — so ``name`` equals the resolved
                    #      file's basename. That ``sub`` is the module
                    #      handle, not an imported symbol; counting it
                    #      would falsely treat any file with a sibling
                    #      ``sub`` import as a symbol-importer of every
                    #      definition in ``sub.py``.
                    resolved_stem = Path(resolved).stem
                    for name in imp.get("names", ()) or ():
                        if not name or name == resolved_stem:
                            continue
                        self._symbol_importers[name].add(rel_path)
                        self._symbol_importer_targets[(name, rel_path)].add(resolved)

    def _resolve_to_project_file(
        self,
        imp: dict[str, Any],
        source_rel: str,
        rel_to_abs: dict[str, str],
    ) -> str | None:
        """Resolve an import dict to a project-relative file path.

        r37bi (dogfood): tool flagged this at 109 lines. The per-language
        if/elif chain was 6 near-identical branches. Refactored into a
        dispatch table of resolver functions; each resolver receives
        ``(module, source_rel, nodes, is_relative)`` and returns a
        candidate path or ``None``.
        """
        language = imp.get("language", "")
        module = imp.get("module_name", "")
        is_relative = imp.get("is_relative", False)

        resolver = _IMPORT_RESOLVERS.get(language)
        if resolver is None:
            return None
        return resolver(module, source_rel, self._nodes, is_relative)

    def nodes(self) -> list[str]:
        """Return all nodes (relative file paths) in the graph."""
        return sorted(self._nodes)

    def all_nodes(self) -> frozenset[str]:
        """Return all nodes as an immutable frozenset.

        Unlike :meth:`nodes` (which returns a sorted list), this returns a
        frozenset for O(1) membership tests and immutable sharing.
        """
        return frozenset(self._nodes)

    def edges(self) -> list[tuple[str, str]]:
        """Return all directed edges (from_file, to_file) in the graph."""
        return sorted(self._edges)

    def all_edges(self) -> frozenset[tuple[str, str]]:
        """Return all directed edges as an immutable frozenset.

        Unlike :meth:`edges` (which returns a sorted list), this returns a
        frozenset for O(1) membership tests and immutable sharing.
        """
        return frozenset(self._edges)

    def all_deps(self) -> dict[str, set[str]]:
        """Return the full dependency map as a shallow copy.

        Returns ``{file: set_of_dependencies}`` for every node that has at
        least one outgoing edge.  The returned dict and its value sets are
        independent copies — mutating them does not affect the graph.
        """
        return {k: set(v) for k, v in self._deps.items()}

    def has_node(self, file_rel: str) -> bool:
        """Return True if *file_rel* is a node in the graph (O(1) set lookup)."""
        return file_rel in self._nodes

    def node_count(self) -> int:
        """Return the number of nodes in the graph."""
        return len(self._nodes)

    def edge_count(self) -> int:
        """Return the number of directed edges in the graph."""
        return len(self._edges)

    def is_excluded(self, path: Path) -> bool:
        """Public alias for :meth:`_is_excluded`.

        Return ``True`` if *path* should be excluded from analysis
        (hidden directories, __pycache__, node_modules, etc.).
        """
        return self._is_excluded(path)

    def iter_source_files(self, supported_exts: set[str]) -> list[Path]:
        """Public alias for :meth:`_iter_source_files`.

        Return source files under the project root whose suffix is in
        *supported_exts*, skipping excluded directories.
        """
        return self._iter_source_files(supported_exts)

    def dependencies_of(self, file_rel: str) -> list[str]:
        """Return files that the given file depends on."""
        return sorted(self._deps.get(file_rel, set()))

    def dependents_of(self, file_rel: str) -> list[str]:
        """Return files that depend on the given file."""
        return sorted(self._dependents.get(file_rel, set()))

    def symbol_in_degree(
        self,
        symbol: str,
        *,
        defining_file: str | None = None,
    ) -> SymbolFanIn:
        """Return how many project files import a symbol by name.

        Counts **distinct importer files**, not import edges — a file
        with two ``from X import Foo`` lines still counts as 1.

        ``defining_file`` (optional) narrows the count to importers whose
        resolved import target was that exact file. Use this when the
        symbol name is defined in multiple files (``ambiguous=True`` in
        the default response) and the caller needs the precise fan-in
        for one specific definition.

        Returns ``SymbolFanIn(symbol, 0, (), (), False)`` for unknown
        symbols rather than raising — same contract as ``dependents_of``
        for unknown files.
        """

        importer_set = self._symbol_importers.get(symbol, set())

        if defining_file is not None:
            importer_set = {
                importer
                for importer in importer_set
                if defining_file
                in self._symbol_importer_targets.get((symbol, importer), set())
            }

        defining_set = self._symbol_def_files.get(symbol, set())
        return SymbolFanIn(
            symbol=symbol,
            file_count=len(importer_set),
            importer_files=tuple(sorted(importer_set)),
            defining_files=tuple(sorted(defining_set)),
            ambiguous=len(defining_set) > 1,
        )

    def find_cycles(self) -> list[list[str]]:
        """Detect circular dependencies using DFS."""
        cycles: list[list[str]] = []
        visited: set[str] = set()
        recursion_stack: list[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            recursion_stack.append(node)

            for neighbor in self._deps.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in recursion_stack:
                    # Found a cycle
                    cycle_start = recursion_stack.index(neighbor)
                    cycle = recursion_stack[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            recursion_stack.pop()

        for node in self._nodes:
            if node not in visited:
                dfs(node)

        return cycles

    def to_dict(self) -> dict[str, Any]:
        """Serialize graph to dictionary format."""
        return {
            "project_root": str(self.project_root),
            "nodes": self.nodes(),
            "edges": [list(e) for e in self.edges()],
            "node_count": len(self._nodes),
            "edge_count": len(self._edges),
            # PR-0.2 additive: number of distinct symbol names with at
            # least one project-internal importer. Additive only;
            # existing keys unchanged.
            "symbol_index_size": len(self._symbol_importers),
        }


# ============================================================
# BlastRadius — Impact / blast radius analysis
# ============================================================


class BlastRadius:
    """
    Impact analysis using a DependencyGraph.

    Forward analysis: Given a file, find all files transitively affected
    by changes to it (files that depend on it, recursively).

    Reverse analysis: Given a file, find all files it depends on (transitively).

    Usage:
        graph = DependencyGraph("/path/to/project")
        br = BlastRadius(graph)
        result = br.analyze("src/main.py")
        print(result["forward_impact"])
    """

    def __init__(self, graph: DependencyGraph) -> None:
        self.graph = graph

    def forward(self, file_rel: str) -> set[str]:
        """
        Compute forward blast radius: all files transitively dependent on file_rel.

        Args:
            file_rel: Relative file path in the project

        Returns:
            Set of relative file paths affected by changes to file_rel
        """
        if not self.graph.has_node(file_rel):
            return set()

        impacted: set[str] = set()
        queue: deque[str] = deque([file_rel])

        while queue:
            current = queue.popleft()
            for dependent in self.graph.dependents_of(current):
                if dependent not in impacted and dependent != file_rel:
                    impacted.add(dependent)
                    queue.append(dependent)

        return impacted

    def reverse(self, file_rel: str) -> set[str]:
        """
        Compute reverse blast radius: all files file_rel transitively depends on.

        Args:
            file_rel: Relative file path in the project

        Returns:
            Set of relative file paths that file_rel depends on
        """
        if not self.graph.has_node(file_rel):
            return set()

        dependencies: set[str] = set()
        queue: deque[str] = deque([file_rel])

        while queue:
            current = queue.popleft()
            for dep in self.graph.dependencies_of(current):
                if dep not in dependencies and dep != file_rel:
                    dependencies.add(dep)
                    queue.append(dep)

        return dependencies

    def analyze(self, file_rel: str) -> dict[str, Any]:
        """
        Full blast radius analysis for a file.

        Returns:
            Dict with 'file', 'forward_impact', 'reverse_dependencies', and counts
        """
        forward_impact = sorted(self.forward(file_rel))
        reverse_deps = sorted(self.reverse(file_rel))

        return {
            "file": file_rel,
            "forward_impact": forward_impact,
            "forward_count": len(forward_impact),
            "reverse_dependencies": reverse_deps,
            "reverse_count": len(reverse_deps),
        }
