"""
Integration tests for MCP Server with auto-registered Code Graph tools.

Tests:
1. Server initializes with all tools registered
2. tools/list returns Code Graph tools
3. Code Graph tools are callable via tools/call
4. Tool execution works end-to-end
"""

import tempfile
from pathlib import Path

from tree_sitter_analyzer_v2.mcp.server import MCPServer


class TestMCPServerRegistration:
    """Tests for MCP server tool auto-registration."""

    def test_server_initialization_registers_tools(self):
        """Test that server auto-registers all tools on initialization."""
        server = MCPServer(project_root=".")

        # Verify tool registry is created
        assert server.tool_registry is not None

        # Verify tools are registered
        tool_names = server.tool_registry.list_tools()
        assert len(tool_names) > 0

        # Verify Code Graph tools are registered
        assert "analyze_code_graph" in tool_names
        assert "find_function_callers" in tool_names
        assert "query_call_chain" in tool_names

    def test_server_capabilities_include_code_graph_tools(self):
        """Test that server capabilities include Code Graph tools."""
        server = MCPServer(project_root=".")

        capabilities = server.get_capabilities()

        # Verify tools capability exists
        assert "tools" in capabilities
        assert isinstance(capabilities["tools"], list)
        assert len(capabilities["tools"]) > 0

        # Extract tool names from schemas
        tool_names = [tool["name"] for tool in capabilities["tools"]]

        # Verify Code Graph tools are in capabilities
        assert "analyze_code_graph" in tool_names
        assert "find_function_callers" in tool_names
        assert "query_call_chain" in tool_names

    def test_tools_list_request(self):
        """Test tools/list JSON-RPC method."""
        server = MCPServer(project_root=".")

        # Initialize server first
        init_request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        init_response = server.handle_request(init_request)
        assert init_response["result"]["capabilities"]["tools"]

        # Request tools list
        list_request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        response = server.handle_request(list_request)

        # Verify response structure
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 2
        assert "result" in response
        assert "tools" in response["result"]

        # Verify Code Graph tools are listed
        tool_names = [tool["name"] for tool in response["result"]["tools"]]
        assert "analyze_code_graph" in tool_names
        assert "find_function_callers" in tool_names
        assert "query_call_chain" in tool_names

    def test_tools_call_analyze_code_graph(self):
        """Test calling analyze_code_graph tool via tools/call."""
        server = MCPServer(project_root=".")

        # Initialize server
        init_request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        server.handle_request(init_request)

        # Create temp Python file
        code = """
def helper():
    return 42

def main():
    return helper()
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            # Call analyze_code_graph tool
            call_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "analyze_code_graph",
                    "arguments": {"file_path": temp_path, "detail_level": "summary"},
                },
            }
            response = server.handle_request(call_request)

            # Verify response
            assert response["jsonrpc"] == "2.0"
            assert response["id"] == 2
            assert "result" in response
            assert response["result"]["success"] is True
            assert "statistics" in response["result"]
            assert response["result"]["statistics"]["functions"] == 2
            assert "structure" in response["result"]

        finally:
            Path(temp_path).unlink()

    def test_tools_call_find_function_callers(self):
        """Test calling find_function_callers tool via tools/call."""
        server = MCPServer(project_root=".")

        # Initialize server
        init_request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        server.handle_request(init_request)

        # Create temp Python file with function calls
        code = """
def helper():
    return 42

def main():
    return helper()

def other():
    return helper() + 1
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            # Call find_function_callers tool
            call_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "find_function_callers",
                    "arguments": {"file_path": temp_path, "function_name": "helper"},
                },
            }
            response = server.handle_request(call_request)

            # Verify response
            assert response["jsonrpc"] == "2.0"
            assert response["id"] == 2
            assert "result" in response
            assert response["result"]["success"] is True
            assert response["result"]["function_name"] == "helper"
            assert len(response["result"]["results"]) == 1
            assert response["result"]["results"][0]["caller_count"] == 2

            # Verify caller names
            caller_names = [c["name"] for c in response["result"]["results"][0]["callers"]]
            assert "main" in caller_names
            assert "other" in caller_names

        finally:
            Path(temp_path).unlink()

    def test_tools_call_query_call_chain(self):
        """Test calling query_call_chain tool via tools/call."""
        server = MCPServer(project_root=".")

        # Initialize server
        init_request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        server.handle_request(init_request)

        # Create temp Python file with call chain
        code = """
def level3():
    return "done"

def level2():
    return level3()

def level1():
    return level2()

def main():
    return level1()
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            # Call query_call_chain tool
            call_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "query_call_chain",
                    "arguments": {
                        "file_path": temp_path,
                        "start_function": "main",
                        "end_function": "level3",
                    },
                },
            }
            response = server.handle_request(call_request)

            # Verify response
            assert response["jsonrpc"] == "2.0"
            assert response["id"] == 2
            assert "result" in response
            assert response["result"]["success"] is True
            assert response["result"]["chains_found"] > 0
            assert len(response["result"]["chains"]) > 0

            # Verify call chain
            first_chain = response["result"]["chains"][0]
            assert first_chain["length"] == 4
            assert first_chain["path"] == ["main", "level1", "level2", "level3"]

        finally:
            Path(temp_path).unlink()

    def test_tools_call_invalid_tool_name(self):
        """Test error handling for invalid tool name."""
        server = MCPServer(project_root=".")

        # Initialize server
        init_request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        server.handle_request(init_request)

        # Call non-existent tool
        call_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        }
        response = server.handle_request(call_request)

        # Verify error response
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 2
        assert "error" in response
        assert response["error"]["code"] == -32602
        assert "Unknown tool" in response["error"]["message"]

    def test_all_registered_tools_count(self):
        """Test that all expected tools are registered."""
        server = MCPServer(project_root=".")

        tool_names = server.tool_registry.list_tools()

        # Expected tools:
        # Core: analyze_code_structure, query_code, check_code_scale, extract_code_section
        # Search: find_files, search_content, find_and_grep
        # Code Graph: analyze_code_graph, find_function_callers, query_call_chain, visualize_code_graph
        # Code Intelligence: code_intelligence
        # Total: 13 tools
        expected_count = 13
        assert len(tool_names) == expected_count

        # Verify all expected tools are present
        expected_tools = [
            "analyze_code_structure",
            "query_code",
            "check_code_scale",
            "extract_code_section",
            "find_files",
            "search_content",
            "find_and_grep",
            "analyze_code_graph",
            "find_function_callers",
            "query_call_chain",
            "visualize_code_graph",
            "code_intelligence",
        ]

        for tool_name in expected_tools:
            assert tool_name in tool_names, f"Missing tool: {tool_name}"
