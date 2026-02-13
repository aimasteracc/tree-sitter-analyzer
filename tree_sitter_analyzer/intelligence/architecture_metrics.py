#!/usr/bin/env python3
"""Architecture metrics for Code Intelligence Graph."""
from __future__ import annotations
from typing import Any
from .models import (
    ArchitectureReport,
    DependencyCycle,
    GodClassInfo,
    LayerViolation,
    ModuleMetrics,
)
from .dependency_graph import DependencyGraphBuilder
from .symbol_index import SymbolIndex
from .cycle_detector import CycleDetector
import os


class ArchitectureMetrics:
    """Computes architecture health metrics."""

    def __init__(self, dep_graph: DependencyGraphBuilder, symbol_index: SymbolIndex) -> None:
        self._dep_graph = dep_graph
        self._symbol_index = symbol_index
        self._cycle_detector = CycleDetector()

    def compute_report(
        self,
        path: str,
        checks: list[str] | None = None,
        layer_rules: dict[str, dict[str, list[str]]] | None = None,
        god_class_threshold: int = 20,
    ) -> ArchitectureReport:
        if checks is None:
            checks = ["coupling_metrics", "circular_dependencies", "layer_violations", "god_classes", "dead_code"]

        report = ArchitectureReport(path=path)

        if "coupling_metrics" in checks:
            report.module_metrics = self._compute_coupling()
            report.coupling_matrix = self._compute_coupling_matrix()

        if "circular_dependencies" in checks:
            report.cycles = self._detect_cycles()

        if "layer_violations" in checks and layer_rules:
            report.layer_violations = self._check_layer_violations(layer_rules)

        if "god_classes" in checks:
            report.god_classes = self._detect_god_classes(god_class_threshold)

        if "dead_code" in checks:
            report.dead_symbols = self._detect_dead_symbols()

        report.score = self._compute_score(report)
        return report

    def _compute_coupling(self) -> dict[str, ModuleMetrics]:
        modules: dict[str, ModuleMetrics] = {}
        all_files = self._dep_graph.get_all_files()
        # Group files by directory
        dir_files: dict[str, list[str]] = {}
        for f in all_files:
            d = os.path.dirname(f) or "."
            if d not in dir_files:
                dir_files[d] = []
            dir_files[d].append(f)

        for d, files in dir_files.items():
            ca = 0  # afferent (incoming from outside)
            ce = 0  # efferent (outgoing to outside)
            for f in files:
                for dep in self._dep_graph.get_dependencies(f):
                    if os.path.dirname(dep) != d:
                        ce += 1
                for dep in self._dep_graph.get_dependents(f):
                    if os.path.dirname(dep) != d:
                        ca += 1
            modules[d] = ModuleMetrics(path=d, file_count=len(files), afferent_coupling=ca, efferent_coupling=ce)
        return modules

    def _compute_coupling_matrix(self) -> dict[str, dict[str, int]]:
        matrix: dict[str, dict[str, int]] = {}
        for edge in self._dep_graph.get_edges():
            src_dir = os.path.dirname(edge.source_file) or "."
            tgt_dir = (os.path.dirname(edge.target_file) or ".") if edge.target_file else "external"
            if src_dir not in matrix:
                matrix[src_dir] = {}
            matrix[src_dir][tgt_dir] = matrix[src_dir].get(tgt_dir, 0) + 1
        return matrix

    def _detect_cycles(self) -> list[DependencyCycle]:
        adjacency: dict[str, list[str]] = {}
        for f in self._dep_graph.get_all_files():
            deps = self._dep_graph.get_dependencies(f)
            if deps:
                adjacency[f] = deps
        return self._cycle_detector.detect_cycles(adjacency)

    def _check_layer_violations(self, layer_rules: dict[str, dict[str, list[str]]]) -> list[LayerViolation]:
        violations: list[LayerViolation] = []
        for edge in self._dep_graph.get_edges():
            if edge.is_external:
                continue
            src_layer = self._get_layer(edge.source_file, layer_rules)
            tgt_layer = self._get_layer(edge.target_file or "", layer_rules)
            if src_layer and tgt_layer and src_layer != tgt_layer:
                allowed = layer_rules.get(src_layer, {}).get("allowed_deps", [])
                if tgt_layer not in allowed:
                    violations.append(LayerViolation(
                        source_file=edge.source_file,
                        target_file=edge.target_file or "",
                        source_layer=src_layer,
                        target_layer=tgt_layer,
                        description=f"{src_layer} should not depend on {tgt_layer}",
                    ))
        return violations

    def _get_layer(self, file_path: str, rules: dict[str, dict[str, list[str]]]) -> str | None:
        for layer_name in rules:
            if layer_name in file_path:
                return layer_name
        return None

    def _detect_god_classes(self, threshold: int) -> list[GodClassInfo]:
        gods: list[GodClassInfo] = []
        all_defs = self._symbol_index.get_all_definitions()
        for name, defs_list in all_defs.items():
            for d in defs_list:
                if d.symbol_type == "class":
                    # Count methods for this class
                    method_count = 0
                    for mname, mdefs in all_defs.items():
                        for md in mdefs:
                            if md.parent_class == name and md.symbol_type in ("method", "function"):
                                method_count += 1
                    if method_count >= threshold:
                        gods.append(GodClassInfo(
                            class_name=name,
                            file_path=d.file_path,
                            method_count=method_count,
                            line_count=d.end_line - d.line + 1,
                        ))
        return gods

    def _detect_dead_symbols(self) -> list[str]:
        dead: list[str] = []
        all_defs = self._symbol_index.get_all_definitions()
        all_refs = self._symbol_index.get_all_references()
        for name in all_defs:
            if name not in all_refs or len(all_refs[name]) == 0:
                # Skip __init__, __main__ etc
                if not name.startswith("__"):
                    dead.append(name)
        return dead

    def _compute_score(self, report: ArchitectureReport) -> int:
        score = 100
        score -= len(report.cycles) * 10
        score -= len(report.layer_violations) * 5
        score -= len(report.god_classes) * 8
        score -= min(len(report.dead_symbols), 10) * 2
        for m in report.module_metrics.values():
            if m.distance_from_main_sequence > 0.7:
                score -= 3
        return max(0, min(100, score))
