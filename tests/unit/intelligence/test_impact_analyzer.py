#!/usr/bin/env python3
"""Tests for ImpactAnalyzer."""
import pytest

from tree_sitter_analyzer.intelligence.call_graph import CallGraphBuilder
from tree_sitter_analyzer.intelligence.dependency_graph import DependencyGraphBuilder
from tree_sitter_analyzer.intelligence.impact_analyzer import ImpactAnalyzer
from tree_sitter_analyzer.intelligence.models import (
    CallSite,
    DependencyEdge,
    SymbolDefinition,
)
from tree_sitter_analyzer.intelligence.symbol_index import SymbolIndex


@pytest.fixture
def components():
    cg = CallGraphBuilder()
    dg = DependencyGraphBuilder()
    si = SymbolIndex()
    return cg, dg, si


@pytest.fixture
def analyzer(components):
    cg, dg, si = components
    return ImpactAnalyzer(cg, dg, si)


class TestImpactAnalyzerBasic:
    def test_no_impacts(self, analyzer):
        result = analyzer.assess("unknown_func")
        assert result.risk_level == "low"
        assert result.total_affected_files == 0

    def test_direct_callers(self, components):
        cg, dg, si = components
        cg._call_sites["api.py"] = [
            CallSite("api.py", "endpoint", "login", None, 10, "login()"),
        ]
        analyzer = ImpactAnalyzer(cg, dg, si)
        result = analyzer.assess("login")
        assert len(result.direct_impacts) >= 1
        assert result.direct_impacts[0].impact_type == "direct_caller"

    def test_importers_detected(self, components):
        cg, dg, si = components
        si.add_definition(SymbolDefinition("AuthService", "auth.py", 1, 50, "class"))
        dg.add_edge(DependencyEdge("api.py", "auth.py", "auth", ["AuthService"]))
        analyzer = ImpactAnalyzer(cg, dg, si)
        result = analyzer.assess("AuthService")
        importer_files = [i.file_path for i in result.direct_impacts]
        assert "api.py" in importer_files

    def test_transitive_impacts(self, components):
        cg, dg, si = components
        si.add_definition(SymbolDefinition("foo", "a.py", 1, 5, "function"))
        dg.add_edge(DependencyEdge("b.py", "a.py", "a", ["foo"]))
        dg.add_edge(DependencyEdge("c.py", "b.py", "b", ["bar"]))
        analyzer = ImpactAnalyzer(cg, dg, si)
        result = analyzer.assess("foo", depth=3)
        trans_files = [i.file_path for i in result.transitive_impacts]
        assert "c.py" in trans_files

    def test_risk_level_high(self, components):
        cg, dg, si = components
        for i in range(6):
            cg._call_sites[f"file{i}.py"] = [
                CallSite(f"file{i}.py", f"func{i}", "target", None, 1, "target()"),
            ]
        analyzer = ImpactAnalyzer(cg, dg, si)
        result = analyzer.assess("target", change_type="signature_change")
        assert result.risk_level in ("high", "critical")

    def test_test_detection(self, components):
        cg, dg, si = components
        si.add_definition(SymbolDefinition("foo", "a.py", 1, 5, "function"))
        dg.add_edge(DependencyEdge("test_a.py", "a.py", "a", ["foo"]))
        analyzer = ImpactAnalyzer(cg, dg, si)
        result = analyzer.assess("foo", include_tests=True)
        assert any("test_" in t for t in result.affected_tests)

    def test_result_to_dict(self, analyzer):
        result = analyzer.assess("something")
        d = result.to_dict()
        assert "target" in d
        assert "risk_level" in d
