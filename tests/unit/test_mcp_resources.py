"""
Tests for mcp/resources.py module.

TDD: Testing MCP Knowledge Resource Provider.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer_v2.mcp.resources import KnowledgeResourceProvider
from tree_sitter_analyzer_v2.features.project_knowledge import (
    ProjectKnowledgeEngine,
    ProjectSnapshot,
    FunctionInfo,
)


class TestKnowledgeResourceProvider:
    """Test KnowledgeResourceProvider."""

    def _create_mock_engine(self) -> MagicMock:
        """Create a mock ProjectKnowledgeEngine."""
        engine = MagicMock(spec=ProjectKnowledgeEngine)
        
        # Mock snapshot
        engine.snapshot = ProjectSnapshot(
            total_files=10,
            total_functions=50,
            timestamp="2024-01-01T00:00:00",
            functions={
                "main": FunctionInfo(
                    name="main",
                    file="app.py",
                    calls=["helper", "process"],
                    called_by=["init"],
                    impact_level="high",
                    impact_score=85
                ),
                "helper": FunctionInfo(
                    name="helper",
                    file="utils.py",
                    calls=[],
                    called_by=["main"],
                    impact_level="low",
                    impact_score=20
                ),
            }
        )
        
        return engine

    def test_list_resources(self) -> None:
        """Should list all available resources."""
        engine = self._create_mock_engine()
        provider = KnowledgeResourceProvider(engine)
        
        resources = provider.list_resources()
        
        assert len(resources) == 3
        uris = [r["uri"] for r in resources]
        assert "knowledge://project/snapshot" in uris
        assert "knowledge://project/hotspots" in uris
        assert "knowledge://project/stats" in uris

    def test_resource_has_required_fields(self) -> None:
        """Each resource should have uri, name, description, mimeType."""
        engine = self._create_mock_engine()
        provider = KnowledgeResourceProvider(engine)
        
        resources = provider.list_resources()
        
        for resource in resources:
            assert "uri" in resource
            assert "name" in resource
            assert "description" in resource
            assert "mimeType" in resource

    def test_read_snapshot_resource(self) -> None:
        """Should read project snapshot resource."""
        engine = self._create_mock_engine()
        engine.load_snapshot.return_value = "FUNC:main→CALLS[helper]"
        
        provider = KnowledgeResourceProvider(engine)
        content = provider.read_resource("knowledge://project/snapshot")
        
        assert "项目知识快照" in content
        assert "FUNC:main→CALLS[helper]" in content
        engine.load_snapshot.assert_called_once()

    def test_read_hotspots_resource(self) -> None:
        """Should read hotspots resource."""
        engine = self._create_mock_engine()
        engine.get_hotspots.return_value = [
            {
                "function": "main",
                "file": "app.py",
                "impact_level": "high",
                "called_by_count": 5,
                "calls_count": 3
            }
        ]
        
        provider = KnowledgeResourceProvider(engine)
        content = provider.read_resource("knowledge://project/hotspots")
        
        assert "热点函数" in content
        assert "main" in content
        engine.get_hotspots.assert_called_once_with(top_n=20)

    def test_read_stats_resource(self) -> None:
        """Should read project stats resource."""
        engine = self._create_mock_engine()
        engine._load_from_cache = MagicMock()
        
        provider = KnowledgeResourceProvider(engine)
        content = provider.read_resource("knowledge://project/stats")
        
        assert "项目统计信息" in content
        assert "总文件数" in content
        assert "总函数数" in content

    def test_read_stats_with_no_snapshot(self) -> None:
        """Should handle missing snapshot for stats."""
        engine = self._create_mock_engine()
        engine.snapshot = None
        engine._load_from_cache = MagicMock()
        
        provider = KnowledgeResourceProvider(engine)
        content = provider.read_resource("knowledge://project/stats")
        
        assert "No snapshot available" in content

    def test_read_function_impact_resource(self) -> None:
        """Should read function impact resource."""
        engine = self._create_mock_engine()
        engine.get_function_impact.return_value = {
            "function": "main",
            "file": "app.py",
            "impact_level": "high",
            "impact_score": 85,
            "callers": ["init", "startup"],
            "callees": ["helper", "process"],
            "affected_files": 3,
            "files_list": ["app.py", "utils.py", "core.py"]
        }
        
        provider = KnowledgeResourceProvider(engine)
        content = provider.read_resource("knowledge://function/main/impact")
        
        assert "函数影响分析" in content
        assert "main" in content
        assert "HIGH" in content
        engine.get_function_impact.assert_called_once_with("main")

    def test_read_function_impact_not_found(self) -> None:
        """Should handle function not found."""
        engine = self._create_mock_engine()
        engine.get_function_impact.return_value = None
        
        provider = KnowledgeResourceProvider(engine)
        content = provider.read_resource("knowledge://function/unknown_func/impact")
        
        assert "not found" in content

    def test_read_unknown_resource(self) -> None:
        """Should handle unknown resource URI."""
        engine = self._create_mock_engine()
        provider = KnowledgeResourceProvider(engine)
        
        content = provider.read_resource("knowledge://unknown/resource")
        
        assert "Unknown resource" in content

    def test_stats_impact_level_distribution(self) -> None:
        """Should show impact level distribution in stats."""
        engine = self._create_mock_engine()
        engine._load_from_cache = MagicMock()
        
        provider = KnowledgeResourceProvider(engine)
        content = provider.read_resource("knowledge://project/stats")
        
        assert "影响等级分布" in content
        assert "高影响函数" in content
        assert "中影响函数" in content
        assert "低影响函数" in content

    def test_function_impact_with_many_callers(self) -> None:
        """Should truncate long caller lists."""
        engine = self._create_mock_engine()
        engine.get_function_impact.return_value = {
            "function": "utils",
            "file": "utils.py",
            "impact_level": "high",
            "impact_score": 90,
            "callers": [f"caller{i}" for i in range(15)],  # More than 10
            "callees": [],
            "affected_files": 1,
            "files_list": ["utils.py"]
        }
        
        provider = KnowledgeResourceProvider(engine)
        content = provider.read_resource("knowledge://function/utils/impact")
        
        assert "还有" in content  # Should show truncation message

    def test_function_impact_with_many_callees(self) -> None:
        """Should truncate long callee lists."""
        engine = self._create_mock_engine()
        engine.get_function_impact.return_value = {
            "function": "main",
            "file": "main.py",
            "impact_level": "high",
            "impact_score": 90,
            "callers": [],
            "callees": [f"callee{i}" for i in range(15)],  # More than 10
            "affected_files": 1,
            "files_list": ["main.py"]
        }
        
        provider = KnowledgeResourceProvider(engine)
        content = provider.read_resource("knowledge://function/main/impact")
        
        assert "还有" in content

    def test_function_impact_with_many_files(self) -> None:
        """Should truncate long file lists."""
        engine = self._create_mock_engine()
        engine.get_function_impact.return_value = {
            "function": "core",
            "file": "core.py",
            "impact_level": "high",
            "impact_score": 90,
            "callers": [],
            "callees": [],
            "affected_files": 10,
            "files_list": [f"file{i}.py" for i in range(10)]  # More than 5
        }
        
        provider = KnowledgeResourceProvider(engine)
        content = provider.read_resource("knowledge://function/core/impact")
        
        assert "还有" in content

    def test_function_impact_no_callers(self) -> None:
        """Should handle function with no callers."""
        engine = self._create_mock_engine()
        engine.get_function_impact.return_value = {
            "function": "main",
            "file": "main.py",
            "impact_level": "low",
            "impact_score": 10,
            "callers": [],
            "callees": ["helper"],
            "affected_files": 1,
            "files_list": ["main.py"]
        }
        
        provider = KnowledgeResourceProvider(engine)
        content = provider.read_resource("knowledge://function/main/impact")
        
        assert "无调用者" in content

    def test_function_impact_no_callees(self) -> None:
        """Should handle function with no callees."""
        engine = self._create_mock_engine()
        engine.get_function_impact.return_value = {
            "function": "leaf",
            "file": "leaf.py",
            "impact_level": "low",
            "impact_score": 10,
            "callers": ["main"],
            "callees": [],
            "affected_files": 1,
            "files_list": ["leaf.py"]
        }
        
        provider = KnowledgeResourceProvider(engine)
        content = provider.read_resource("knowledge://function/leaf/impact")
        
        assert "不调用其他函数" in content
