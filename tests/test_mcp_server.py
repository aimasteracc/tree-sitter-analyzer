"""
Test MCP server initialization and basic functionality.

Following TDD: Write tests FIRST, then implement MCP server.
This is T0.3: MCP Hello World
"""

from pathlib import Path


class TestMCPServerBasics:
    """Test basic MCP server functionality."""

    def test_mcp_module_exists(self):
        """Test that MCP module can be imported."""
        # This will fail initially - that's the TDD RED phase
        from tree_sitter_analyzer_v2.mcp import server

        assert server is not None

    def test_mcp_server_class_exists(self):
        """Test that MCPServer class exists."""
        from tree_sitter_analyzer_v2.mcp.server import MCPServer

        assert MCPServer is not None

    def test_mcp_server_can_initialize(self, project_root: Path):
        """Test that MCP server can be initialized."""
        from tree_sitter_analyzer_v2.mcp.server import MCPServer

        server = MCPServer(project_root=str(project_root))
        assert server is not None
        assert server.project_root == project_root

    def test_mcp_server_has_name(self):
        """Test that MCP server has a name."""
        from tree_sitter_analyzer_v2.mcp.server import MCPServer

        server = MCPServer(project_root=".")
        assert hasattr(server, "name")
        assert server.name == "tree-sitter-analyzer-v2"

    def test_mcp_server_has_version(self):
        """Test that MCP server has a version."""
        from tree_sitter_analyzer_v2.mcp.server import MCPServer

        server = MCPServer(project_root=".")
        assert hasattr(server, "version")
        assert server.version == "2.0.0-alpha.1"


class TestMCPServerCapabilities:
    """Test MCP server capabilities."""

    def test_server_reports_capabilities(self):
        """Test that server can report its capabilities."""
        from tree_sitter_analyzer_v2.mcp.server import MCPServer

        server = MCPServer(project_root=".")
        capabilities = server.get_capabilities()

        assert isinstance(capabilities, dict)
        assert "tools" in capabilities
        assert isinstance(capabilities["tools"], list)

    def test_server_has_tools_auto_registered(self):
        """Test that server auto-registers tools (E1 enhancement)."""
        from tree_sitter_analyzer_v2.mcp.server import MCPServer

        server = MCPServer(project_root=".")
        capabilities = server.get_capabilities()

        # Core tools only (11 tree-sitter + search + graph tools)
        assert len(capabilities["tools"]) == 11

        # Verify some key tools are present
        tool_names = [t["name"] for t in capabilities["tools"]]
        assert "analyze_code_graph" in tool_names
        assert "visualize_code_graph" in tool_names


class TestMCPServerProtocol:
    """Test MCP protocol compliance."""

    def test_server_handles_initialize_request(self):
        """Test that server handles MCP initialize request."""
        from tree_sitter_analyzer_v2.mcp.server import MCPServer

        server = MCPServer(project_root=".")

        # MCP initialize request
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "0.1.0",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
        }

        response = server.handle_request(request)

        assert response is not None
        assert "jsonrpc" in response
        assert response["jsonrpc"] == "2.0"
        assert "id" in response
        assert response["id"] == 1
        assert "result" in response

        result = response["result"]
        assert "protocolVersion" in result
        assert "capabilities" in result
        assert "serverInfo" in result
        assert result["serverInfo"]["name"] == "tree-sitter-analyzer-v2"

    def test_server_handles_ping_request(self):
        """Test that server responds to ping."""
        from tree_sitter_analyzer_v2.mcp.server import MCPServer

        server = MCPServer(project_root=".")

        # First initialize
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "0.1.0",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
        }
        server.handle_request(init_request)

        # Then ping
        ping_request = {"jsonrpc": "2.0", "id": 2, "method": "ping"}

        response = server.handle_request(ping_request)

        assert response is not None
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 2
        assert "result" in response
        # Ping just returns empty object or success indicator
        assert response["result"] == {}

    def test_server_handles_unknown_method(self):
        """Test that server handles unknown methods gracefully."""
        from tree_sitter_analyzer_v2.mcp.server import MCPServer

        server = MCPServer(project_root=".")

        request = {"jsonrpc": "2.0", "id": 3, "method": "unknown_method"}

        response = server.handle_request(request)

        assert response is not None
        assert "error" in response
        assert response["error"]["code"] == -32601  # Method not found
        assert "unknown_method" in response["error"]["message"].lower()

    def test_server_handles_invalid_json_rpc(self):
        """Test that server handles invalid JSON-RPC requests."""
        from tree_sitter_analyzer_v2.mcp.server import MCPServer

        server = MCPServer(project_root=".")

        # Missing jsonrpc field
        request = {"id": 4, "method": "ping"}

        response = server.handle_request(request)

        assert response is not None
        assert "error" in response
        assert response["error"]["code"] == -32600  # Invalid request


class TestMCPServerLifecycle:
    """Test MCP server lifecycle."""

    def test_server_can_be_started_and_stopped(self):
        """Test server lifecycle management."""
        from tree_sitter_analyzer_v2.mcp.server import MCPServer

        server = MCPServer(project_root=".")

        # Server should not be initialized yet
        assert not server.is_initialized

        # Initialize
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "0.1.0",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
        }
        server.handle_request(init_request)

        # Now should be initialized
        assert server.is_initialized

        # Can handle shutdown
        shutdown_request = {"jsonrpc": "2.0", "id": 2, "method": "shutdown"}
        response = server.handle_request(shutdown_request)

        assert response["result"] is None  # Shutdown returns null

    def test_server_rejects_requests_before_initialize(self):
        """Test that server rejects requests before initialization."""
        from tree_sitter_analyzer_v2.mcp.server import MCPServer

        server = MCPServer(project_root=".")

        # Try to ping before initialization
        ping_request = {"jsonrpc": "2.0", "id": 1, "method": "ping"}

        response = server.handle_request(ping_request)

        # Should get an error
        assert "error" in response
        assert "not initialized" in response["error"]["message"].lower()
