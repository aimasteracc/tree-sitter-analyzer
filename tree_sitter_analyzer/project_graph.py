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

# Standard library / well-known external module prefixes
_STDLIB_TOP_LEVEL = {
    "os",
    "sys",
    "re",
    "json",
    "math",
    "time",
    "datetime",
    "collections",
    "itertools",
    "functools",
    "typing",
    "io",
    "pathlib",
    "hashlib",
    "random",
    "string",
    "textwrap",
    "logging",
    "argparse",
    "subprocess",
    "shutil",
    "tempfile",
    "unittest",
    "pytest",
    "warnings",
    "traceback",
    "abc",
    "base64",
    "csv",
    "enum",
    "glob",
    "gzip",
    "http",
    "inspect",
    "struct",
    "threading",
    "multiprocessing",
    "asyncio",
    "concurrent",
    "socket",
    "ssl",
    "email",
    "xml",
    "html",
    "urllib",
    "sqlite3",
    "copy",
    "pprint",
    "statistics",
    "dataclasses",
    "contextlib",
    "importlib",
    "types",
    "typing_extensions",
    "decimal",
    "fractions",
    "array",
    "binascii",
    "bisect",
    "calendar",
    "cmath",
    "codecs",
}
_JS_BUILTIN = {
    "fs",
    "path",
    "os",
    "http",
    "https",
    "url",
    "crypto",
    "stream",
    "events",
    "util",
    "assert",
    "buffer",
    "child_process",
    "cluster",
    "dgram",
    "dns",
    "domain",
    "net",
    "readline",
    "repl",
    "tls",
    "string_decoder",
    "timers",
    "tty",
    "v8",
    "vm",
    "zlib",
}


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
    _walk_imports(tree.root_node, source, language, imports)

    return imports


def _walk_imports(
    node: Any, source: str, language: str, imports: list[dict[str, Any]]
) -> None:
    """Walk the AST to collect import statements."""
    try:
        if language in ("python",):
            _extract_python_imports(node, source, imports)
        elif language in ("javascript", "typescript"):
            _extract_js_imports(node, source, imports)
    except Exception:  # nosec B110
        pass

    # Recurse into children
    if hasattr(node, "children"):
        for child in node.children:
            _walk_imports(child, source, language, imports)


def _extract_python_imports(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Extract Python import statements."""
    node_type = getattr(node, "type", None)

    if node_type == "import_statement":
        _extract_python_import_simple(node, source, imports)
    elif node_type == "import_from_statement":
        _extract_python_import_from(node, source, imports)


def _extract_python_import_simple(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Handle: import os, sys"""
    for child in node.children:
        if getattr(child, "type", None) != "dotted_name":
            continue
        name = _node_text(child, source)
        if not name or name.split(".")[0] in _STDLIB_TOP_LEVEL:
            continue
        imports.append(
            {
                "module_name": name,
                "resolved_path": name.replace(".", "/") + ".py",
                "names": [name],
                "is_relative": False,
                "language": "python",
            }
        )


def _extract_python_import_from(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Handle: from [.][.]module import name1, name2"""
    module_name = ""
    dots_prefix = ""
    imported_names: list[str] = []

    for child in node.children:
        ct = getattr(child, "type", None)

        if ct == "relative_import":
            for sub in child.children:
                st = getattr(sub, "type", None)
                if st == "import_prefix":
                    dots_prefix = _node_text(sub, source)
                elif st == "dotted_name":
                    module_name = _node_text(sub, source)

        elif ct == "dotted_name":
            if not module_name and not dots_prefix:
                module_name = _node_text(child, source)
            else:
                imported_names.append(_node_text(child, source))

        elif ct == "aliased_import":
            imported_names.extend(_extract_import_names(child, source))

    if not module_name:
        return

    full_module = dots_prefix + module_name
    if not dots_prefix and module_name.split(".")[0] in _STDLIB_TOP_LEVEL:
        return

    imports.append(
        {
            "module_name": full_module,
            "resolved_path": full_module.replace(".", "/") + ".py"
            if full_module
            else "",
            "names": imported_names,
            "is_relative": bool(dots_prefix),
            "language": "python",
        }
    )


def _extract_js_imports(node: Any, source: str, imports: list[dict[str, Any]]) -> None:
    """Extract JS/TS import/require statements."""
    node_type = getattr(node, "type", None)

    if node_type == "import_statement":
        # import { foo } from './bar'
        module_path = None
        for child in node.children:
            if getattr(child, "type", None) == "string":
                raw = _node_text(child, source).strip("'\"")
                if not raw.startswith(".") and not raw.startswith("/"):
                    # Could be a package import like 'lodash'
                    if raw in _JS_BUILTIN:
                        continue
                module_path = raw

        if module_path:
            imports.append(
                {
                    "module_name": module_path,
                    "resolved_path": module_path,
                    "names": [],
                    "is_relative": module_path.startswith("."),
                    "language": "javascript",
                }
            )

    elif node_type == "call_expression":
        # require('./foo') or require('fs')
        func = node.child_by_field_name("function")
        if func and _node_text(func, source) == "require":
            args_node = node.child_by_field_name("arguments")
            if args_node and hasattr(args_node, "children"):
                for child in args_node.children:
                    if getattr(child, "type", None) == "string":
                        raw = _node_text(child, source).strip("'\"")

                        # Check if builtin
                        if raw in _JS_BUILTIN:
                            continue

                        imports.append(
                            {
                                "module_name": raw,
                                "resolved_path": raw,
                                "names": [],
                                "is_relative": raw.startswith("."),
                                "language": "javascript",
                            }
                        )


def _extract_import_names(names_node: Any, source: str) -> list[str]:
    """Extract individual names from an import_list or aliased_import node."""
    names = []
    if hasattr(names_node, "children"):
        for child in names_node.children:
            ct = getattr(child, "type", None)
            if ct == "dotted_name" or ct == "identifier":
                text = _node_text(child, source)
                if text and text != ",":
                    names.append(text)
            elif ct == "aliased_import":
                # Handle 'foo as bar'
                for sub in child.children:
                    st = getattr(sub, "type", None)
                    if st in ("dotted_name", "identifier"):
                        names.append(_node_text(sub, source))
    return names


def _node_text(node: Any, source: str) -> str:
    """Safely extract text from a Tree-sitter node."""
    try:
        start = node.start_byte
        end = node.end_byte
        if (
            start is not None
            and end is not None
            and start < end <= len(source.encode("utf-8", errors="replace"))
        ):
            return source.encode("utf-8", errors="replace")[start:end].decode(
                "utf-8", errors="replace"
            )
        return ""
    except Exception:
        return ""


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
