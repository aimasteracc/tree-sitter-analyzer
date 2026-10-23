"""Path, language and graph-lookup primitives shared by safe-to-edit helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ....languages.lang_extension_map import EXT_TO_LANG

_CERTIFIED_IMPORT_LANGUAGES = frozenset(
    {"python", "javascript", "typescript", "java", "c", "cpp"}
)

_TYPESCRIPT_SOURCE_SUBSTITUTIONS = {
    ".js": (".ts", ".tsx", ".d.ts", ".js"),
    ".jsx": (".tsx", ".d.ts", ".jsx"),
    ".mjs": (".mts", ".d.mts", ".mjs"),
    ".cjs": (".cts", ".d.cts", ".cjs"),
}


class FileDependencyView:
    """Small graph-like view for one file's immediate import surface."""

    def __init__(
        self,
        *,
        rel_path: str,
        dependencies: set[str],
        dependents: set[str],
        dependents_answer: Any | None = None,
    ) -> None:
        self._nodes = {rel_path, *dependencies, *dependents}
        self._deps = {rel_path: dependencies}
        self._dependents = {rel_path: dependents}
        #: The RFC-0025 L1 ``DependentsAnswer`` this view's dependents came
        #: from, or ``None`` for hand-built views. Carries how completely the
        #: set was established so the response can say so rather than
        #: presenting a fallback as the derived answer.
        self.dependents_answer = dependents_answer

    def has_node(self, file_rel: str) -> bool:
        """Return True if *file_rel* is a node in this view (O(1) set lookup)."""
        return file_rel in self._nodes

    def node_count(self) -> int:
        """Return the number of nodes in this view."""
        return len(self._nodes)

    def nodes(self) -> list[str]:
        """Return all nodes as a sorted list."""
        return sorted(self._nodes)

    def dependencies_of(self, file_rel: str) -> list[str]:
        return sorted(self._deps.get(file_rel, set()))

    def dependents_of(self, file_rel: str) -> list[str]:
        return sorted(self._dependents.get(file_rel, set()))


def to_relative(abs_path: str, project_root: str) -> str:
    """Return a path relative to the project root when possible."""
    try:
        return str(Path(abs_path).relative_to(project_root))
    except ValueError:
        return abs_path


def _normalize_relative_path(path: str) -> str:
    """Use snapshot separators without changing legal POSIX backslashes."""

    return path.replace("\\", "/") if os.sep == "\\" else path


def _target_language(rel_path: str) -> str:
    """Return the canonical indexed language for one relative path."""

    return EXT_TO_LANG.get(Path(rel_path).suffix.lower(), "unknown")


def _module_path_without_suffix(path: Path) -> Path:
    """Strip one source module suffix, including TypeScript's compound suffix."""

    for suffix in (".d.mts", ".d.cts", ".d.ts"):
        if path.name.endswith(suffix):
            return path.with_name(path.name[: -len(suffix)])
    return path.with_suffix("")


def _typescript_emitted_import_paths(path: Path) -> tuple[Path, ...]:
    """Map a TypeScript source path to runtime spellings importers may use."""

    for source_suffix, emitted_suffixes in (
        (".d.mts", (".mjs",)),
        (".d.cts", (".cjs",)),
        (".d.ts", (".js", ".jsx")),
        (".mts", (".mjs",)),
        (".cts", (".cjs",)),
        (".tsx", (".js", ".jsx")),
        (".ts", (".js",)),
    ):
        if path.name.endswith(source_suffix):
            stem = path.name[: -len(source_suffix)]
            return tuple(
                path.with_name(f"{stem}{emitted_suffix}")
                for emitted_suffix in emitted_suffixes
            )
    return ()


def safe_dependents(graph: Any, rel_path: str) -> list[str]:
    """Return files that depend on rel_path, tolerating stale graph data."""
    return _safe_graph_lookup(graph, rel_path, graph.dependents_of)


def safe_dependencies(graph: Any, rel_path: str) -> list[str]:
    """Return files rel_path depends on, tolerating stale graph data."""
    return _safe_graph_lookup(graph, rel_path, graph.dependencies_of)


def is_init_file(file_path: str) -> bool:
    """Return whether a path points at a package __init__.py file."""
    return Path(file_path).name == "__init__.py"


def _safe_graph_lookup(
    graph: Any,
    rel_path: str,
    lookup: Any,
) -> list[str]:
    """Look up graph edges directly or via suffix match."""
    try:
        node = _matching_node(graph, rel_path)
        return lookup(node) if node else []
    except Exception:  # nosec B110 - graph lookup failure returns no edges
        return []


def _matching_node(graph: Any, rel_path: str) -> str | None:
    """Find the graph node matching a relative path."""
    if graph.has_node(rel_path):
        return rel_path
    normalized = rel_path.replace("\\", "/")
    suffix = f"/{normalized}"
    return next((node for node in graph.nodes() if node.endswith(suffix)), None)
