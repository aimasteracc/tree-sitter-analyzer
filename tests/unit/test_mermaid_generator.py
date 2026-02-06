"""
Tests for utils/mermaid_generator.py module.

TDD: Testing Mermaid diagram generation.
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import pytest

from tree_sitter_analyzer_v2.utils.mermaid_generator import (
    MermaidGenerator,
    quick_architecture,
    quick_heatmap,
    quick_call_graph,
)


# Mock PerformanceHotspot for testing
@dataclass
class MockPerformanceHotspot:
    function: str
    complexity: int
    hotspot_score: float


# Mock TechDebt for testing
@dataclass
class MockTechDebt:
    severity: str


class TestMermaidGenerator:
    """Test MermaidGenerator class."""

    def test_generate_architecture_basic(self) -> None:
        """Should generate basic architecture diagram."""
        diagram = MermaidGenerator.generate_architecture_diagram(
            modules={},
            entry_points=[]
        )
        
        assert "graph TD" in diagram
        assert "Root[Project Root]" in diagram

    def test_generate_architecture_with_cli(self) -> None:
        """Should include CLI in architecture diagram."""
        diagram = MermaidGenerator.generate_architecture_diagram(
            modules={},
            entry_points=[],
            has_cli=True
        )
        
        assert "CLI[CLI Entry]" in diagram
        assert "Core[Core Module]" in diagram

    def test_generate_architecture_with_api(self) -> None:
        """Should include API in architecture diagram."""
        diagram = MermaidGenerator.generate_architecture_diagram(
            modules={},
            entry_points=[],
            has_api=True
        )
        
        assert "API[API Layer]" in diagram

    def test_generate_architecture_with_mcp(self) -> None:
        """Should include MCP in architecture diagram."""
        diagram = MermaidGenerator.generate_architecture_diagram(
            modules={},
            entry_points=[],
            has_mcp=True
        )
        
        assert "MCP[MCP Server]" in diagram
        assert "Tools[Analysis Tools]" in diagram

    def test_generate_architecture_with_features(self) -> None:
        """Should include features module."""
        diagram = MermaidGenerator.generate_architecture_diagram(
            modules={"features": {}},
            entry_points=[]
        )
        
        assert "Features[Feature Modules]" in diagram

    def test_generate_call_graph_empty(self) -> None:
        """Should generate empty call graph."""
        diagram = MermaidGenerator.generate_call_graph_diagram([])
        assert "graph LR" in diagram

    def test_generate_call_graph_with_hotspots(self) -> None:
        """Should generate call graph with hotspots."""
        hotspots = [
            {
                "function": "process_data",
                "impact_score": 100,
                "called_by_count": 5,
                "calls_count": 3,
                "impact_level": "high"
            },
            {
                "function": "helper_func",
                "impact_score": 20,
                "called_by_count": 2,
                "calls_count": 1,
                "impact_level": "low"
            }
        ]
        
        diagram = MermaidGenerator.generate_call_graph_diagram(hotspots)
        
        assert "graph LR" in diagram
        assert "process_data" in diagram
        assert "5 callers" in diagram

    def test_generate_call_graph_limits_nodes(self) -> None:
        """Should limit nodes in call graph."""
        hotspots = [
            {"function": f"func{i}", "impact_score": i}
            for i in range(20)
        ]
        
        diagram = MermaidGenerator.generate_call_graph_diagram(hotspots, max_nodes=5)
        
        # Should contain top 5 by impact score
        assert "func19" in diagram

    def test_generate_heatmap_empty(self) -> None:
        """Should generate empty heatmap."""
        diagram = MermaidGenerator.generate_heatmap_diagram([])
        assert "graph TD" in diagram
        assert "PerformanceHotspots" in diagram

    def test_generate_heatmap_with_hotspots(self) -> None:
        """Should generate heatmap with hotspots."""
        hotspots = [
            MockPerformanceHotspot("high_func", 20, 100.0),
            MockPerformanceHotspot("medium_func", 10, 60.0),
            MockPerformanceHotspot("low_func", 5, 30.0),
        ]
        
        diagram = MermaidGenerator.generate_heatmap_diagram(hotspots)
        
        assert "high_func" in diagram
        assert "Complexity: 20" in diagram
        assert "fill:#ff4757" in diagram  # High severity color

    def test_generate_coverage_map(self) -> None:
        """Should generate coverage map."""
        coverage_data = {
            "module_a": 90.0,
            "module_b": 60.0,
            "module_c": 30.0,
        }
        modules = ["module_a", "module_b", "module_c"]
        
        diagram = MermaidGenerator.generate_coverage_map(coverage_data, modules)
        
        assert "CoverageMap" in diagram
        assert "90%" in diagram
        assert "fill:#2ed573" in diagram  # High coverage color
        assert "fill:#ff4757" in diagram  # Low coverage color

    def test_generate_dependency_health_basic(self) -> None:
        """Should generate dependency health diagram."""
        dependencies = {
            "module_a": ["module_b", "module_c"],
            "module_b": ["module_c"],
        }
        
        diagram = MermaidGenerator.generate_dependency_health_diagram(dependencies, [])
        
        assert "graph TD" in diagram
        assert "module_a" in diagram
        assert "-->" in diagram

    def test_generate_dependency_health_with_cycles(self) -> None:
        """Should highlight cycles in diagram."""
        dependencies = {
            "module_a": ["module_b"],
            "module_b": ["module_a"],
        }
        cycles = [["module_a", "module_b"]]
        
        diagram = MermaidGenerator.generate_dependency_health_diagram(dependencies, cycles)
        
        assert "Cycles" in diagram
        assert "fill:#ff6b6b" in diagram

    def test_generate_evolution_timeline(self) -> None:
        """Should generate evolution timeline."""
        snapshots = [
            {"date": "2024-01", "files": 10, "functions": 50},
            {"date": "2024-02", "files": 15, "functions": 80},
        ]
        
        diagram = MermaidGenerator.generate_evolution_timeline(snapshots)
        
        assert "graph LR" in diagram
        assert "2024-01" in diagram
        assert "10 files" in diagram
        assert "V0 --> V1" in diagram

    def test_generate_learning_path(self) -> None:
        """Should generate learning path diagram."""
        learning_path = [
            "main.py - Entry point",
            "core/engine.py - Core logic",
            "utils/helpers.py - Utility functions",
        ]
        
        diagram = MermaidGenerator.generate_learning_path_diagram(learning_path)
        
        assert "graph TD" in diagram
        assert "Start[Start Here]" in diagram
        assert "main.py" in diagram
        assert "Step1 --> Step2" in diagram

    def test_generate_tech_debt_breakdown(self) -> None:
        """Should generate tech debt breakdown."""
        debts = [
            MockTechDebt("high"),
            MockTechDebt("high"),
            MockTechDebt("medium"),
            MockTechDebt("low"),
        ]
        
        diagram = MermaidGenerator.generate_tech_debt_breakdown(debts)
        
        assert "Technical Debt" in diagram
        assert "High Severity" in diagram
        assert "2 items" in diagram  # 2 high severity items

    def test_generate_comparison_diagram(self) -> None:
        """Should generate comparison diagram."""
        project_a = {"name": "Project A", "files": 100, "functions": 500, "complexity": 50, "debt": 10}
        project_b = {"name": "Project B", "files": 200, "functions": 1000, "complexity": 80, "debt": 25}
        
        diagram = MermaidGenerator.generate_comparison_diagram(project_a, project_b)
        
        assert "graph LR" in diagram
        assert "Project A" in diagram
        assert "Project B" in diagram
        assert "Comparison" in diagram


class TestQuickFunctions:
    """Test convenience functions."""

    def test_quick_architecture(self) -> None:
        """Should generate quick architecture diagram."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create cli directory
            (Path(tmpdir) / "cli").mkdir()
            
            diagram = quick_architecture(Path(tmpdir))
            
            assert "CLI" in diagram

    def test_quick_heatmap(self) -> None:
        """Should generate quick heatmap."""
        hotspots = [MockPerformanceHotspot("func", 10, 50.0)]
        
        diagram = quick_heatmap(hotspots)
        
        assert "func" in diagram

    def test_quick_call_graph(self) -> None:
        """Should generate quick call graph."""
        hotspots = [{"function": "main", "impact_score": 100}]
        
        diagram = quick_call_graph(hotspots)
        
        assert "main" in diagram
