"""
Coupling Metrics Analyzer.

Quantifies module coupling intensity using fan-out (dependencies)
and fan-in (dependents) metrics from the dependency graph.

Risk classification based on Instability (I = fan_out / (fan_in + fan_out)):
  - STABLE: I < 0.3 (many dependents, few dependencies)
  - FLEXIBLE: 0.3 <= I <= 0.7 (balanced)
  - UNSTABLE: I > 0.7 (few dependents, many dependencies)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.utils import setup_logger

from .dependency_graph import DependencyGraph, DependencyGraphBuilder

logger = setup_logger(__name__)

RISK_STABLE = "STABLE"
RISK_FLEXIBLE = "FLEXIBLE"
RISK_UNSTABLE = "UNSTABLE"

INSTABILITY_STABLE = 0.3
INSTABILITY_UNSTABLE = 0.7


def _classify_risk(instability: float) -> str:
    if instability < INSTABILITY_STABLE:
        return RISK_STABLE
    if instability > INSTABILITY_UNSTABLE:
        return RISK_UNSTABLE
    return RISK_FLEXIBLE


@dataclass(frozen=True)
class FileCouplingMetrics:
    file_path: str
    fan_out: int
    fan_in: int
    instability: float
    risk: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "fan_out": self.fan_out,
            "fan_in": self.fan_in,
            "instability": round(self.instability, 3),
            "risk": self.risk,
        }


@dataclass(frozen=True)
class CouplingResult:
    project_root: str
    total_files: int
    total_edges: int
    avg_fan_out: float
    avg_fan_in: float
    most_coupled: tuple[FileCouplingMetrics, ...]
    most_critical: tuple[FileCouplingMetrics, ...]
    unstable_files: tuple[FileCouplingMetrics, ...]
    file_metrics: tuple[FileCouplingMetrics, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "total_files": self.total_files,
            "total_edges": self.total_edges,
            "avg_fan_out": round(self.avg_fan_out, 2),
            "avg_fan_in": round(self.avg_fan_in, 2),
            "most_coupled": [m.to_dict() for m in self.most_coupled],
            "most_critical": [m.to_dict() for m in self.most_critical],
            "unstable_count": len(self.unstable_files),
            "file_metrics": [m.to_dict() for m in self.file_metrics],
        }

    def get_high_risk(self) -> tuple[FileCouplingMetrics, ...]:
        return tuple(
            m for m in self.file_metrics if m.risk == RISK_UNSTABLE
        )


class CouplingMetricsAnalyzer:
    """Analyzes module coupling from dependency graph data."""

    def analyze_project(self, project_root: str | Path) -> CouplingResult:
        root = Path(project_root)
        if not root.is_dir():
            return CouplingResult(
                project_root=str(root),
                total_files=0,
                total_edges=0,
                avg_fan_out=0.0,
                avg_fan_in=0.0,
                most_coupled=(),
                most_critical=(),
                unstable_files=(),
                file_metrics=(),
            )

        builder = DependencyGraphBuilder(str(root))
        graph = builder.build()
        return self._compute_metrics(graph, str(root))

    def analyze_graph(
        self, graph: DependencyGraph, project_root: str
    ) -> CouplingResult:
        return self._compute_metrics(graph, project_root)

    def _compute_metrics(
        self, graph: DependencyGraph, project_root: str
    ) -> CouplingResult:
        fan_out_map: dict[str, int] = {}
        fan_in_map: dict[str, int] = {}

        for node in graph.nodes:
            fan_out_map[node] = 0
            fan_in_map[node] = 0

        for src, dst in graph.edges:
            fan_out_map[src] = fan_out_map.get(src, 0) + 1
            fan_in_map[dst] = fan_in_map.get(dst, 0) + 1

        metrics: list[FileCouplingMetrics] = []
        for node in sorted(graph.nodes):
            out = fan_out_map.get(node, 0)
            inp = fan_in_map.get(node, 0)
            total = out + inp
            instability = (out / total) if total > 0 else 0.5
            risk = _classify_risk(instability)
            metrics.append(FileCouplingMetrics(
                file_path=node,
                fan_out=out,
                fan_in=inp,
                instability=instability,
                risk=risk,
            ))

        total_files = len(metrics)
        total_edges = len(graph.edges)
        avg_out = (sum(m.fan_out for m in metrics) / total_files) if total_files else 0.0
        avg_in = (sum(m.fan_in for m in metrics) / total_files) if total_files else 0.0

        sorted_by_out = sorted(metrics, key=lambda m: m.fan_out, reverse=True)
        sorted_by_in = sorted(metrics, key=lambda m: m.fan_in, reverse=True)
        unstable = tuple(m for m in metrics if m.risk == RISK_UNSTABLE)

        return CouplingResult(
            project_root=project_root,
            total_files=total_files,
            total_edges=total_edges,
            avg_fan_out=avg_out,
            avg_fan_in=avg_in,
            most_coupled=tuple(sorted_by_out[:10]),
            most_critical=tuple(sorted_by_in[:10]),
            unstable_files=unstable,
            file_metrics=tuple(metrics),
        )
