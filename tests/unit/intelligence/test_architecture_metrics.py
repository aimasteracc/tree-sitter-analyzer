#!/usr/bin/env python3
"""Tests for ArchitectureMetrics."""

import pytest

from tree_sitter_analyzer.intelligence.architecture_metrics import ArchitectureMetrics
from tree_sitter_analyzer.intelligence.dependency_graph import DependencyGraphBuilder
from tree_sitter_analyzer.intelligence.models import (
    DependencyEdge,
    SymbolDefinition,
    SymbolReference,
)
from tree_sitter_analyzer.intelligence.symbol_index import SymbolIndex


@pytest.fixture
def components():
    dg = DependencyGraphBuilder()
    si = SymbolIndex()
    return dg, si


@pytest.fixture
def metrics(components):
    dg, si = components
    return ArchitectureMetrics(dg, si)


class TestArchitectureMetricsBasic:
    def test_empty_report(self, metrics):
        report = metrics.compute_report("src/")
        assert report.score == 100
        assert report.cycles == []

    def test_coupling_metrics(self, components):
        dg, si = components
        dg.add_edge(DependencyEdge("src/a.py", "src/b.py", "b"))
        dg.add_edge(DependencyEdge("lib/c.py", "src/a.py", "a"))
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["coupling_metrics"])
        assert len(report.module_metrics) > 0

    def test_cycle_detection(self, components):
        dg, si = components
        dg.add_edge(DependencyEdge("a.py", "b.py", "b"))
        dg.add_edge(DependencyEdge("b.py", "a.py", "a"))
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["circular_dependencies"])
        assert len(report.cycles) == 1

    def test_layer_violations(self, components):
        dg, si = components
        dg.add_edge(
            DependencyEdge("models/user.py", "services/auth.py", "services.auth")
        )
        m = ArchitectureMetrics(dg, si)
        rules = {
            "models": {"allowed_deps": ["utils"]},
            "services": {"allowed_deps": ["models"]},
        }
        report = m.compute_report(".", checks=["layer_violations"], layer_rules=rules)
        assert len(report.layer_violations) >= 1

    def test_god_class_detection(self, components):
        dg, si = components
        si.add_definition(SymbolDefinition("BigClass", "big.py", 1, 500, "class"))
        for i in range(25):
            si.add_definition(
                SymbolDefinition(
                    f"method_{i}",
                    "big.py",
                    i * 10,
                    i * 10 + 5,
                    "method",
                    parent_class="BigClass",
                )
            )
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["god_classes"], god_class_threshold=20)
        assert len(report.god_classes) >= 1
        assert report.god_classes[0].method_count >= 20

    def test_dead_code_detection(self, components):
        dg, si = components
        si.add_definition(SymbolDefinition("used_func", "a.py", 1, 5, "function"))
        si.add_definition(SymbolDefinition("dead_func", "b.py", 1, 5, "function"))
        si.add_reference(SymbolReference("used_func", "c.py", 10, "call"))
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["dead_code"])
        assert "dead_func" in report.dead_symbols
        assert "used_func" not in report.dead_symbols

    def test_score_penalized_by_cycles(self, components):
        dg, si = components
        dg.add_edge(DependencyEdge("a.py", "b.py", "b"))
        dg.add_edge(DependencyEdge("b.py", "a.py", "a"))
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".")
        assert report.score < 100

    def test_report_to_dict(self, metrics):
        report = metrics.compute_report("src/")
        d = report.to_dict()
        assert "score" in d
        assert "cycles" in d

    def test_coupling_matrix(self, components):
        dg, si = components
        dg.add_edge(DependencyEdge("src/a.py", "lib/b.py", "lib.b"))
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["coupling_metrics"])
        assert len(report.coupling_matrix) > 0


class TestStabilityMetrics:
    """Tests for stability_metrics check - AH-015."""

    @pytest.fixture
    def unstable_setup(self, components):
        """Module 'a' has Ce=5, Ca=0 → instability=1.0 (clearly unstable)."""
        dg, si = components
        for target in ["b/m.py", "c/m.py", "d/m.py", "e/m.py", "f/m.py"]:
            dg.add_edge(DependencyEdge("a/m.py", target, target.split("/")[0]))
        return dg, si

    @pytest.fixture
    def stable_setup(self, components):
        """Module 'stable' has Ce=1, Ca=5 → instability=0.167 (stable)."""
        dg, si = components
        for i in range(5):
            dg.add_edge(DependencyEdge(f"dep{i}/m.py", "stable/m.py", "stable"))
        dg.add_edge(DependencyEdge("stable/m.py", "utils/m.py", "utils"))
        return dg, si

    def test_stability_metrics_returns_unstable_modules(self, unstable_setup):
        dg, si = unstable_setup
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["stability_metrics"])
        unstable_paths = [mod.path for mod in report.unstable_modules]
        assert "a" in unstable_paths

    def test_stable_modules_excluded(self, stable_setup):
        dg, si = stable_setup
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["stability_metrics"])
        unstable_paths = [mod.path for mod in report.unstable_modules]
        assert "stable" not in unstable_paths

    def test_stability_metrics_without_coupling_metrics(self, unstable_setup):
        """stability_metrics must work even if coupling_metrics not in checks."""
        dg, si = unstable_setup
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["stability_metrics"])
        assert isinstance(report.unstable_modules, list)
        assert len(report.unstable_modules) > 0

    def test_stability_threshold_is_strictly_greater_than_07(self, components):
        """Exact instability=0.7 (Ca=3, Ce=7) should NOT appear (threshold is strict >0.7)."""
        dg, si = components
        for i in range(3):
            dg.add_edge(DependencyEdge(f"caller{i}/m.py", "target/m.py", "target"))
        for i in range(7):
            dg.add_edge(DependencyEdge("target/m.py", f"dep{i}/m.py", f"dep{i}"))
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["stability_metrics"])
        unstable_paths = [mod.path for mod in report.unstable_modules]
        assert "target" not in unstable_paths

    def test_stability_metrics_sorted_by_instability_desc(self, components):
        """unstable_modules must be sorted by instability descending."""
        dg, si = components
        # module_high: Ce=9, Ca=1 → instability=0.9
        dg.add_edge(DependencyEdge("caller_h/m.py", "high/m.py", "high"))
        for i in range(9):
            dg.add_edge(DependencyEdge("high/m.py", f"hd{i}/m.py", f"hd{i}"))
        # module_mid: Ce=8, Ca=2 → instability=0.8
        for i in range(2):
            dg.add_edge(DependencyEdge(f"caller_m{i}/m.py", "mid/m.py", "mid"))
        for i in range(8):
            dg.add_edge(DependencyEdge("mid/m.py", f"md{i}/m.py", f"md{i}"))
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["stability_metrics"])
        if len(report.unstable_modules) >= 2:
            for i in range(len(report.unstable_modules) - 1):
                assert (
                    report.unstable_modules[i].instability
                    >= report.unstable_modules[i + 1].instability
                )


    def test_stability_metrics_reuses_existing_module_metrics(self, components):
        """stability_metrics skips recomputing coupling when module_metrics already populated."""
        dg, si = components
        dg.add_edge(DependencyEdge("a/m.py", "b/m.py", "b"))
        dg.add_edge(DependencyEdge("a/m.py", "c/m.py", "c"))
        dg.add_edge(DependencyEdge("a/m.py", "d/m.py", "d"))
        m = ArchitectureMetrics(dg, si)
        # coupling_metrics runs first and populates module_metrics;
        # stability_metrics must use that cached value (False branch of 'if not report.module_metrics')
        report = m.compute_report(".", checks=["coupling_metrics", "stability_metrics"])
        assert isinstance(report.unstable_modules, list)
        assert len(report.module_metrics) > 0


class TestHotspotDetection:
    """Tests for hotspots check - AH-016."""

    def test_hotspot_high_instability_high_coupling(self, components):
        """instability > 0.7 AND efferent_coupling >= 3 → hotspot."""
        dg, si = components
        # "hot": Ce=8, Ca=1 → instability=8/9≈0.889, Ce=8 >= 3
        dg.add_edge(DependencyEdge("caller/m.py", "hot/m.py", "hot"))
        for i in range(8):
            dg.add_edge(DependencyEdge("hot/m.py", f"dep{i}/m.py", f"dep{i}"))
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["hotspots"])
        hotspot_paths = [mod.path for mod in report.hotspot_modules]
        assert "hot" in hotspot_paths

    def test_low_coupling_not_hotspot(self, components):
        """instability > 0.7 but efferent_coupling < 3 → NOT hotspot."""
        dg, si = components
        # "lonely": Ce=2, Ca=0 → instability=1.0, but Ce=2 < 3
        for i in range(2):
            dg.add_edge(DependencyEdge("lonely/m.py", f"dep{i}/m.py", f"dep{i}"))
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["hotspots"])
        hotspot_paths = [mod.path for mod in report.hotspot_modules]
        assert "lonely" not in hotspot_paths

    def test_hotspot_modules_sorted_by_score_desc(self, components):
        """hotspot_modules sorted by (instability × efferent_coupling) descending."""
        dg, si = components
        # "big": Ce=10, Ca=0 → I=1.0, score=10.0
        for i in range(10):
            dg.add_edge(DependencyEdge("big/m.py", f"b{i}/m.py", f"b{i}"))
        # "small": Ce=4, Ca=1 → I=0.8, score=3.2
        dg.add_edge(DependencyEdge("x/m.py", "small/m.py", "small"))
        for i in range(4):
            dg.add_edge(DependencyEdge("small/m.py", f"s{i}/m.py", f"s{i}"))
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["hotspots"])
        if len(report.hotspot_modules) >= 2:
            scores = [
                mod.instability * mod.efferent_coupling
                for mod in report.hotspot_modules
            ]
            assert scores == sorted(scores, reverse=True)

    def test_hotspots_result_field_is_list(self, components):
        """report.hotspot_modules is always a list, even when empty."""
        dg, si = components
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["hotspots"])
        assert isinstance(report.hotspot_modules, list)

    def test_hotspots_reuses_existing_module_metrics(self, components):
        """hotspots skips recomputing coupling when module_metrics already populated."""
        dg, si = components
        dg.add_edge(DependencyEdge("caller/m.py", "hot/m.py", "hot"))
        for i in range(8):
            dg.add_edge(DependencyEdge("hot/m.py", f"dep{i}/m.py", f"dep{i}"))
        m = ArchitectureMetrics(dg, si)
        # coupling_metrics runs first; hotspots uses cached module_metrics
        # (False branch of 'if not report.module_metrics')
        report = m.compute_report(".", checks=["coupling_metrics", "hotspots"])
        hotspot_paths = [mod.path for mod in report.hotspot_modules]
        assert "hot" in hotspot_paths
