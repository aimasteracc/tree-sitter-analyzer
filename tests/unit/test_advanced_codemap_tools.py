"""Tests for advanced code map tools"""

import pytest

from tree_sitter_analyzer_v2.mcp.tools.advanced_codemap import (
    CodeQueryTool,
    GraphStorageTool,
    GraphVisualizeTool,
    RealtimeWatchTool,
    _GLOBAL_STORAGE,
)


@pytest.fixture(autouse=True)
def clear_storage():
    """Clear global storage before each test"""
    _GLOBAL_STORAGE.clear()
    yield
    _GLOBAL_STORAGE.clear()


class TestGraphStorageTool:
    """Test graph storage tool"""

    def test_add_node(self):
        """Test adding a node"""
        tool = GraphStorageTool()
        result = tool.execute({
            "operation": "add_node",
            "node_id": "func_1",
            "node_type": "function",
            "attributes": {"name": "main", "file": "main.py"}
        })
        
        assert result["success"]
        assert "added" in result["message"].lower()

    def test_add_edge(self):
        """Test adding an edge"""
        tool = GraphStorageTool()
        
        # Add nodes first
        tool.execute({
            "operation": "add_node",
            "node_id": "func_1",
            "node_type": "function",
            "attributes": {"name": "main"}
        })
        tool.execute({
            "operation": "add_node",
            "node_id": "func_2",
            "node_type": "function",
            "attributes": {"name": "helper"}
        })
        
        # Add edge
        result = tool.execute({
            "operation": "add_edge",
            "source": "func_1",
            "target": "func_2",
            "edge_type": "calls"
        })
        
        assert result["success"]

    def test_get_node(self):
        """Test getting a node"""
        tool = GraphStorageTool()
        
        # Add node
        tool.execute({
            "operation": "add_node",
            "node_id": "func_1",
            "node_type": "function",
            "attributes": {"name": "main"}
        })
        
        # Get node
        result = tool.execute({
            "operation": "get_node",
            "node_id": "func_1"
        })
        
        assert result["success"]
        assert result["node"]["name"] == "main"

    def test_query_by_type(self):
        """Test querying by type"""
        tool = GraphStorageTool()
        
        # Add nodes
        tool.execute({
            "operation": "add_node",
            "node_id": "func_1",
            "node_type": "function",
            "attributes": {"name": "main"}
        })
        tool.execute({
            "operation": "add_node",
            "node_id": "class_1",
            "node_type": "class",
            "attributes": {"name": "User"}
        })
        
        # Query functions
        result = tool.execute({
            "operation": "query_by_type",
            "node_type": "function"
        })
        
        assert result["success"]
        assert result["count"] == 1

    def test_stats(self):
        """Test getting stats"""
        tool = GraphStorageTool()
        
        # Add some data
        tool.execute({
            "operation": "add_node",
            "node_id": "func_1",
            "node_type": "function",
            "attributes": {"name": "main"}
        })
        
        # Get stats
        result = tool.execute({
            "operation": "stats"
        })
        
        assert result["success"]
        assert result["stats"]["nodes"] >= 1

    def test_clear(self):
        """Test clearing storage"""
        tool = GraphStorageTool()
        
        # Add data
        tool.execute({
            "operation": "add_node",
            "node_id": "func_1",
            "node_type": "function",
            "attributes": {"name": "main"}
        })
        
        # Clear
        result = tool.execute({
            "operation": "clear"
        })
        
        assert result["success"]
        
        # Verify cleared
        stats = tool.execute({"operation": "stats"})
        assert stats["stats"]["nodes"] == 0


class TestCodeQueryTool:
    """Test code query tool"""

    def test_find_functions(self):
        """Test finding functions"""
        # Add test data
        storage_tool = GraphStorageTool()
        storage_tool.execute({
            "operation": "add_node",
            "node_id": "func_1",
            "node_type": "function",
            "attributes": {"name": "main"}
        })
        
        # Query
        query_tool = CodeQueryTool()
        result = query_tool.execute({
            "query": "find functions"
        })
        
        assert result["success"]
        assert result["count"] >= 1

    def test_find_with_filter(self):
        """Test finding with file filter"""
        # Add test data
        storage_tool = GraphStorageTool()
        storage_tool.execute({
            "operation": "add_node",
            "node_id": "func_1",
            "node_type": "function",
            "attributes": {"name": "main", "file": "main.py"}
        })
        storage_tool.execute({
            "operation": "add_node",
            "node_id": "func_2",
            "node_type": "function",
            "attributes": {"name": "helper", "file": "utils.py"}
        })
        
        # Query with filter
        query_tool = CodeQueryTool()
        result = query_tool.execute({
            "query": "find functions in file:main.py"
        })
        
        assert result["success"]
        assert result["count"] == 1
        assert result["results"][0]["name"] == "main"

    def test_find_with_relationship(self):
        """Test finding with relationship"""
        # Add test data
        storage_tool = GraphStorageTool()
        storage_tool.execute({
            "operation": "add_node",
            "node_id": "func_1",
            "node_type": "function",
            "attributes": {"name": "main"}
        })
        storage_tool.execute({
            "operation": "add_node",
            "node_id": "func_2",
            "node_type": "function",
            "attributes": {"name": "helper"}
        })
        storage_tool.execute({
            "operation": "add_edge",
            "source": "func_1",
            "target": "func_2",
            "edge_type": "calls"
        })
        
        # Query with relationship
        query_tool = CodeQueryTool()
        result = query_tool.execute({
            "query": "find functions called_by main"
        })
        
        assert result["success"]
        assert result["count"] == 1
        assert result["results"][0]["name"] == "helper"


class TestRealtimeWatchTool:
    """Test real-time watch tool"""

    def test_scan_nonexistent_directory(self):
        """Test scanning nonexistent directory"""
        tool = RealtimeWatchTool()
        result = tool.execute({
            "operation": "scan",
            "directory": "/nonexistent/path"
        })
        
        assert not result["success"]
        assert "not found" in result["error"].lower()

    def test_subscribe(self):
        """Test subscribing to query"""
        tool = RealtimeWatchTool()
        result = tool.execute({
            "operation": "subscribe",
            "query": "find functions with complexity > 10"
        })
        
        assert result["success"]
        assert "subscription" in result["message"].lower()


class TestGraphVisualizeTool:
    """Test graph visualization tool"""

    def test_visualize_mermaid(self):
        """Test generating Mermaid diagram"""
        # Add test data
        storage_tool = GraphStorageTool()
        storage_tool.execute({
            "operation": "add_node",
            "node_id": "func_1",
            "node_type": "function",
            "attributes": {"name": "main"}
        })
        storage_tool.execute({
            "operation": "add_node",
            "node_id": "func_2",
            "node_type": "function",
            "attributes": {"name": "helper"}
        })
        storage_tool.execute({
            "operation": "add_edge",
            "source": "func_1",
            "target": "func_2",
            "edge_type": "calls"
        })
        
        # Visualize
        viz_tool = GraphVisualizeTool()
        result = viz_tool.execute({
            "format": "mermaid",
            "layout": "hierarchical"
        })
        
        assert result["success"]
        assert "diagram" in result
        assert "graph TD" in result["diagram"] or "graph LR" in result["diagram"]

    def test_visualize_json(self):
        """Test generating JSON format"""
        # Add test data
        storage_tool = GraphStorageTool()
        storage_tool.execute({
            "operation": "add_node",
            "node_id": "func_1",
            "node_type": "function",
            "attributes": {"name": "main"}
        })
        
        # Visualize
        viz_tool = GraphVisualizeTool()
        result = viz_tool.execute({
            "format": "json"
        })
        
        assert result["success"]
        assert "graph" in result
        assert "nodes" in result["graph"]
        assert "links" in result["graph"]

    def test_visualize_with_filter(self):
        """Test visualization with filter"""
        # Add test data
        storage_tool = GraphStorageTool()
        storage_tool.execute({
            "operation": "add_node",
            "node_id": "func_1",
            "node_type": "function",
            "attributes": {"name": "main"}
        })
        storage_tool.execute({
            "operation": "add_node",
            "node_id": "class_1",
            "node_type": "class",
            "attributes": {"name": "User"}
        })
        
        # Visualize only functions
        viz_tool = GraphVisualizeTool()
        result = viz_tool.execute({
            "format": "json",
            "filter": {"by_type": "function"}
        })
        
        assert result["success"]
        assert result["node_count"] == 1
