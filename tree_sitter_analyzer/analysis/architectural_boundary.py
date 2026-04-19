"""
Architectural Boundary Analyzer.

Detects layered architecture violations by analyzing import relationships.
Maps directory/package names to architectural layers and flags
cross-boundary imports that skip intermediate layers.

Layer hierarchy (higher number = deeper layer):
  0: UI / Controller / Handler / Endpoint / Route / View
  1: Service / Business / Logic / Application / UseCase
  2: Repository / DAO / Data / Store / Persistence / Model / Entity

Violation types:
  - skip_layer: higher layer imports from 2+ levels deeper (skips middle)
  - wrong_direction: deeper layer imports from higher layer
  - circular: two files in different layers import each other
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.utils import setup_logger

from .dependency_graph import DependencyGraph, DependencyGraphBuilder

logger = setup_logger(__name__)

VIOLATION_SKIP_LAYER = "skip_layer"
VIOLATION_WRONG_DIRECTION = "wrong_direction"
VIOLATION_CIRCULAR = "circular"

LAYER_UI = 0
LAYER_SERVICE = 1
LAYER_REPOSITORY = 2

LAYER_NAMES: dict[int, str] = {
    LAYER_UI: "UI/Controller",
    LAYER_SERVICE: "Service/Business",
    LAYER_REPOSITORY: "Repository/DAO",
}

LAYER_PATTERNS: dict[int, list[re.Pattern[str]]] = {
    LAYER_UI: [
        re.compile(r"(?:^|[/\\])(?:controller|controllers|handler|handlers|endpoint|endpoints|route|routes|view|views|api|web|ui)(?:[/\\]|$)", re.IGNORECASE),
    ],
    LAYER_SERVICE: [
        re.compile(r"(?:^|[/\\])(?:service|services|business|logic|application|usecase|usecases|use_case|use_cases|domain)(?:[/\\]|$)", re.IGNORECASE),
    ],
    LAYER_REPOSITORY: [
        re.compile(r"(?:^|[/\\])(?:repository|repositories|dao|daos|data|store|stores|persistence|model|models|entity|entities|db|database|infra|infrastructure)(?:[/\\]|$)", re.IGNORECASE),
    ],
}

def _classify_layer(file_path: str) -> int | None:
    parts = file_path.replace("\\", "/")
    for layer, patterns in LAYER_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(parts):
                return layer
    return None

@dataclass(frozen=True)
class BoundaryViolation:
    source_file: str
    target_file: str
    source_layer: int
    target_layer: int
    violation_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "target_file": self.target_file,
            "source_layer": LAYER_NAMES.get(self.source_layer, f"Layer {self.source_layer}"),
            "target_layer": LAYER_NAMES.get(self.target_layer, f"Layer {self.target_layer}"),
            "violation_type": self.violation_type,
            "description": _describe_violation(self),
        }

def _describe_violation(v: BoundaryViolation) -> str:
    src_name = LAYER_NAMES.get(v.source_layer, f"Layer {v.source_layer}")
    tgt_name = LAYER_NAMES.get(v.target_layer, f"Layer {v.target_layer}")
    if v.violation_type == VIOLATION_SKIP_LAYER:
        return f"{src_name} layer imports from {tgt_name} layer (skips middle layer)"
    if v.violation_type == VIOLATION_WRONG_DIRECTION:
        return f"{tgt_name} layer imports from {src_name} layer (wrong direction)"
    if v.violation_type == VIOLATION_CIRCULAR:
        return f"Circular dependency between {src_name} and {tgt_name} layers"
    return f"Unknown violation: {v.violation_type}"

@dataclass(frozen=True)
class LayerSummary:
    layer: int
    layer_name: str
    file_count: int
    violation_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "layer_name": self.layer_name,
            "file_count": self.file_count,
            "violation_count": self.violation_count,
        }

@dataclass(frozen=True)
class BoundaryResult:
    project_root: str
    total_files: int
    classified_files: int
    violations: tuple[BoundaryViolation, ...]
    circular_dependencies: tuple[BoundaryViolation, ...]
    compliance_score: float
    layer_summary: tuple[LayerSummary, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "total_files": self.total_files,
            "classified_files": self.classified_files,
            "compliance_score": round(self.compliance_score, 3),
            "violation_count": len(self.violations),
            "circular_count": len(self.circular_dependencies),
            "violations": [v.to_dict() for v in self.violations],
            "circular_dependencies": [v.to_dict() for v in self.circular_dependencies],
            "layer_summary": [ls.to_dict() for ls in self.layer_summary],
        }

class ArchitecturalBoundaryAnalyzer:
    """Analyzes layered architecture compliance from dependency data."""

    def analyze_project(self, project_root: str | Path) -> BoundaryResult:
        root = Path(project_root)
        if not root.is_dir():
            return BoundaryResult(
                project_root=str(root),
                total_files=0,
                classified_files=0,
                violations=(),
                circular_dependencies=(),
                compliance_score=1.0,
                layer_summary=(),
            )

        builder = DependencyGraphBuilder(str(root))
        graph = builder.build()
        return self._compute_boundary(graph, str(root))

    def analyze_graph(
        self, graph: DependencyGraph, project_root: str
    ) -> BoundaryResult:
        return self._compute_boundary(graph, project_root)

    def _compute_boundary(
        self, graph: DependencyGraph, project_root: str
    ) -> BoundaryResult:
        layer_map: dict[str, int] = {}
        for node in graph.nodes:
            layer = _classify_layer(node)
            if layer is not None:
                layer_map[node] = layer

        classified = len(layer_map)
        total = len(graph.nodes)

        violations: list[BoundaryViolation] = []
        edge_pairs: set[tuple[str, str]] = set()

        for src, dst in graph.edges:
            src_layer = layer_map.get(src)
            dst_layer = layer_map.get(dst)
            if src_layer is None or dst_layer is None:
                continue
            if src_layer == dst_layer:
                continue

            edge_pairs.add((src, dst))

            if dst_layer > src_layer:
                layer_distance = dst_layer - src_layer
                if layer_distance >= 2:
                    violations.append(BoundaryViolation(
                        source_file=src,
                        target_file=dst,
                        source_layer=src_layer,
                        target_layer=dst_layer,
                        violation_type=VIOLATION_SKIP_LAYER,
                    ))
            else:
                violations.append(BoundaryViolation(
                    source_file=src,
                    target_file=dst,
                    source_layer=src_layer,
                    target_layer=dst_layer,
                    violation_type=VIOLATION_WRONG_DIRECTION,
                ))

        circular: list[BoundaryViolation] = []
        seen_circular: set[frozenset[str]] = set()
        for src, dst in graph.edges:
            if (dst, src) in edge_pairs:
                src_layer = layer_map.get(src)
                dst_layer = layer_map.get(dst)
                if src_layer is not None and dst_layer is not None and src_layer != dst_layer:
                    pair = frozenset((src, dst))
                    if pair not in seen_circular:
                        seen_circular.add(pair)
                        circular.append(BoundaryViolation(
                            source_file=src,
                            target_file=dst,
                            source_layer=src_layer,
                            target_layer=dst_layer,
                            violation_type=VIOLATION_CIRCULAR,
                        ))

        total_cross_layer = len(violations) + len(circular)
        total_classified_edges = sum(
            1 for src, dst in graph.edges
            if src in layer_map and dst in layer_map and layer_map[src] != layer_map[dst]
        )
        compliance = (
            1.0 - (total_cross_layer / total_classified_edges)
            if total_classified_edges > 0
            else 1.0
        )

        layer_counts: dict[int, int] = {}
        layer_viol_counts: dict[int, int] = {}
        for _node, layer in layer_map.items():
            layer_counts[layer] = layer_counts.get(layer, 0) + 1
        for v in violations:
            layer_viol_counts[v.source_layer] = layer_viol_counts.get(v.source_layer, 0) + 1

        summary = tuple(
            LayerSummary(
                layer=layer,
                layer_name=LAYER_NAMES.get(layer, f"Layer {layer}"),
                file_count=layer_counts.get(layer, 0),
                violation_count=layer_viol_counts.get(layer, 0),
            )
            for layer in sorted(LAYER_NAMES)
            if layer_counts.get(layer, 0) > 0
        )

        return BoundaryResult(
            project_root=project_root,
            total_files=total,
            classified_files=classified,
            violations=tuple(violations),
            circular_dependencies=tuple(circular),
            compliance_score=max(0.0, compliance),
            layer_summary=summary,
        )
