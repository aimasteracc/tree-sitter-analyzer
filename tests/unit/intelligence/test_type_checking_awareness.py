#!/usr/bin/env python3
"""Tests for TYPE_CHECKING awareness in dependency analysis (H1)."""
import pytest

from tree_sitter_analyzer.intelligence.architecture_metrics import ArchitectureMetrics
from tree_sitter_analyzer.intelligence.dependency_graph import DependencyGraphBuilder
from tree_sitter_analyzer.intelligence.models import DependencyEdge
from tree_sitter_analyzer.intelligence.symbol_index import SymbolIndex


@pytest.fixture
def components():
    dg = DependencyGraphBuilder()
    si = SymbolIndex()
    return dg, si


class TestTypeCheckingAwareness:
    """TYPE_CHECKING imports should not create runtime dependency cycles."""

    def test_type_checking_edge_has_marker(self):
        """DependencyEdge should support is_type_check_only flag."""
        edge = DependencyEdge(
            source_file="a.py",
            target_file="b.py",
            target_module="b",
            is_type_check_only=True,
        )
        assert edge.is_type_check_only is True

    def test_default_edge_not_type_check_only(self):
        """Default DependencyEdge should have is_type_check_only=False."""
        edge = DependencyEdge("a.py", "b.py", "b")
        assert edge.is_type_check_only is False

    def test_type_checking_cycle_excluded(self, components):
        """Cycles caused only by TYPE_CHECKING imports should not be reported."""
        dg, si = components
        # Normal import: a -> b
        dg.add_edge(DependencyEdge("a.py", "b.py", "b"))
        # TYPE_CHECKING import: b -> a (would create cycle, but is type-only)
        dg.add_edge(DependencyEdge("b.py", "a.py", "a", is_type_check_only=True))

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["circular_dependencies"])
        assert len(report.cycles) == 0, f"Expected no cycles, got {report.cycles}"

    def test_real_cycle_still_detected(self, components):
        """Real runtime cycles should still be detected."""
        dg, si = components
        dg.add_edge(DependencyEdge("a.py", "b.py", "b"))
        dg.add_edge(DependencyEdge("b.py", "a.py", "a"))  # NOT type_check_only

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["circular_dependencies"])
        assert len(report.cycles) == 1

    def test_mixed_cycle_with_type_checking(self, components):
        """A cycle where one edge is type-check-only should not be reported."""
        dg, si = components
        # a -> b (normal)
        dg.add_edge(DependencyEdge("a.py", "b.py", "b"))
        # b -> c (normal)
        dg.add_edge(DependencyEdge("b.py", "c.py", "c"))
        # c -> a (TYPE_CHECKING only — breaks the cycle at runtime)
        dg.add_edge(DependencyEdge("c.py", "a.py", "a", is_type_check_only=True))

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["circular_dependencies"])
        assert len(report.cycles) == 0

    def test_to_dict_includes_type_check_only_when_true(self):
        """to_dict should include is_type_check_only when True."""
        edge = DependencyEdge("a.py", "b.py", "b", is_type_check_only=True)
        d = edge.to_dict()
        assert "is_type_check_only" in d
        assert d["is_type_check_only"] is True

    def test_to_dict_includes_type_check_only_when_false(self):
        """to_dict should include is_type_check_only even when False (for consistency)."""
        edge = DependencyEdge("a.py", "b.py", "b")
        d = edge.to_dict()
        assert "is_type_check_only" in d
        assert d["is_type_check_only"] is False
