#!/usr/bin/env python3
"""Tests for ArchitectureMetrics path scoping and score capping (C2/H2)."""
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


class TestPathScoping:
    """All _detect_* methods should respect the path parameter."""

    def test_god_classes_scoped_to_path(self, components):
        """Only god classes within the path should be reported."""
        dg, si = components
        # God class inside target path
        si.add_definition(SymbolDefinition("BigClass", "src/core/big.py", 1, 500, "class"))
        for i in range(25):
            si.add_definition(SymbolDefinition(f"method_{i}", "src/core/big.py", i * 10, i * 10 + 5, "method", parent_class="BigClass"))
        # God class outside target path
        si.add_definition(SymbolDefinition("TestBig", "tests/test_big.py", 1, 500, "class"))
        for i in range(25):
            si.add_definition(SymbolDefinition(f"test_{i}", "tests/test_big.py", i * 10, i * 10 + 5, "method", parent_class="TestBig"))

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report("src/", checks=["god_classes"], god_class_threshold=20)
        assert len(report.god_classes) == 1
        assert report.god_classes[0].class_name == "BigClass"

    def test_cycles_scoped_to_path(self, components):
        """Only cycles within the path should be reported."""
        dg, si = components
        # Cycle inside src/
        dg.add_edge(DependencyEdge("src/a.py", "src/b.py", "b"))
        dg.add_edge(DependencyEdge("src/b.py", "src/a.py", "a"))
        # Cycle outside src/ (in tests/)
        dg.add_edge(DependencyEdge("tests/x.py", "tests/y.py", "y"))
        dg.add_edge(DependencyEdge("tests/y.py", "tests/x.py", "x"))

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report("src/", checks=["circular_dependencies"])
        assert len(report.cycles) == 1
        # The cycle should only contain src/ files
        for cycle in report.cycles:
            for f in cycle.files:
                assert f.startswith("src/")

    def test_coupling_scoped_to_path(self, components):
        """Coupling metrics should only include files within the path."""
        dg, si = components
        dg.add_edge(DependencyEdge("src/a.py", "src/b.py", "b"))
        dg.add_edge(DependencyEdge("lib/c.py", "lib/d.py", "d"))

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report("src/", checks=["coupling_metrics"])
        # Should only have src/ module metrics
        for module_path in report.module_metrics:
            assert module_path.startswith("src")

    def test_dead_code_scoped_to_path(self, components):
        """Dead code detection should only check definitions within the path."""
        dg, si = components
        si.add_definition(SymbolDefinition("used_func", "src/a.py", 1, 5, "function"))
        si.add_definition(SymbolDefinition("dead_in_src", "src/b.py", 1, 5, "function"))
        si.add_definition(SymbolDefinition("dead_in_tests", "tests/c.py", 1, 5, "function"))
        si.add_reference(SymbolReference("used_func", "src/c.py", 10, "call"))

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report("src/", checks=["dead_code"])
        assert "dead_in_src" in report.dead_symbols
        assert "dead_in_tests" not in report.dead_symbols

    def test_coupling_matrix_scoped_to_path(self, components):
        """Coupling matrix should only include edges within the path."""
        dg, si = components
        dg.add_edge(DependencyEdge("src/a.py", "src/b.py", "b"))
        dg.add_edge(DependencyEdge("lib/c.py", "lib/d.py", "d"))

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report("src/", checks=["coupling_metrics"])
        for src_dir in report.coupling_matrix:
            assert src_dir.startswith("src")

    def test_empty_path_returns_all(self, components):
        """When path is empty or '.', return global results (original behavior)."""
        dg, si = components
        dg.add_edge(DependencyEdge("src/a.py", "src/b.py", "b"))
        dg.add_edge(DependencyEdge("lib/c.py", "lib/d.py", "d"))

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["coupling_metrics"])
        assert len(report.module_metrics) >= 2


class TestScoreCapping:
    """Score should use per-category caps to avoid score=0 for medium-sized projects."""

    def test_score_not_zero_with_moderate_issues(self, components):
        """A project with moderate issues should not score 0."""
        dg, si = components
        # Add 2 cycles
        dg.add_edge(DependencyEdge("a.py", "b.py", "b"))
        dg.add_edge(DependencyEdge("b.py", "a.py", "a"))
        # Add 30 god classes (simulate typical project)
        for i in range(30):
            si.add_definition(SymbolDefinition(f"Class{i}", f"file{i}.py", 1, 500, "class"))
            for j in range(25):
                si.add_definition(SymbolDefinition(
                    f"method_{j}", f"file{i}.py", j * 10, j * 10 + 5, "method", parent_class=f"Class{i}"
                ))
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".")
        # With capping, score should NOT be 0
        assert report.score > 0, f"Score should be > 0 but got {report.score}"

    def test_score_each_category_capped(self, components):
        """Each category's deduction should have an upper limit."""
        dg, si = components
        # Add 100 god classes (extreme)
        for i in range(100):
            si.add_definition(SymbolDefinition(f"C{i}", f"f{i}.py", 1, 500, "class"))
            for j in range(25):
                si.add_definition(SymbolDefinition(
                    f"m{j}", f"f{i}.py", j * 10, j * 10 + 5, "method", parent_class=f"C{i}"
                ))
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["god_classes"])
        # Even with 100 god classes, god_class deduction should be capped
        # Score should be >= 100 - 20 (cap) = 80
        assert report.score >= 80, f"Score {report.score} too low; god class deduction should be capped"

    def test_max_deduction_100(self, components):
        """Total deductions should never exceed 100 (score can't go below 0)."""
        dg, si = components
        # Many issues of all types
        for i in range(20):
            dg.add_edge(DependencyEdge(f"a{i}.py", f"b{i}.py", f"b{i}"))
            dg.add_edge(DependencyEdge(f"b{i}.py", f"a{i}.py", f"a{i}"))
        for i in range(50):
            si.add_definition(SymbolDefinition(f"Big{i}", f"g{i}.py", 1, 500, "class"))
            for j in range(25):
                si.add_definition(SymbolDefinition(f"m{j}", f"g{i}.py", j * 10, j * 10 + 5, "method", parent_class=f"Big{i}"))
        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".")
        assert report.score >= 0
