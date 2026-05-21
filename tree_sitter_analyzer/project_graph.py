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
from pathlib import Path
from typing import Any

from .core.parser import Parser, ParseResult
from .import_extractors import (
    walk_imports,
)


def _language_from_ext(file_path: str) -> str | None:
    """Guess language from file extension."""
    ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".c": "c",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".hxx": "cpp",
    }
    ext = Path(file_path).suffix.lower()
    return ext_map.get(ext)


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
    return str(resolved)


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
    return str(candidate)


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

    return str(target_dir / "__init__.py")


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
        # Local import to avoid a hard dependency cycle (mcp.tools imports
        # project_graph, so we can't import it at module level).
        from .mcp.tools._graph_cache_fingerprint import compute_graph_fingerprint

        fp = compute_graph_fingerprint(project_root)
        return f"{project_root}:{fp.file_count}:{fp.max_mtime_ns}"

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

    def _is_excluded(self, path: Path) -> bool:
        """Check if a path is inside an excluded directory."""
        return any(part in self._EXCLUDE_DIRS for part in path.parts)

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
        all_files: list[Path] = []
        for ext in supported_exts:
            for f in self.project_root.rglob(f"*{ext}"):
                if not self._is_excluded(f):
                    all_files.append(f)

        # Build relative path mapping
        rel_to_abs: dict[str, str] = {}
        for f in all_files:
            try:
                rel = str(f.relative_to(self.project_root))
                rel_to_abs[rel] = str(f)
                self._nodes.add(rel)
            except ValueError:
                continue

        # Parse each file and extract imports
        for rel_path, abs_path in rel_to_abs.items():
            language = _language_from_ext(rel_path)
            if language is None:
                continue

            raw_imports = extract_imports_from_file(abs_path, language)
            for imp in raw_imports:
                resolved = self._resolve_to_project_file(imp, rel_path, rel_to_abs)
                if resolved and resolved in self._nodes:
                    self._edges.add((rel_path, resolved))
                    self._deps[rel_path].add(resolved)
                    self._dependents[resolved].add(rel_path)

    def _resolve_to_project_file(
        self,
        imp: dict[str, Any],
        source_rel: str,
        rel_to_abs: dict[str, str],
    ) -> str | None:
        """Resolve an import dict to a project-relative file path."""
        language = imp.get("language", "")
        module = imp.get("module_name", "")
        is_relative = imp.get("is_relative", False)

        if language == "python":
            if is_relative:
                # Match Python's actual import semantics: a package
                # (``foo/bar/__init__.py``) takes precedence over a
                # sibling file module (``foo/bar.py``) when both
                # exist. In practice projects use one or the other, so
                # the choice rarely matters — but we pin the package
                # form to match the interpreter.
                init_candidate = _relative_init_candidate(module, source_rel)
                if init_candidate and init_candidate in self._nodes:
                    return init_candidate
                file_candidate = _resolve_relative_import(module, source_rel)
                if file_candidate and file_candidate in self._nodes:
                    return file_candidate
                # ``from . import name`` / ``from .. import name`` where
                # ``name`` is neither a file-module nor a sub-package:
                # Python falls back to the attribute defined in the
                # ancestor package's ``__init__.py``. Emit the edge to
                # that ``__init__.py`` so e.g. ``from . import
                # __version__`` is not silently dropped.
                anchor_init = _relative_anchor_init(module, source_rel)
                if anchor_init and anchor_init in self._nodes:
                    return anchor_init
                return file_candidate  # legacy: return file form even if absent
            else:
                # Absolute import: e.g., "pkg.submodule" → pkg/submodule.py
                # Package-module form (``pkg/submodule/__init__.py``)
                # takes precedence over file-module form (``pkg/submodule.py``)
                # when both exist — matches Python's import semantics.
                init_candidate_abs: str = module.replace(".", "/") + "/__init__.py"
                if init_candidate_abs in self._nodes:
                    return init_candidate_abs
                candidate: str = module.replace(".", "/") + ".py"
                if candidate in self._nodes:
                    return candidate
                return None

        elif language in ("javascript", "typescript"):
            if is_relative:
                # './src/utils' → src/utils.js or src/utils/index.js
                source_dir = Path(source_rel).parent
                candidate_raw = str(source_dir / module)
                # Try common extensions
                for ext in (".js", ".ts", ".jsx", ".tsx", "/index.js", "/index.ts"):
                    candidate = candidate_raw + ext
                    if candidate in self._nodes:
                        return candidate
                # Also try without extension
                if candidate_raw in self._nodes:
                    return candidate_raw
            return None

        elif language == "go":
            if not is_relative:
                return None
            source_dir = Path(source_rel).parent
            candidate_raw = str(source_dir / module)
            if candidate_raw in self._nodes:
                return candidate_raw
            for ext in (".go", "/index.go"):
                candidate = candidate_raw + ext
                if candidate in self._nodes:
                    return candidate
            return None

        elif language == "rust":
            if not is_relative:
                return None
            path_parts = (
                module.replace("crate::", "")
                .replace("super::", "")
                .replace("self::", "")
            )
            path = path_parts.replace("::", "/")
            source_dir = Path(source_rel).parent
            candidate = str(source_dir / path)
            if candidate in self._nodes:
                return candidate
            for ext in (".rs", "/mod.rs", "/lib.rs"):
                candidate_with_ext = candidate + ext
                if candidate_with_ext in self._nodes:
                    return candidate_with_ext
            return None

        elif language in ("c", "cpp"):
            source_dir = Path(source_rel).parent
            candidate = str(source_dir / module)
            if candidate in self._nodes:
                return candidate
            return None

        elif language == "java":
            candidate = module.replace(".", "/") + ".java"
            if candidate in self._nodes:
                return candidate
            return None

        return None

    def nodes(self) -> list[str]:
        """Return all nodes (relative file paths) in the graph."""
        return sorted(self._nodes)

    def edges(self) -> list[tuple[str, str]]:
        """Return all directed edges (from_file, to_file) in the graph."""
        return sorted(self._edges)

    def dependencies_of(self, file_rel: str) -> list[str]:
        """Return files that the given file depends on."""
        return sorted(self._deps.get(file_rel, set()))

    def dependents_of(self, file_rel: str) -> list[str]:
        """Return files that depend on the given file."""
        return sorted(self._dependents.get(file_rel, set()))

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
        if file_rel not in self.graph._nodes:
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
        if file_rel not in self.graph._nodes:
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
