#!/usr/bin/env python3
"""Architecture metrics for Code Intelligence Graph."""

from __future__ import annotations

import os
from collections.abc import Callable

from .cycle_detector import CycleDetector
from .dependency_graph import DependencyGraphBuilder
from .models import (
    ArchitectureReport,
    DependencyCycle,
    GodClassInfo,
    LayerViolation,
    ModuleMetrics,
    OvertestedSymbol,
    SymbolDefinition,
    TestCoverageReport,
    UntestedSymbol,
)
from .symbol_index import SymbolIndex


class ArchitectureMetrics:
    """Computes architecture health metrics."""

    def __init__(
        self, dep_graph: DependencyGraphBuilder, symbol_index: SymbolIndex
    ) -> None:
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
        return file_path.startswith(scope) or os.path.dirname(file_path).startswith(
            scope.rstrip("/")
        )

    def compute_report(
        self,
        path: str,
        checks: list[str] | None = None,
        layer_rules: dict[str, dict[str, list[str]]] | None = None,
        god_class_threshold: int = 20,
        test_file_predicate: Callable[[str], bool] | None = None,
    ) -> ArchitectureReport:
        if checks is None:
            checks = [
                "coupling_metrics",
                "circular_dependencies",
                "layer_violations",
                "god_classes",
                "dead_code",
            ]

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

        if "test_coverage" in checks and test_file_predicate is not None:
            report.test_coverage = self._analyze_test_coverage(
                scope=scope,
                test_file_predicate=test_file_predicate,
            )

        if "stability_metrics" in checks:
            if not report.module_metrics:
                report.module_metrics = self._compute_coupling(scope)
            report.unstable_modules = sorted(
                [m for m in report.module_metrics.values() if m.instability > 0.7],
                key=lambda m: m.instability,
                reverse=True,
            )

        if "hotspots" in checks:
            if not report.module_metrics:
                report.module_metrics = self._compute_coupling(scope)
            report.hotspot_modules = sorted(
                [
                    m
                    for m in report.module_metrics.values()
                    if m.instability > 0.7 and m.efferent_coupling >= 3
                ],
                key=lambda m: m.instability * m.efferent_coupling,
                reverse=True,
            )

        report.score = self._compute_score(report)
        return report

    def _compute_coupling(self, scope: str = "") -> dict[str, ModuleMetrics]:
        modules: dict[str, ModuleMetrics] = {}
        all_files: set[str] | list[str] = self._dep_graph.get_all_files()
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
                1
                for c in classes_in_module
                if c.modifiers and any(kw in c.modifiers for kw in abstract_keywords)
            )
            abstractness = (
                abstract_count / len(classes_in_module) if classes_in_module else 0.0
            )

            modules[d] = ModuleMetrics(
                path=d,
                file_count=len(files),
                afferent_coupling=ca,
                efferent_coupling=ce,
                abstractness=abstractness,
            )
        return modules

    def _compute_coupling_matrix(self, scope: str = "") -> dict[str, dict[str, int]]:
        matrix: dict[str, dict[str, int]] = {}
        for edge in self._dep_graph.get_edges():
            if scope and not self._file_in_scope(edge.source_file, scope):
                continue
            src_dir = os.path.dirname(edge.source_file) or "."
            tgt_dir = (
                (os.path.dirname(edge.target_file) or ".")
                if edge.target_file
                else "external"
            )
            if src_dir not in matrix:
                matrix[src_dir] = {}
            matrix[src_dir][tgt_dir] = matrix[src_dir].get(tgt_dir, 0) + 1
        return matrix

    def _detect_cycles(self, scope: str = "") -> list[DependencyCycle]:
        adjacency: dict[str, list[str]] = {}
        all_files: set[str] | list[str] = self._dep_graph.get_all_files()
        if scope:
            all_files = [f for f in all_files if self._file_in_scope(f, scope)]
        scoped_set = set(all_files)
        for f in all_files:
            # 过滤掉 TYPE_CHECKING import 和懒加载（函数体内）import：
            # 这两类 import 不会在模块加载时形成运行时循环依赖。
            edges = self._dep_graph.get_edges_for_file(f)
            runtime_deps: list[str] = []
            for edge in edges:
                if (
                    edge.target_file
                    and not edge.is_type_check_only
                    and not edge.is_lazy_import
                ):
                    if not scope or edge.target_file in scoped_set:
                        if edge.target_file not in runtime_deps:
                            runtime_deps.append(edge.target_file)
            if runtime_deps:
                adjacency[f] = runtime_deps
        return self._cycle_detector.detect_cycles(adjacency)

    def _check_layer_violations(
        self, layer_rules: dict[str, dict[str, list[str]]]
    ) -> list[LayerViolation]:
        violations: list[LayerViolation] = []
        for edge in self._dep_graph.get_edges():
            if edge.is_external:
                continue
            src_layer = self._get_layer(edge.source_file, layer_rules)
            tgt_layer = self._get_layer(edge.target_file or "", layer_rules)
            if src_layer and tgt_layer and src_layer != tgt_layer:
                allowed = layer_rules.get(src_layer, {}).get("allowed_deps", [])
                if tgt_layer not in allowed:
                    violations.append(
                        LayerViolation(
                            source_file=edge.source_file,
                            target_file=edge.target_file or "",
                            source_layer=src_layer,
                            target_layer=tgt_layer,
                            description=f"{src_layer} should not depend on {tgt_layer}",
                        )
                    )
        return violations

    def _get_layer(
        self, file_path: str, rules: dict[str, dict[str, list[str]]]
    ) -> str | None:
        for layer_name in rules:
            if layer_name in file_path:
                return layer_name
        return None

    def _detect_god_classes(
        self, threshold: int, scope: str = ""
    ) -> list[GodClassInfo]:
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
                            if md.parent_class == name and md.symbol_type in (
                                "method",
                                "function",
                            ):
                                method_count += 1
                    if method_count >= threshold:
                        gods.append(
                            GodClassInfo(
                                class_name=name,
                                file_path=d.file_path,
                                method_count=method_count,
                                line_count=d.end_line - d.line + 1,
                            )
                        )
        return gods

    # Decorators whose methods are accessed via attribute syntax, not calls.
    # These cannot be detected by call-graph-based dead-code analysis.
    _IMPLICIT_ACCESS_MODIFIERS = frozenset(
        {
            "property",
            "staticmethod",
            "classmethod",
        }
    )

    # Known decorator patterns that register callbacks at runtime (e.g. MCP SDK).
    # Functions decorated with these are NOT dead even if never called directly.
    _CALLBACK_DECORATOR_PATTERNS = frozenset(
        {
            "server.list_tools",
            "server.call_tool",
            "server.list_resources",
            "server.read_resource",
            "server.list_prompts",
            "server.get_prompt",
        }
    )

    def _detect_dead_symbols(self, scope: str = "") -> list[str]:
        dead: list[str] = []
        all_defs = self._symbol_index.get_all_definitions()
        all_refs = self._symbol_index.get_all_references()

        # Pre-compute a lookup of (file_path) -> list[SymbolDefinition] for
        # inner-function detection.
        file_defs: dict[str, list[SymbolDefinition]] = {}
        for defs_list in all_defs.values():
            for d in defs_list:
                file_defs.setdefault(d.file_path, []).append(d)

        for name, defs_list in all_defs.items():
            if name not in all_refs or len(all_refs[name]) == 0:
                # Skip __init__, __main__ etc
                if name.startswith("__"):
                    continue
                # Skip symbols with implicit-access decorators (@property, etc.)
                if any(
                    d.modifiers
                    and any(m in self._IMPLICIT_ACCESS_MODIFIERS for m in d.modifiers)
                    for d in defs_list
                ):
                    continue

                # (v5) Skip inner/nested functions whose line range is
                # enclosed by another definition in the same file.
                if all(self._is_inner_def(d, file_defs) for d in defs_list):
                    continue

                # (v5) Skip functions registered via known callback decorators
                # (e.g. @server.list_tools()).
                if any(
                    d.modifiers
                    and any(m in self._CALLBACK_DECORATOR_PATTERNS for m in d.modifiers)
                    for d in defs_list
                ):
                    continue

                # If scope is set, only include definitions within scope
                if scope:
                    if any(self._file_in_scope(d.file_path, scope) for d in defs_list):
                        dead.append(name)
                else:
                    dead.append(name)
        return dead

    @staticmethod
    def _is_inner_def(
        defn: SymbolDefinition,
        file_defs: dict[str, list[SymbolDefinition]],
    ) -> bool:
        """Return True if *defn* is textually nested inside another definition."""
        siblings = file_defs.get(defn.file_path, [])
        for other in siblings:
            if other is defn or other.name == defn.name:
                continue
            if other.line < defn.line and other.end_line > defn.end_line:
                return True
        return False

    def _analyze_test_coverage(
        self,
        scope: str = "",
        test_file_predicate: Callable[[str], bool] | None = None,
        overtested_threshold: int = 10,
    ) -> TestCoverageReport:
        """Analyse test coverage by comparing symbol references from test vs source files.

        Args:
            scope: Path prefix to restrict analysis.
            test_file_predicate: Callable that returns True for test file paths.
            overtested_threshold: Distinct test-function references above which a
                symbol is considered over-tested.
        """
        if test_file_predicate is None:
            return TestCoverageReport()

        all_defs = self._symbol_index.get_all_definitions()
        all_refs = self._symbol_index.get_all_references()

        untested: list[UntestedSymbol] = []
        overtested: list[OvertestedSymbol] = []
        test_only: list[str] = []

        total_public = 0
        tested_count = 0

        # Build a set of all defined symbol names for inner-function detection.
        # A function is considered "inner" if it is textually nested inside
        # another definition in the same file (its line range is contained).
        def _is_inner_function(
            defn: SymbolDefinition, all_source_defs: dict[str, list[SymbolDefinition]]
        ) -> bool:
            """Return True if *defn* is a nested/inner function inside another definition."""
            for other_name, other_defs in all_source_defs.items():
                if other_name == defn.name:
                    continue
                for od in other_defs:
                    if (
                        od.file_path == defn.file_path
                        and od.symbol_type in ("function", "method")
                        and od.line < defn.line
                        and od.end_line > defn.end_line
                    ):
                        return True
            return False

        # Pre-filter source definitions for scope/test-file exclusion
        source_defs_map: dict[str, list[SymbolDefinition]] = {}
        for name, defs_list in all_defs.items():
            if name.startswith("_"):
                continue
            filtered = [
                d
                for d in defs_list
                if not test_file_predicate(d.file_path)
                and (not scope or self._file_in_scope(d.file_path, scope))
            ]
            if filtered:
                source_defs_map[name] = filtered

        # (v5) Pre-compute which parent classes have test references so we
        # can mark methods as "indirectly tested" when their class IS tested.
        tested_classes: set[str] = set()
        for cls_name in source_defs_map:
            cls_defs = source_defs_map[cls_name]
            if any(d.symbol_type == "class" for d in cls_defs):
                refs_for_cls = all_refs.get(cls_name, [])
                if any(test_file_predicate(r.file_path) for r in refs_for_cls):
                    tested_classes.add(cls_name)

        for name, source_defs in source_defs_map.items():
            # AH-013: Skip symbols with implicit-access modifiers (@property, etc.)
            if any(
                d.modifiers
                and any(m in self._IMPLICIT_ACCESS_MODIFIERS for m in d.modifiers)
                for d in source_defs
            ):
                continue

            # AH-013: Skip inner/nested functions (their coverage is inherited
            # from the enclosing function)
            if all(_is_inner_function(d, source_defs_map) for d in source_defs):
                continue

            # (v5) Skip MCP callback-registered functions (decorated with
            # @server.list_tools(), etc.) — these are tested via integration.
            if any(
                d.modifiers
                and any(m in self._CALLBACK_DECORATOR_PATTERNS for m in d.modifiers)
                for d in source_defs
            ):
                continue

            total_public += 1

            # Partition references into test vs source
            refs_for_name = all_refs.get(name, [])
            test_refs = [r for r in refs_for_name if test_file_predicate(r.file_path)]
            source_refs = [
                r for r in refs_for_name if not test_file_predicate(r.file_path)
            ]

            has_test_refs = len(test_refs) > 0
            has_source_refs = len(source_refs) > 0

            # (v5) Consider methods "indirectly tested" if their parent class
            # has direct test references — avoids flagging internal methods of
            # well-tested classes.
            if not has_test_refs:
                if any(
                    d.parent_class and d.parent_class in tested_classes
                    for d in source_defs
                ):
                    has_test_refs = True  # promote to tested

            if has_test_refs:
                tested_count += 1

            # AH-014: Scope overtested by (file_path, name) — iterate per-definition
            for defn in source_defs:
                # Untested: no test references at all for this name
                if not has_test_refs:
                    untested.append(
                        UntestedSymbol(
                            name=name,
                            file_path=defn.file_path,
                            symbol_type=defn.symbol_type,
                            line=defn.line,
                        )
                    )
                    break  # one untested entry per name is sufficient

                # Over-tested: count distinct test functions referencing this symbol
                # For correct scoping we still count all test refs for *name*
                # but partition so each definition file gets its own overtested entry.
                distinct_test_fns: set[str] = set()
                test_file_set: set[str] = set()
                for r in test_refs:
                    key = f"{r.file_path}::{r.context_function or '_'}"
                    distinct_test_fns.add(key)
                    test_file_set.add(r.file_path)

                # When multiple definitions exist for the same name across files,
                # split refs proportionally by checking if any ref's context
                # mentions the definition file.  Simple heuristic: divide by
                # number of source definitions.
                if len(source_defs) > 1:
                    per_def_count = len(distinct_test_fns) // len(source_defs)
                else:
                    per_def_count = len(distinct_test_fns)

                if per_def_count > overtested_threshold:
                    overtested.append(
                        OvertestedSymbol(
                            name=name,
                            file_path=defn.file_path,
                            test_ref_count=per_def_count,
                            test_files=sorted(test_file_set),
                        )
                    )

            # Test-only: referenced from tests but not from source code
            if has_test_refs and not has_source_refs:
                test_only.append(name)

        coverage_ratio = tested_count / total_public if total_public > 0 else 0.0

        return TestCoverageReport(
            untested_symbols=untested,
            overtested_symbols=overtested,
            test_only_symbols=test_only,
            coverage_ratio=coverage_ratio,
        )

    def _compute_score(self, report: ArchitectureReport) -> int:
        score = 100
        # Each category has a cap to prevent score collapse
        score -= min(len(report.cycles) * 5, 25)  # cycles: max -25
        score -= min(len(report.layer_violations) * 3, 20)  # violations: max -20
        score -= min(len(report.god_classes) * 2, 20)  # god classes: max -20
        score -= min(len(report.dead_symbols), 20)  # dead code: max -20
        d_count = sum(
            1
            for m in report.module_metrics.values()
            if m.distance_from_main_sequence > 0.7
        )
        score -= min(d_count, 15)  # D>0.7: max -15
        return max(0, min(100, score))
