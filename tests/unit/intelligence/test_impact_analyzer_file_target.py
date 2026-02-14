#!/usr/bin/env python3
"""Tests for ImpactAnalyzer file path target support (C1)."""

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


class TestFilePathTarget:
    """assess_change_impact should support file paths as targets, not just symbols."""

    def test_file_path_target_returns_dependents(self, components):
        """When target is a file path, return all files that import it."""
        cg, dg, si = components
        # auth.py is imported by api.py and cli.py
        dg.add_edge(DependencyEdge("api.py", "auth.py", "auth", ["login"]))
        dg.add_edge(DependencyEdge("cli.py", "auth.py", "auth", ["login"]))
        analyzer = ImpactAnalyzer(cg, dg, si)
        result = analyzer.assess("auth.py")
        impact_files = [i.file_path for i in result.direct_impacts]
        assert "api.py" in impact_files
        assert "cli.py" in impact_files
        assert result.total_affected_files >= 2

    def test_file_path_target_includes_symbol_callers(self, components):
        """File path target should also find callers of symbols defined in that file."""
        cg, dg, si = components
        # auth.py defines 'login' function
        si.add_definition(SymbolDefinition("login", "auth.py", 1, 10, "function"))
        # handler.py calls login()
        cg._call_sites["handler.py"] = [
            CallSite("handler.py", "handle_request", "login", None, 5, "login()"),
        ]
        analyzer = ImpactAnalyzer(cg, dg, si)
        result = analyzer.assess("auth.py")
        impact_files = [i.file_path for i in result.direct_impacts]
        assert "handler.py" in impact_files

    def test_file_path_target_combines_importers_and_callers(self, components):
        """File path target should combine both importers and symbol callers."""
        cg, dg, si = components
        # auth.py defines 'AuthService'
        si.add_definition(SymbolDefinition("AuthService", "auth.py", 1, 50, "class"))
        # api.py imports auth.py
        dg.add_edge(DependencyEdge("api.py", "auth.py", "auth", ["AuthService"]))
        # handler.py calls AuthService (but doesn't directly import auth.py)
        cg._call_sites["handler.py"] = [
            CallSite("handler.py", "process", "AuthService", None, 10, "AuthService()"),
        ]
        analyzer = ImpactAnalyzer(cg, dg, si)
        result = analyzer.assess("auth.py")
        impact_files = [i.file_path for i in result.direct_impacts]
        assert "api.py" in impact_files
        assert "handler.py" in impact_files

    def test_file_path_with_directory(self, components):
        """File paths containing directory separators should be detected."""
        cg, dg, si = components
        target = "tree_sitter_analyzer/core/analysis_engine.py"
        si.add_definition(SymbolDefinition("Engine", target, 1, 100, "class"))
        dg.add_edge(
            DependencyEdge("main.py", target, "core.analysis_engine", ["Engine"])
        )
        analyzer = ImpactAnalyzer(cg, dg, si)
        result = analyzer.assess(target)
        impact_files = [i.file_path for i in result.direct_impacts]
        assert "main.py" in impact_files

    def test_symbol_target_unchanged(self, components):
        """Symbol name targets should still work as before."""
        cg, dg, si = components
        si.add_definition(SymbolDefinition("AuthService", "auth.py", 1, 50, "class"))
        dg.add_edge(DependencyEdge("api.py", "auth.py", "auth", ["AuthService"]))
        cg._call_sites["handler.py"] = [
            CallSite("handler.py", "process", "AuthService", None, 10, "AuthService()"),
        ]
        analyzer = ImpactAnalyzer(cg, dg, si)
        result = analyzer.assess("AuthService")
        # Symbol target should find callers via call graph
        impact_files = [i.file_path for i in result.direct_impacts]
        assert "handler.py" in impact_files
        # Symbol target should find importers via definition lookup
        assert "api.py" in impact_files

    def test_file_path_transitive_impacts(self, components):
        """File path target should still produce transitive impacts."""
        cg, dg, si = components
        dg.add_edge(DependencyEdge("b.py", "a.py", "a", ["foo"]))
        dg.add_edge(DependencyEdge("c.py", "b.py", "b", ["bar"]))
        analyzer = ImpactAnalyzer(cg, dg, si)
        result = analyzer.assess("a.py", depth=3)
        trans_files = [i.file_path for i in result.transitive_impacts]
        assert "c.py" in trans_files

    def test_file_path_affected_tests(self, components):
        """File path target should detect affected test files."""
        cg, dg, si = components
        dg.add_edge(DependencyEdge("test_auth.py", "auth.py", "auth", ["login"]))
        analyzer = ImpactAnalyzer(cg, dg, si)
        result = analyzer.assess("auth.py", include_tests=True)
        assert any("test_" in t for t in result.affected_tests)
