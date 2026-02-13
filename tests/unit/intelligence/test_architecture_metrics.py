#!/usr/bin/env python3
"""Tests for ArchitectureMetrics."""
import pytest
from tree_sitter_analyzer.intelligence.architecture_metrics import ArchitectureMetrics
from tree_sitter_analyzer.intelligence.dependency_graph import DependencyGraphBuilder
from tree_sitter_analyzer.intelligence.symbol_index import SymbolIndex
from tree_sitter_analyzer.intelligence.models import DependencyEdge, SymbolDefinition, SymbolReference


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
        dg.add_edge(DependencyEdge("models/user.py", "services/auth.py", "services.auth"))
        m = ArchitectureMetrics(dg, si)
        rules = {"models": {"allowed_deps": ["utils"]}, "services": {"allowed_deps": ["models"]}}
        report = m.compute_report(".", checks=["layer_violations"], layer_rules=rules)
        assert len(report.layer_violations) >= 1

    def test_god_class_detection(self, components):
        dg, si = components
        si.add_definition(SymbolDefinition("BigClass", "big.py", 1, 500, "class"))
        for i in range(25):
            si.add_definition(SymbolDefinition(f"method_{i}", "big.py", i*10, i*10+5, "method", parent_class="BigClass"))
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
