#!/usr/bin/env python3
"""UML-oriented Mermaid exports built from cached project intelligence."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .call_path import CallPathFinder
from .class_hierarchy import ClassHierarchy
from .import_graph import ImportGraph
from .utils.test_detection import is_test_file

_EXTERNAL_BASES = frozenset(
    {
        "ABC",
        "Enum",
        "Exception",
        "Protocol",
        "RuntimeError",
        "ValueError",
        "object",
        "str",
    }
)

# P1-C (RFC-0015): path segments that identify test/fixture content.
# is_test_file() already covers these and more; we use it for filtering.
# This constant documents the intent rather than providing a second filter.

_TRUNCATION_NOTE = (
    "%% NOTE: diagram truncated — only the top N edges shown.\n"
    "%% Pass a higher max_edges value to see more, or use file_path / class_name to scope."
)


@dataclass(frozen=True)
class UMLEdge:
    source: str
    target: str
    label: str = ""
    weight: int = 1

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source": self.source,
            "target": self.target,
            "weight": self.weight,
        }
        if self.label:
            data["label"] = self.label
        return data


@dataclass(frozen=True)
class UMLDiagram:
    diagram_type: str
    mermaid_type: str
    mermaid: str
    nodes: list[str]
    edges: list[UMLEdge]
    truncated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "diagram_type": self.diagram_type,
            "mermaid_type": self.mermaid_type,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "truncated": self.truncated,
            "nodes": self.nodes,
            "edges": [edge.to_dict() for edge in self.edges],
            "mermaid": self.mermaid,
            "metadata": self.metadata,
        }


def _safe_id(name: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_]", "_", name)
    if not safe or safe[0].isdigit():
        safe = f"N_{safe}"
    return safe


def _escape_label(label: str) -> str:
    return label.replace('"', "'")


def _package_name(file_path: str, max_depth: int = 2) -> str:
    parts = [part for part in Path(file_path).parts if part and part != "."]
    if not parts:
        return "root"
    if len(parts) == 1:
        return "root"
    package_parts = parts[:-1][:max_depth]
    return ".".join(package_parts) if package_parts else "root"


def _component_name(file_path: str) -> str:
    parts = [part for part in Path(file_path).parts if part and part != "."]
    if not parts:
        return "root"
    if len(parts) == 1 and Path(parts[0]).suffix:
        return "root"
    if parts[0] == "tree_sitter_analyzer" and len(parts) > 1:
        if len(parts) == 2 and parts[1].endswith(".py"):
            return "tree_sitter_analyzer.root"
        return parts[1]
    return parts[0]


def _clamp_edges(
    edges: Iterable[UMLEdge], max_edges: int
) -> tuple[list[UMLEdge], bool]:
    unique: dict[tuple[str, str, str], UMLEdge] = {}
    for edge in edges:
        key = (edge.source, edge.target, edge.label)
        existing = unique.get(key)
        if existing is None:
            unique[key] = edge
        else:
            unique[key] = UMLEdge(
                source=edge.source,
                target=edge.target,
                label=edge.label,
                weight=existing.weight + edge.weight,
            )
    sorted_edges = sorted(
        unique.values(), key=lambda edge: (-edge.weight, edge.source, edge.target)
    )
    return sorted_edges[:max_edges], len(sorted_edges) > max_edges


def render_class_mermaid(
    nodes: Iterable[str],
    edges: Iterable[UMLEdge],
    truncated: bool = False,
) -> str:
    lines = ["classDiagram"]
    node_list = sorted(set(nodes))
    edge_list = sorted(edges, key=lambda edge: (edge.source, edge.target))
    if not node_list and not edge_list:
        lines.append("  class EmptyProject")
        return "\n".join(lines)
    for node in node_list:
        lines.append(f"  class {_safe_id(node)}")
    for edge in edge_list:
        lines.append(f"  {_safe_id(edge.source)} <|-- {_safe_id(edge.target)}")
    # P1-D: honest truncation note so consumers know the diagram is incomplete
    if truncated:
        lines.append(_TRUNCATION_NOTE)
    return "\n".join(lines)


def render_flowchart_mermaid(
    nodes: Iterable[str],
    edges: Iterable[UMLEdge],
    direction: str = "LR",
) -> str:
    lines = [f"flowchart {direction}"]
    node_list = sorted(set(nodes))
    edge_list = sorted(edges, key=lambda edge: (edge.source, edge.target, edge.label))
    if not node_list and not edge_list:
        lines.append('  empty["No edges found"]')
        return "\n".join(lines)
    for node in node_list:
        lines.append(f'  {_safe_id(node)}["{_escape_label(node)}"]')
    for edge in edge_list:
        if edge.label:
            lines.append(
                f"  {_safe_id(edge.source)} -->|{_escape_label(edge.label)}| "
                f"{_safe_id(edge.target)}"
            )
        else:
            lines.append(f"  {_safe_id(edge.source)} --> {_safe_id(edge.target)}")
    return "\n".join(lines)


def render_sequence_mermaid(paths: list[dict[str, Any]], max_hops: int) -> str:
    lines = ["sequenceDiagram"]
    if not paths:
        lines.append("  participant NoPath")
        lines.append("  Note over NoPath: No call path found")
        return "\n".join(lines)

    first_path = paths[0].get("hops", [])[:max_hops]
    participants: list[str] = []
    for hop in first_path:
        for key in ("caller", "callee"):
            name = hop.get(key, "")
            if name and name not in participants:
                participants.append(name)
    if not participants:
        lines.append("  participant EmptyPath")
        return "\n".join(lines)
    for name in participants:
        lines.append(f'  participant {_safe_id(name)} as "{_escape_label(name)}"')
    for hop in first_path:
        caller = hop.get("caller", "")
        callee = hop.get("callee", "")
        if caller and callee:
            lines.append(f"  {_safe_id(caller)}->>+{_safe_id(callee)}: call")
            lines.append(f"  {_safe_id(callee)}-->>-{_safe_id(caller)}: return")
    return "\n".join(lines)


def _file_matches(cls_file: str, filter_path: str | None) -> bool:
    """Return True when *cls_file* matches *filter_path*.

    Accepts both exact-match and suffix-match so callers can pass either
    a repo-relative path ("src/a.py") or a basename ("a.py").
    """
    if not cls_file or not filter_path:
        return False
    norm_cls = cls_file.replace("\\", "/").lstrip("/")
    norm_filter = filter_path.replace("\\", "/").lstrip("/")
    return norm_cls == norm_filter or norm_cls.endswith("/" + norm_filter)


def _is_neighbourhood(
    child: str,
    cls: dict[str, Any],
    center: str | None,
    all_classes: list[dict[str, Any]],
) -> bool:
    """Return True when *child* is in the neighbourhood of *center*.

    The neighbourhood is: center itself + direct parents of center + direct
    subclasses of center (classes that list center as a parent).
    """
    if center is None:
        return False
    if child == center:
        return True
    # child is a direct parent of center
    center_cls = next((c for c in all_classes if c.get("name") == center), None)
    if center_cls is not None:
        parents = [str(p).rsplit(".", 1)[-1] for p in (center_cls.get("parents") or [])]
        if child in parents:
            return True
    # child is a direct subclass of center (center is in child's parents)
    child_parents = [str(p).rsplit(".", 1)[-1] for p in (cls.get("parents") or [])]
    return center in child_parents


class UMLExporter:
    """Build Mermaid UML-style diagrams from existing CodeGraph indexes."""

    def __init__(self, project_root: str, cache: Any | None = None) -> None:
        self.project_root = project_root
        self._cache = cache

    def _open_cache(self) -> tuple[Any, bool]:
        if self._cache is not None:
            return self._cache, False
        from .ast_cache import ASTCache

        return ASTCache(self.project_root), True

    def class_diagram(
        self,
        max_edges: int = 80,
        include_external_bases: bool = True,
        *,
        file_path: str | None = None,
        class_name: str | None = None,
        include_tests: bool = False,
    ) -> UMLDiagram:
        """Build a class inheritance diagram.

        Scoping (P1-A, RFC-0015): applied in priority order, first match wins.
        1. class_name given — neighbourhood subgraph (named class + direct bases
           + direct subclasses).
        2. file_path given — classes defined in that file plus their direct
           bases (so inheritance arrows remain correct).
        3. Neither given — whole-project view, subject to include_tests.

        include_tests=False (P1-C) strips classes whose source file is a
        test/fixture path (detected via is_test_file()).
        """
        cache, should_close = self._open_cache()
        try:
            hierarchy = ClassHierarchy(cache)
            hierarchy.build()
            classes = hierarchy.all_classes()
        finally:
            if should_close:
                cache.close()

        # P1-C: strip test-corpus classes from whole-project view by default
        if not include_tests:
            classes = [c for c in classes if not is_test_file(c.get("file"))]

        internal_names = {c.get("name", "") for c in classes if c.get("name")}
        raw_edges: list[UMLEdge] = []
        nodes: set[str] = set()

        # Determine scope label for metadata
        if class_name is not None:
            scope = "class_neighbourhood"
        elif file_path is not None:
            scope = "file"
        else:
            scope = "whole_project"

        # P2-1: an unknown class_name must be distinguishable from a known
        # class with an empty neighbourhood — agents can't tell them apart
        # from an empty diagram alone.
        not_found = class_name is not None and class_name not in internal_names

        for cls in classes:
            child = cls.get("name", "")
            if not child:
                continue

            # P1-A scoping: apply file_path / class_name filter
            if scope == "file":
                cls_file = cls.get("file", "")
                if not _file_matches(cls_file, file_path):
                    continue
            elif scope == "class_neighbourhood":
                # Include: the named class itself, its direct parents, and
                # classes that list it as a direct parent (subclasses one hop)
                if not _is_neighbourhood(child, cls, class_name, classes):
                    continue

            nodes.add(child)
            for parent_text in cls.get("parents") or []:
                parent = str(parent_text).rsplit(".", 1)[-1]
                if parent in internal_names or (
                    include_external_bases and parent in _EXTERNAL_BASES
                ):
                    nodes.add(parent)
                    raw_edges.append(UMLEdge(parent, child, "inherits"))

        edges, truncated = _clamp_edges(raw_edges, max_edges)
        rendered_nodes = sorted(
            {n for edge in edges for n in (edge.source, edge.target)}
        )
        if not rendered_nodes:
            rendered_nodes = sorted(nodes)[:max_edges]
        return UMLDiagram(
            diagram_type="class",
            mermaid_type="classDiagram",
            mermaid=render_class_mermaid(rendered_nodes, edges, truncated=truncated),
            nodes=rendered_nodes,
            edges=edges,
            truncated=truncated,
            metadata={
                "source": "class_hierarchy",
                "scope": scope,
                **({"not_found": True} if not_found else {}),
            },
        )

    def package_diagram(
        self, max_edges: int = 200, package_depth: int = 2
    ) -> UMLDiagram:
        graph = ImportGraph(self.project_root)
        result = graph.build()
        edge_weights: dict[tuple[str, str], int] = defaultdict(int)
        nodes: set[str] = set()
        for edge in result.edges:
            source = _package_name(edge.source_file, package_depth)
            target = _package_name(edge.target_file, package_depth)
            if source == target:
                continue
            edge_weights[(source, target)] += 1
            nodes.update((source, target))
        edges, truncated = _clamp_edges(
            (
                UMLEdge(source, target, str(weight), weight)
                for (source, target), weight in edge_weights.items()
            ),
            max_edges,
        )
        return UMLDiagram(
            diagram_type="package",
            mermaid_type="flowchart",
            mermaid=render_flowchart_mermaid(nodes, edges, "LR"),
            nodes=sorted(nodes),
            edges=edges,
            truncated=truncated,
            metadata={"source": "import_graph", "package_depth": package_depth},
        )

    def component_diagram(self, max_edges: int = 120) -> UMLDiagram:
        graph = ImportGraph(self.project_root)
        result = graph.build()
        edge_weights: dict[tuple[str, str], int] = defaultdict(int)
        nodes: set[str] = set()
        for edge in result.edges:
            source = _component_name(edge.source_file)
            target = _component_name(edge.target_file)
            if source == target:
                continue
            edge_weights[(source, target)] += 1
            nodes.update((source, target))
        edges, truncated = _clamp_edges(
            (
                UMLEdge(source, target, str(weight), weight)
                for (source, target), weight in edge_weights.items()
            ),
            max_edges,
        )
        return UMLDiagram(
            diagram_type="component",
            mermaid_type="flowchart",
            mermaid=render_flowchart_mermaid(nodes, edges, "LR"),
            nodes=sorted(nodes),
            edges=edges,
            truncated=truncated,
            metadata={"source": "import_graph", "group_by": "top_level_component"},
        )

    def sequence_diagram(
        self,
        source: str,
        target: str,
        max_depth: int = 8,
        max_paths: int = 3,
        max_hops: int = 12,
    ) -> UMLDiagram:
        finder = CallPathFinder(self.project_root, self._cache)
        result = finder.find_path(
            source_function=source,
            target_function=target,
            max_depth=max_depth,
            max_paths=max_paths,
        )
        result_dict = result.to_dict()
        paths = result_dict.get("paths", [])
        first_hops = paths[0].get("hops", []) if paths else []
        nodes = sorted(
            {
                hop.get(key, "")
                for hop in first_hops[:max_hops]
                for key in ("caller", "callee")
                if hop.get(key)
            }
        )
        edges = [
            UMLEdge(hop.get("caller", ""), hop.get("callee", ""), "call")
            for hop in first_hops[:max_hops]
            if hop.get("caller") and hop.get("callee")
        ]
        # P1-E (RFC-0015): observability label — "call_path+synapse_resolved"
        # when at least one hop has callee_file populated (synapse resolution
        # contributed to BFS traversal); "call_path" otherwise.
        has_resolved = any(
            hop.get("callee_file") for path in paths for hop in path.get("hops", [])
        )
        source_label = "call_path+synapse_resolved" if has_resolved else "call_path"
        return UMLDiagram(
            diagram_type="sequence",
            mermaid_type="sequenceDiagram",
            mermaid=render_sequence_mermaid(paths, max_hops),
            nodes=nodes,
            edges=edges,
            truncated=result.truncated or len(first_hops) > max_hops,
            metadata={
                "source": source_label,
                "analysis_kind": "static_approximation",
                "path_count": len(paths),
            },
        )
