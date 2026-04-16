"""
Graph service for dependency analysis and health scoring.

Elevates the edge extractor output into a persisted, queryable graph
and provides blast radius (transitive closure) computation.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter_analyzer.analysis.health_score import FileHealthScore, HealthScorer
from tree_sitter_analyzer.mcp.utils.edge_extractors import get_extractor
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)


@dataclass(frozen=True)
class BlastRadius:
    """Transitive closure result for a node."""

    source: str
    dependents: frozenset[str]
    depth_map: dict[str, int]


@dataclass
class ProjectGraph:
    """Queryable directed graph of project dependencies."""

    edges: list[tuple[str, str]]
    _adjacency: dict[str, list[str]] = field(default_factory=dict, repr=False, init=False)
    _reverse: dict[str, list[str]] = field(default_factory=dict, repr=False, init=False)

    def __post_init__(self) -> None:
        for src, dst in self.edges:
            self._adjacency.setdefault(src, []).append(dst)
            self._reverse.setdefault(dst, []).append(src)

    def direct_dependents(self, node: str) -> list[str]:
        """Files that directly depend on the given node (reverse edges)."""
        return list(self._reverse.get(node, []))

    def direct_dependencies(self, node: str) -> list[str]:
        """Files that the given node directly depends on (forward edges)."""
        return list(self._adjacency.get(node, []))

    def blast_radius(self, node: str, *, max_depth: int = 10) -> BlastRadius:
        """Compute transitive closure of all dependents (BFS)."""
        visited: dict[str, int] = {node: 0}
        queue: deque[str] = deque([node])

        while queue:
            current = queue.popleft()
            current_depth = visited[current]
            if current_depth >= max_depth:
                continue
            for dep in self._reverse.get(current, []):
                if dep not in visited:
                    visited[dep] = current_depth + 1
                    queue.append(dep)

        dependents = frozenset(visited.keys()) - {node}
        depth_map = {k: v for k, v in visited.items() if k != node}
        return BlastRadius(source=node, dependents=dependents, depth_map=depth_map)

    def nodes(self) -> set[str]:
        """All unique nodes in the graph."""
        all_nodes: set[str] = set()
        for src, dst in self.edges:
            all_nodes.add(src)
            all_nodes.add(dst)
        return all_nodes

    def edge_weights(self) -> dict[tuple[str, str], int]:
        """Compute edge weights based on occurrence frequency."""
        weights: dict[tuple[str, str], int] = {}
        for src, dst in self.edges:
            key = (src, dst)
            weights[key] = weights.get(key, 0) + 1
        return weights

    def hub_score(self) -> dict[str, int]:
        """Rank nodes by (in-degree + out-degree) as a hub centrality measure."""
        scores: dict[str, int] = {}
        for src, dst in self.edges:
            scores[src] = scores.get(src, 0) + 1
            scores[dst] = scores.get(dst, 0) + 1
        return dict(sorted(scores.items(), key=lambda x: x[1], reverse=True))


def build_graph_from_files(
    files: list[str],
    project_root: str,
) -> ProjectGraph:
    """Build a ProjectGraph from a list of file paths."""
    edges: list[tuple[str, str]] = []
    root_path = Path(project_root)

    for file_path in files:
        path = Path(file_path)
        extractor = get_extractor(path.suffix)
        if extractor is None:
            continue

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        src_name = str(path.relative_to(root_path)) if path.is_relative_to(root_path) else path.name
        file_edges = extractor.extract(content, src_name, project_root)
        edges.extend(file_edges)

    return ProjectGraph(edges=edges)


def score_project_health(
    project_root: str,
    *,
    file_paths: list[str] | None = None,
) -> list[FileHealthScore]:
    """Score project files using HealthScorer."""
    scorer = HealthScorer(project_root)
    if file_paths:
        return [scorer.score_file(fp) for fp in file_paths]
    return scorer.score_all()
