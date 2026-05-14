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
    }
    ext = Path(file_path).suffix.lower()
    return ext_map.get(ext)


def _resolve_relative_import(module_path: str, current_file_rel: str) -> str | None:
    """
    Resolve a relative Python import ('.utils', '..pkg.sub') to a relative file path.

    Returns None if the import is not project-internal.
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
    module_file = module_rest.replace(".", "/") + ".py"

    resolved = target_dir / module_file
    return str(resolved)


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
        """Generate a cache key based on project directory metadata."""
        try:
            stat = os.stat(project_root)
            return f"{project_root}:{stat.st_mtime}"
        except OSError:
            return None

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
        supported_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".java"}

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
                resolved = _resolve_relative_import(module, source_rel)
                return resolved
            else:
                # Absolute import: e.g., "pkg.submodule" → pkg/submodule.py
                candidate: str = module.replace(".", "/") + ".py"
                if candidate in self._nodes:
                    return candidate
                # Also try matching without .py (e.g., __init__.py packages)
                init_candidate: str = module.replace(".", "/") + "/__init__.py"
                if init_candidate in self._nodes:
                    return init_candidate
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
