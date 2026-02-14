#!/usr/bin/env python3
"""Architecture metrics for Code Intelligence Graph."""
from __future__ import annotations

import os

from .cycle_detector import CycleDetector
from .dependency_graph import DependencyGraphBuilder
from .models import (
    ArchitectureReport,
    DependencyCycle,
    GodClassInfo,
    LayerViolation,
    ModuleMetrics,
)
from .symbol_index import SymbolIndex


class ArchitectureMetrics:
    """Computes architecture health metrics."""

    def __init__(self, dep_graph: DependencyGraphBuilder, symbol_index: SymbolIndex) -> None:
        self._dep_graph = dep_graph
        self._symbol_index = symbol_index
        self._cycle_detector = CycleDetector()

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Normalize path for filtering. Returns empty string for root/global scope."""
        if not path or path == ".":
            return ""
        # Ensure trailing separator for prefix matching
        return path if path.endswith("/") else path + "/"

    def _file_in_scope(self, file_path: str, scope: str) -> bool:
        """Check if file_path is within the given scope prefix."""
        if not scope:
            return True
        return file_path.startswith(scope) or os.path.dirname(file_path).startswith(scope.rstrip("/"))

    def compute_report(
        self,
        path: str,
        checks: list[str] | None = None,
        layer_rules: dict[str, dict[str, list[str]]] | None = None,
        god_class_threshold: int = 20,
    ) -> ArchitectureReport:
        if checks is None:
            checks = ["coupling_metrics", "circular_dependencies", "layer_violations", "god_classes", "dead_code"]

        scope = self._normalize_path(path)
        report = ArchitectureReport(path=path)

        if "coupling_metrics" in checks:
            report.module_metrics = self._compute_coupling(scope)
            report.coupling_matrix = self._compute_coupling_matrix(scope)

        if "circular_dependencies" in checks:
            report.cycles = self._detect_cycles(scope)

        if "layer_violations" in checks and layer_rules:
            report.layer_violations = self._check_layer_violations(layer_rules)

        if "god_classes" in checks:
            report.god_classes = self._detect_god_classes(god_class_threshold, scope)

        if "dead_code" in checks:
            report.dead_symbols = self._detect_dead_symbols(scope)

        report.score = self._compute_score(report)
        return report

    def _compute_coupling(self, scope: str = "") -> dict[str, ModuleMetrics]:
        modules: dict[str, ModuleMetrics] = {}
        all_files = self._dep_graph.get_all_files()
        if scope:
            all_files = [f for f in all_files if self._file_in_scope(f, scope)]
        # Group files by directory
        dir_files: dict[str, list[str]] = {}
        for f in all_files:
            d = os.path.dirname(f) or "."
            if d not in dir_files:
                dir_files[d] = []
            dir_files[d].append(f)

        # Pre-compute all definitions for abstractness calculation
        all_defs = self._symbol_index.get_all_definitions()

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

            # Compute abstractness: ratio of abstract classes to total classes
            files_set = set(files)
            classes_in_module = []
            for _name, defs_list in all_defs.items():
                for defn in defs_list:
                    if defn.symbol_type == "class" and defn.file_path in files_set:
                        classes_in_module.append(defn)

            abstract_keywords = {"ABC", "Protocol", "abstractmethod"}
            abstract_count = sum(
                1 for c in classes_in_module
                if c.modifiers and any(kw in c.modifiers for kw in abstract_keywords)
            )
            abstractness = abstract_count / len(classes_in_module) if classes_in_module else 0.0

            modules[d] = ModuleMetrics(
                path=d, file_count=len(files),
                afferent_coupling=ca, efferent_coupling=ce,
                abstractness=abstractness,
            )
        return modules

    def _compute_coupling_matrix(self, scope: str = "") -> dict[str, dict[str, int]]:
        matrix: dict[str, dict[str, int]] = {}
        for edge in self._dep_graph.get_edges():
            if scope and not self._file_in_scope(edge.source_file, scope):
                continue
            src_dir = os.path.dirname(edge.source_file) or "."
            tgt_dir = (os.path.dirname(edge.target_file) or ".") if edge.target_file else "external"
            if src_dir not in matrix:
                matrix[src_dir] = {}
            matrix[src_dir][tgt_dir] = matrix[src_dir].get(tgt_dir, 0) + 1
        return matrix

    def _detect_cycles(self, scope: str = "") -> list[DependencyCycle]:
        adjacency: dict[str, list[str]] = {}
        all_files = self._dep_graph.get_all_files()
        if scope:
            all_files = [f for f in all_files if self._file_in_scope(f, scope)]
        scoped_set = set(all_files)
        for f in all_files:
            # Use edges to filter out TYPE_CHECKING-only imports
            edges = self._dep_graph.get_edges_for_file(f)
            runtime_deps: list[str] = []
            for edge in edges:
                if edge.target_file and not edge.is_type_check_only:
                    if not scope or edge.target_file in scoped_set:
                        if edge.target_file not in runtime_deps:
                            runtime_deps.append(edge.target_file)
            if runtime_deps:
                adjacency[f] = runtime_deps
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

    def _detect_god_classes(self, threshold: int, scope: str = "") -> list[GodClassInfo]:
        gods: list[GodClassInfo] = []
        all_defs = self._symbol_index.get_all_definitions()
        for name, defs_list in all_defs.items():
            for d in defs_list:
                if d.symbol_type == "class":
                    # Skip classes outside scope
                    if scope and not self._file_in_scope(d.file_path, scope):
                        continue
                    # Count methods for this class
                    method_count = 0
                    for _mname, mdefs in all_defs.items():
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

    def _detect_dead_symbols(self, scope: str = "") -> list[str]:
        dead: list[str] = []
        all_defs = self._symbol_index.get_all_definitions()
        all_refs = self._symbol_index.get_all_references()
        for name, defs_list in all_defs.items():
            if name not in all_refs or len(all_refs[name]) == 0:
                # Skip __init__, __main__ etc
                if not name.startswith("__"):
                    # If scope is set, only include definitions within scope
                    if scope:
                        if any(self._file_in_scope(d.file_path, scope) for d in defs_list):
                            dead.append(name)
                    else:
                        dead.append(name)
        return dead

    def _compute_score(self, report: ArchitectureReport) -> int:
        score = 100
        # Each category has a cap to prevent score collapse
        score -= min(len(report.cycles) * 5, 25)          # cycles: max -25
        score -= min(len(report.layer_violations) * 3, 20) # violations: max -20
        score -= min(len(report.god_classes) * 2, 20)      # god classes: max -20
        score -= min(len(report.dead_symbols), 20)         # dead code: max -20
        d_count = sum(1 for m in report.module_metrics.values()
                      if m.distance_from_main_sequence > 0.7)
        score -= min(d_count, 15)                          # D>0.7: max -15
        return max(0, min(100, score))
