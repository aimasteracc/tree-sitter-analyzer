"""Tests for MCP Server implementation."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer_v2.mcp.server import MCPServer


class TestMCPServerInit:
    """Tests for MCPServer initialization."""

    def test_init_basic(self) -> None:
        """Test basic server initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            assert server.project_root == Path(tmpdir).resolve()
            assert server.name == "tree-sitter-analyzer-v2"
            assert server.version == "2.0.0-alpha.1"
            assert server.is_initialized is False

    def test_init_registers_tools(self) -> None:
        """Test that initialization registers tools."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            # Should have many tools registered
            tools = server.tool_registry.get_all_schemas()
            assert len(tools) > 30  # We have many tools

    def test_get_capabilities(self) -> None:
        """Test get_capabilities returns tool schemas."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            capabilities = server.get_capabilities()
            assert "tools" in capabilities
            assert isinstance(capabilities["tools"], list)


class TestMCPServerHandleRequest:
    """Tests for handle_request method."""

    def test_missing_jsonrpc_field(self) -> None:
        """Test error on missing jsonrpc field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            result = server.handle_request({"method": "ping"})
            assert "error" in result
            assert result["error"]["code"] == -32600

    def test_invalid_jsonrpc_version(self) -> None:
        """Test error on invalid jsonrpc version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            result = server.handle_request({
                "jsonrpc": "1.0",
                "method": "ping",
                "id": 1
            })
            assert "error" in result
            assert result["error"]["code"] == -32600
            assert "unsupported jsonrpc version" in result["error"]["message"]

    def test_unknown_method(self) -> None:
        """Test error on unknown method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            result = server.handle_request({
                "jsonrpc": "2.0",
                "method": "unknown_method",
                "id": 1
            })
            assert "error" in result
            assert result["error"]["code"] == -32601
            assert "not found" in result["error"]["message"]

    def test_initialize_request(self) -> None:
        """Test initialize request."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            result = server.handle_request({
                "jsonrpc": "2.0",
                "method": "initialize",
                "id": 1
            })
            assert "result" in result
            assert result["result"]["serverInfo"]["name"] == "tree-sitter-analyzer-v2"
            assert server.is_initialized is True

    def test_shutdown_request(self) -> None:
        """Test shutdown request."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            server.is_initialized = True
            
            result = server.handle_request({
                "jsonrpc": "2.0",
                "method": "shutdown",
                "id": 1
            })
            
            assert "result" in result
            assert result["result"] is None
            assert server.is_initialized is False

    def test_ping_before_init(self) -> None:
        """Test ping before initialization fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            result = server.handle_request({
                "jsonrpc": "2.0",
                "method": "ping",
                "id": 1
            })
            assert "error" in result
            assert result["error"]["code"] == -32002
            assert "not initialized" in result["error"]["message"].lower()

    def test_ping_after_init(self) -> None:
        """Test ping after initialization succeeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            server.is_initialized = True
            
            result = server.handle_request({
                "jsonrpc": "2.0",
                "method": "ping",
                "id": 1
            })
            
            assert "result" in result
            assert result["result"] == {}

    def test_tools_list_before_init(self) -> None:
        """Test tools/list before initialization fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            result = server.handle_request({
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1
            })
            assert "error" in result

    def test_tools_list_after_init(self) -> None:
        """Test tools/list after initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            server.is_initialized = True
            
            result = server.handle_request({
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1
            })
            
            assert "result" in result
            assert "tools" in result["result"]
            assert len(result["result"]["tools"]) > 0


class TestMCPServerToolsCall:
    """Tests for tools/call handling."""

    def test_tools_call_missing_name(self) -> None:
        """Test tools/call with missing tool name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            server.is_initialized = True
            
            result = server.handle_request({
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 1,
                "params": {}
            })
            
            assert "error" in result
            assert result["error"]["code"] == -32602
            assert "name" in result["error"]["message"]

    def test_tools_call_unknown_tool(self) -> None:
        """Test tools/call with unknown tool name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            server.is_initialized = True
            
            result = server.handle_request({
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 1,
                "params": {"name": "nonexistent_tool"}
            })
            
            assert "error" in result
            assert result["error"]["code"] == -32602

    def test_tools_call_success(self) -> None:
        """Test successful tools/call."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "test.py").write_text("x = 1\n")
            
            server = MCPServer(tmpdir)
            server.is_initialized = True
            
            result = server.handle_request({
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 1,
                "params": {
                    "name": "find_files",
                    "arguments": {"roots": [tmpdir], "extensions": ["py"]}
                }
            })
            
            assert "result" in result

    def test_tools_call_with_error(self) -> None:
        """Test tools/call that throws exception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            server.is_initialized = True
            
            # Mock tool that raises exception
            mock_tool = MagicMock()
            mock_tool.execute.side_effect = Exception("Tool error")
            server.tool_registry._tools["mock_tool"] = mock_tool
            
            result = server.handle_request({
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 1,
                "params": {"name": "mock_tool", "arguments": {}}
            })
            
            assert "error" in result
            assert result["error"]["code"] == -32603
            assert "execution failed" in result["error"]["message"].lower()


class TestMCPServerResources:
    """Tests for resource handling."""

    def test_resources_list(self) -> None:
        """Test resources/list request."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            server.is_initialized = True
            
            result = server.handle_request({
                "jsonrpc": "2.0",
                "method": "resources/list",
                "id": 1
            })
            
            assert "result" in result
            assert "resources" in result["result"]

    def test_resources_read_missing_uri(self) -> None:
        """Test resources/read with missing URI."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            server.is_initialized = True
            
            result = server.handle_request({
                "jsonrpc": "2.0",
                "method": "resources/read",
                "id": 1,
                "params": {}
            })
            
            assert "error" in result
            assert result["error"]["code"] == -32602
            assert "uri" in result["error"]["message"]

    def test_resources_read_invalid_uri(self) -> None:
        """Test resources/read with invalid URI returns result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            server.is_initialized = True
            
            result = server.handle_request({
                "jsonrpc": "2.0",
                "method": "resources/read",
                "id": 1,
                "params": {"uri": "invalid://uri"}
            })
            
            # Resource provider handles unknown URIs gracefully
            assert "result" in result
            assert "contents" in result["result"]


class TestMCPServerErrorResponse:
    """Tests for error response generation."""

    def test_error_response_format(self) -> None:
        """Test error response format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            response = server._error_response(123, -32600, "Test error")
            
            assert response["jsonrpc"] == "2.0"
            assert response["id"] == 123
            assert response["error"]["code"] == -32600
            assert response["error"]["message"] == "Test error"

    def test_error_response_with_none_id(self) -> None:
        """Test error response with None request ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            response = server._error_response(None, -32600, "Error")
            
            assert response["id"] is None


class TestMCPServerKnowledgeInit:
    """Tests for knowledge snapshot initialization."""

    @patch.object(MCPServer, "_init_knowledge_snapshot")
    def test_init_calls_knowledge_init(self, mock_init) -> None:
        """Test that __init__ calls _init_knowledge_snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            MCPServer(tmpdir)
            mock_init.assert_called_once()

    def test_knowledge_init_with_cache(self) -> None:
        """Test knowledge init when cache exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(tmpdir)
            # Knowledge engine should be initialized
            assert server.knowledge_engine is not None

    def test_knowledge_init_handles_error(self) -> None:
        """Test knowledge init handles errors gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Should not raise even if knowledge init fails
            server = MCPServer(tmpdir)
            assert server is not None


class TestTreeSitterAnalyzerMCPServer:
    """Tests for TreeSitterAnalyzerMCPServer class."""

    def test_import_when_mcp_not_available(self) -> None:
        """Test import error when MCP is not available."""
        from tree_sitter_analyzer_v2.mcp.server import MCP_AVAILABLE
        
        if not MCP_AVAILABLE:
            from tree_sitter_analyzer_v2.mcp.server import TreeSitterAnalyzerMCPServer
            with pytest.raises(ImportError):
                with tempfile.TemporaryDirectory() as tmpdir:
                    TreeSitterAnalyzerMCPServer(tmpdir)

    def test_mcp_available_constant(self) -> None:
        """Test MCP_AVAILABLE constant is defined."""
        from tree_sitter_analyzer_v2.mcp.server import MCP_AVAILABLE
        assert isinstance(MCP_AVAILABLE, bool)
