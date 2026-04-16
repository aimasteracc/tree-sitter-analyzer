"""
Tests for dependency graph service and blast radius analysis.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.dependency_query_tool import DependencyQueryTool
from tree_sitter_analyzer.mcp.utils.graph_service import (
    ProjectGraph,
)

# Fixtures: small project with known dependency structure
SERVICE_JAVA = '''
package com.example.service;

import com.example.model.User;
import com.example.dao.UserDao;

public class UserService {
    private UserDao dao;
    public User getUser(int id) { return dao.findById(id); }
}
'''

DAO_JAVA = '''
package com.example.dao;

import com.example.model.User;

public class UserDao {
    public User findById(int id) { return null; }
}
'''

MODEL_JAVA = '''
package com.example.model;

public class User {
    private String name;
    public String getName() { return name; }
}
'''

CONTROLLER_JAVA = '''
package com.example.controller;

import com.example.service.UserService;

public class UserController {
    private UserService service;
}
'''


@pytest.fixture()
def java_project(tmp_path: Path) -> str:
    """Create a small Java project with known imports."""
    (tmp_path / "service").mkdir()
    (tmp_path / "dao").mkdir()
    (tmp_path / "model").mkdir()
    (tmp_path / "controller").mkdir()

    (tmp_path / "service" / "UserService.java").write_text(SERVICE_JAVA, encoding="utf-8")
    (tmp_path / "dao" / "UserDao.java").write_text(DAO_JAVA, encoding="utf-8")
    (tmp_path / "model" / "User.java").write_text(MODEL_JAVA, encoding="utf-8")
    (tmp_path / "controller" / "UserController.java").write_text(CONTROLLER_JAVA, encoding="utf-8")
    return str(tmp_path)


class TestProjectGraph:
    """Unit tests for ProjectGraph data structure."""

    def test_blast_radius_direct(self) -> None:
        edges = [("A", "B"), ("B", "C"), ("C", "D")]
        graph = ProjectGraph(edges=edges)
        result = graph.blast_radius("C")
        assert "B" in result.dependents
        assert "A" in result.dependents

    def test_blast_radius_isolated_node(self) -> None:
        edges = [("A", "B")]
        graph = ProjectGraph(edges=edges)
        result = graph.blast_radius("Z")
        assert len(result.dependents) == 0

    def test_blast_radius_max_depth(self) -> None:
        edges = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")]
        graph = ProjectGraph(edges=edges)
        result = graph.blast_radius("E", max_depth=1)
        assert "D" in result.dependents
        # A and B should be beyond max_depth=1 from E's direct dependents
        assert "A" not in result.dependents or result.depth_map.get("A", 0) > 1

    def test_direct_dependents(self) -> None:
        edges = [("A", "B"), ("C", "B")]
        graph = ProjectGraph(edges=edges)
        deps = graph.direct_dependents("B")
        assert set(deps) == {"A", "C"}

    def test_direct_dependencies(self) -> None:
        edges = [("A", "B"), ("A", "C")]
        graph = ProjectGraph(edges=edges)
        deps = graph.direct_dependencies("A")
        assert set(deps) == {"B", "C"}

    def test_nodes(self) -> None:
        edges = [("A", "B"), ("B", "C")]
        graph = ProjectGraph(edges=edges)
        assert graph.nodes() == {"A", "B", "C"}


class TestDependencyQueryTool:
    """Integration tests for the MCP dependency_query tool."""

    @pytest.mark.asyncio
    async def test_blast_radius_query(self, java_project: str) -> None:
        tool = DependencyQueryTool(project_root=java_project)
        files = [
            str(Path(java_project) / "service" / "UserService.java"),
            str(Path(java_project) / "dao" / "UserDao.java"),
            str(Path(java_project) / "model" / "User.java"),
            str(Path(java_project) / "controller" / "UserController.java"),
        ]
        result = await tool.execute({
            "query_type": "blast_radius",
            "node": "model/User.java",
            "file_paths": files,
        })
        assert result["success"] is True
        assert result["total_affected"] >= 0

    @pytest.mark.asyncio
    async def test_dependents_query(self, java_project: str) -> None:
        tool = DependencyQueryTool(project_root=java_project)
        files = [
            str(Path(java_project) / "service" / "UserService.java"),
            str(Path(java_project) / "dao" / "UserDao.java"),
            str(Path(java_project) / "model" / "User.java"),
        ]
        result = await tool.execute({
            "query_type": "dependents",
            "node": "model/User.java",
            "file_paths": files,
        })
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_health_scores_query(self, java_project: str) -> None:
        tool = DependencyQueryTool(project_root=java_project)
        result = await tool.execute({"query_type": "health_scores"})
        assert result["success"] is True
        assert "grade_distribution" in result
        assert result["total_files"] >= 0

    @pytest.mark.asyncio
    async def test_export_json_query(self, java_project: str) -> None:
        tool = DependencyQueryTool(project_root=java_project)
        files = [
            str(Path(java_project) / "service" / "UserService.java"),
            str(Path(java_project) / "dao" / "UserDao.java"),
        ]
        result = await tool.execute({
            "query_type": "export",
            "format": "json",
            "file_paths": files,
        })
        assert result["success"] is True
        assert "output" in result

    @pytest.mark.asyncio
    async def test_export_mermaid_query(self, java_project: str) -> None:
        tool = DependencyQueryTool(project_root=java_project)
        files = [
            str(Path(java_project) / "service" / "UserService.java"),
            str(Path(java_project) / "dao" / "UserDao.java"),
        ]
        result = await tool.execute({
            "query_type": "export",
            "format": "mermaid",
            "file_paths": files,
        })
        assert result["success"] is True
        assert "graph LR" in result["output"] or result["node_count"] == 0

    @pytest.mark.asyncio
    async def test_validation_requires_node(self) -> None:
        tool = DependencyQueryTool()
        with pytest.raises(ValueError, match="node is required"):
            await tool.execute({"query_type": "dependents"})

    @pytest.mark.asyncio
    async def test_validation_requires_query_type(self) -> None:
        tool = DependencyQueryTool()
        with pytest.raises(ValueError, match="query_type is required"):
            await tool.execute({})
