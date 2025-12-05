#!/usr/bin/env python3
"""
Additional tests for tree_sitter_analyzer.interfaces.mcp_server module.

This module provides additional test coverage for the MCP server interface,
focusing on tool call handlers and resource handlers.
Requirements: 3.1, 3.3
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tree_sitter_analyzer import __version__


class TestToolCallHandlers:
    """Test MCP server tool call handlers."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def sample_python_file(self, temp_dir):
        """Create a sample Python file for testing."""
        file_path = Path(temp_dir) / "sample.py"
        file_path.write_text("""
def hello():
    '''Say hello'''
    return "Hello, World!"

class Calculator:
    def add(self, a, b):
        return a + b
""")
        return str(file_path)

    @pytest.fixture
    def sample_java_file(self, temp_dir):
        """Create a sample Java file for testing."""
        file_path = Path(temp_dir) / "Sample.java"
        file_path.write_text("""
public class Sample {
    public int add(int a, int b) {
        return a + b;
    }
}
""")
        return str(file_path)

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_handle_call_tool_analyze_file(self, sample_python_file):
        """Test handle_call_tool with analyze_file tool."""
        from tree_sitter_analyzer.interfaces.mcp_server import (
            TreeSitterAnalyzerMCPServer,
        )

        # Create server and capture the handler
        server = TreeSitterAnalyzerMCPServer()

        # Mock the Server class to capture the decorated handlers
        handlers = {}

        def capture_decorator(name):
            def decorator(func):
                handlers[name] = func
                return func
            return decorator

        with patch("tree_sitter_analyzer.interfaces.mcp_server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server.list_resources.return_value = capture_decorator("list_resources")
            mock_server.read_resource.return_value = capture_decorator("read_resource")
            mock_server_class.return_value = mock_server

            server.create_server()

        # Test the call_tool handler
        assert "call_tool" in handlers
        call_tool_handler = handlers["call_tool"]

        # Run the handler
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                call_tool_handler("analyze_file", {"file_path": sample_python_file})
            )
            assert len(result) == 1
            # Parse the JSON result
            result_data = json.loads(result[0].text)
            assert "error" not in result_data or result_data.get("success", True)
        finally:
            loop.close()

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_handle_call_tool_analyze_code(self):
        """Test handle_call_tool with analyze_code tool."""
        from tree_sitter_analyzer.interfaces.mcp_server import (
            TreeSitterAnalyzerMCPServer,
        )

        server = TreeSitterAnalyzerMCPServer()
        handlers = {}

        def capture_decorator(name):
            def decorator(func):
                handlers[name] = func
                return func
            return decorator

        with patch("tree_sitter_analyzer.interfaces.mcp_server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server.list_resources.return_value = capture_decorator("list_resources")
            mock_server.read_resource.return_value = capture_decorator("read_resource")
            mock_server_class.return_value = mock_server

            server.create_server()

        call_tool_handler = handlers["call_tool"]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                call_tool_handler("analyze_code", {
                    "source_code": "def hello(): pass",
                    "language": "python"
                })
            )
            assert len(result) == 1
            result_data = json.loads(result[0].text)
            assert isinstance(result_data, dict)
        finally:
            loop.close()

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_handle_call_tool_extract_elements(self, sample_python_file):
        """Test handle_call_tool with extract_elements tool."""
        from tree_sitter_analyzer.interfaces.mcp_server import (
            TreeSitterAnalyzerMCPServer,
        )

        server = TreeSitterAnalyzerMCPServer()
        handlers = {}

        def capture_decorator(name):
            def decorator(func):
                handlers[name] = func
                return func
            return decorator

        with patch("tree_sitter_analyzer.interfaces.mcp_server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server.list_resources.return_value = capture_decorator("list_resources")
            mock_server.read_resource.return_value = capture_decorator("read_resource")
            mock_server_class.return_value = mock_server

            server.create_server()

        call_tool_handler = handlers["call_tool"]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                call_tool_handler("extract_elements", {"file_path": sample_python_file})
            )
            assert len(result) == 1
            result_data = json.loads(result[0].text)
            assert isinstance(result_data, dict)
        finally:
            loop.close()

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_handle_call_tool_execute_query(self, sample_python_file):
        """Test handle_call_tool with execute_query tool."""
        from tree_sitter_analyzer.interfaces.mcp_server import (
            TreeSitterAnalyzerMCPServer,
        )

        server = TreeSitterAnalyzerMCPServer()
        handlers = {}

        def capture_decorator(name):
            def decorator(func):
                handlers[name] = func
                return func
            return decorator

        with patch("tree_sitter_analyzer.interfaces.mcp_server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server.list_resources.return_value = capture_decorator("list_resources")
            mock_server.read_resource.return_value = capture_decorator("read_resource")
            mock_server_class.return_value = mock_server

            server.create_server()

        call_tool_handler = handlers["call_tool"]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                call_tool_handler("execute_query", {
                    "file_path": sample_python_file,
                    "query_name": "functions"
                })
            )
            assert len(result) == 1
            result_data = json.loads(result[0].text)
            assert isinstance(result_data, dict)
        finally:
            loop.close()

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_handle_call_tool_validate_file(self, sample_python_file):
        """Test handle_call_tool with validate_file tool."""
        from tree_sitter_analyzer.interfaces.mcp_server import (
            TreeSitterAnalyzerMCPServer,
        )

        server = TreeSitterAnalyzerMCPServer()
        handlers = {}

        def capture_decorator(name):
            def decorator(func):
                handlers[name] = func
                return func
            return decorator

        with patch("tree_sitter_analyzer.interfaces.mcp_server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server.list_resources.return_value = capture_decorator("list_resources")
            mock_server.read_resource.return_value = capture_decorator("read_resource")
            mock_server_class.return_value = mock_server

            server.create_server()

        call_tool_handler = handlers["call_tool"]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                call_tool_handler("validate_file", {"file_path": sample_python_file})
            )
            assert len(result) == 1
            result_data = json.loads(result[0].text)
            assert isinstance(result_data, dict)
        finally:
            loop.close()

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_handle_call_tool_get_supported_languages(self):
        """Test handle_call_tool with get_supported_languages tool."""
        from tree_sitter_analyzer.interfaces.mcp_server import (
            TreeSitterAnalyzerMCPServer,
        )

        server = TreeSitterAnalyzerMCPServer()
        handlers = {}

        def capture_decorator(name):
            def decorator(func):
                handlers[name] = func
                return func
            return decorator

        with patch("tree_sitter_analyzer.interfaces.mcp_server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server.list_resources.return_value = capture_decorator("list_resources")
            mock_server.read_resource.return_value = capture_decorator("read_resource")
            mock_server_class.return_value = mock_server

            server.create_server()

        call_tool_handler = handlers["call_tool"]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                call_tool_handler("get_supported_languages", {})
            )
            assert len(result) == 1
            result_data = json.loads(result[0].text)
            assert "languages" in result_data
            assert "total" in result_data
            assert isinstance(result_data["languages"], list)
        finally:
            loop.close()

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_handle_call_tool_get_available_queries(self):
        """Test handle_call_tool with get_available_queries tool."""
        from tree_sitter_analyzer.interfaces.mcp_server import (
            TreeSitterAnalyzerMCPServer,
        )

        server = TreeSitterAnalyzerMCPServer()
        handlers = {}

        def capture_decorator(name):
            def decorator(func):
                handlers[name] = func
                return func
            return decorator

        with patch("tree_sitter_analyzer.interfaces.mcp_server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server.list_resources.return_value = capture_decorator("list_resources")
            mock_server.read_resource.return_value = capture_decorator("read_resource")
            mock_server_class.return_value = mock_server

            server.create_server()

        call_tool_handler = handlers["call_tool"]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                call_tool_handler("get_available_queries", {"language": "python"})
            )
            assert len(result) == 1
            result_data = json.loads(result[0].text)
            assert "language" in result_data
            assert "queries" in result_data
            assert "total" in result_data
        finally:
            loop.close()

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_handle_call_tool_get_framework_info(self):
        """Test handle_call_tool with get_framework_info tool."""
        from tree_sitter_analyzer.interfaces.mcp_server import (
            TreeSitterAnalyzerMCPServer,
        )

        server = TreeSitterAnalyzerMCPServer()
        handlers = {}

        def capture_decorator(name):
            def decorator(func):
                handlers[name] = func
                return func
            return decorator

        with patch("tree_sitter_analyzer.interfaces.mcp_server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server.list_resources.return_value = capture_decorator("list_resources")
            mock_server.read_resource.return_value = capture_decorator("read_resource")
            mock_server_class.return_value = mock_server

            server.create_server()

        call_tool_handler = handlers["call_tool"]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                call_tool_handler("get_framework_info", {})
            )
            assert len(result) == 1
            result_data = json.loads(result[0].text)
            assert isinstance(result_data, dict)
        finally:
            loop.close()

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_handle_call_tool_unknown_tool(self):
        """Test handle_call_tool with unknown tool name returns error."""
        from tree_sitter_analyzer.interfaces.mcp_server import (
            TreeSitterAnalyzerMCPServer,
        )

        server = TreeSitterAnalyzerMCPServer()
        handlers = {}

        def capture_decorator(name):
            def decorator(func):
                handlers[name] = func
                return func
            return decorator

        with patch("tree_sitter_analyzer.interfaces.mcp_server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server.list_resources.return_value = capture_decorator("list_resources")
            mock_server.read_resource.return_value = capture_decorator("read_resource")
            mock_server_class.return_value = mock_server

            server.create_server()

        call_tool_handler = handlers["call_tool"]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                call_tool_handler("unknown_tool", {})
            )
            assert len(result) == 1
            result_data = json.loads(result[0].text)
            assert "error" in result_data
            assert result_data["success"] is False
            assert "Unknown tool" in result_data["error"]
        finally:
            loop.close()

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_handle_call_tool_error_handling(self):
        """Test handle_call_tool error handling for invalid arguments."""
        from tree_sitter_analyzer.interfaces.mcp_server import (
            TreeSitterAnalyzerMCPServer,
        )

        server = TreeSitterAnalyzerMCPServer()
        handlers = {}

        def capture_decorator(name):
            def decorator(func):
                handlers[name] = func
                return func
            return decorator

        with patch("tree_sitter_analyzer.interfaces.mcp_server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server.list_resources.return_value = capture_decorator("list_resources")
            mock_server.read_resource.return_value = capture_decorator("read_resource")
            mock_server_class.return_value = mock_server

            server.create_server()

        call_tool_handler = handlers["call_tool"]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Test with missing required argument
            result = loop.run_until_complete(
                call_tool_handler("analyze_file", {})  # Missing file_path
            )
            assert len(result) == 1
            result_data = json.loads(result[0].text)
            assert "error" in result_data
            assert result_data["success"] is False
        finally:
            loop.close()


class TestResourceHandlers:
    """Test MCP server resource handlers."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def sample_python_file(self, temp_dir):
        """Create a sample Python file for testing."""
        file_path = Path(temp_dir) / "sample.py"
        file_path.write_text("def hello(): pass")
        return str(file_path)

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_handle_list_resources(self):
        """Test handle_list_resources returns expected resources."""
        from tree_sitter_analyzer.interfaces.mcp_server import (
            TreeSitterAnalyzerMCPServer,
        )

        server = TreeSitterAnalyzerMCPServer()
        handlers = {}

        def capture_decorator(name):
            def decorator(func):
                handlers[name] = func
                return func
            return decorator

        with patch("tree_sitter_analyzer.interfaces.mcp_server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server.list_resources.return_value = capture_decorator("list_resources")
            mock_server.read_resource.return_value = capture_decorator("read_resource")
            mock_server_class.return_value = mock_server

            server.create_server()

        list_resources_handler = handlers["list_resources"]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(list_resources_handler())
            assert len(result) == 2
            # Check resource URIs (may be URL-encoded)
            uris = [str(r.uri) for r in result]
            assert any("code://file/" in uri for uri in uris)
            assert any("code://stats/" in uri for uri in uris)
        finally:
            loop.close()

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_handle_read_resource_file(self, sample_python_file):
        """Test handle_read_resource with file URI."""
        from tree_sitter_analyzer.interfaces.mcp_server import (
            TreeSitterAnalyzerMCPServer,
        )

        server = TreeSitterAnalyzerMCPServer()
        handlers = {}

        def capture_decorator(name):
            def decorator(func):
                handlers[name] = func
                return func
            return decorator

        with patch("tree_sitter_analyzer.interfaces.mcp_server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server.list_resources.return_value = capture_decorator("list_resources")
            mock_server.read_resource.return_value = capture_decorator("read_resource")
            mock_server_class.return_value = mock_server

            server.create_server()

        read_resource_handler = handlers["read_resource"]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                read_resource_handler(f"code://file/{sample_python_file}")
            )
            result_data = json.loads(result)
            assert isinstance(result_data, dict)
        finally:
            loop.close()

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_handle_read_resource_stats_framework(self):
        """Test handle_read_resource with stats/framework URI."""
        from tree_sitter_analyzer.interfaces.mcp_server import (
            TreeSitterAnalyzerMCPServer,
        )

        server = TreeSitterAnalyzerMCPServer()
        handlers = {}

        def capture_decorator(name):
            def decorator(func):
                handlers[name] = func
                return func
            return decorator

        with patch("tree_sitter_analyzer.interfaces.mcp_server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server.list_resources.return_value = capture_decorator("list_resources")
            mock_server.read_resource.return_value = capture_decorator("read_resource")
            mock_server_class.return_value = mock_server

            server.create_server()

        read_resource_handler = handlers["read_resource"]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                read_resource_handler("code://stats/framework")
            )
            result_data = json.loads(result)
            assert isinstance(result_data, dict)
        finally:
            loop.close()

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_handle_read_resource_stats_languages(self):
        """Test handle_read_resource with stats/languages URI."""
        from tree_sitter_analyzer.interfaces.mcp_server import (
            TreeSitterAnalyzerMCPServer,
        )

        server = TreeSitterAnalyzerMCPServer()
        handlers = {}

        def capture_decorator(name):
            def decorator(func):
                handlers[name] = func
                return func
            return decorator

        with patch("tree_sitter_analyzer.interfaces.mcp_server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server.list_resources.return_value = capture_decorator("list_resources")
            mock_server.read_resource.return_value = capture_decorator("read_resource")
            mock_server_class.return_value = mock_server

            server.create_server()

        read_resource_handler = handlers["read_resource"]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                read_resource_handler("code://stats/languages")
            )
            result_data = json.loads(result)
            assert "supported_languages" in result_data
            assert "total_languages" in result_data
        finally:
            loop.close()

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_handle_read_resource_unknown_stats_type(self):
        """Test handle_read_resource with unknown stats type returns error."""
        from tree_sitter_analyzer.interfaces.mcp_server import (
            TreeSitterAnalyzerMCPServer,
        )

        server = TreeSitterAnalyzerMCPServer()
        handlers = {}

        def capture_decorator(name):
            def decorator(func):
                handlers[name] = func
                return func
            return decorator

        with patch("tree_sitter_analyzer.interfaces.mcp_server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server.list_resources.return_value = capture_decorator("list_resources")
            mock_server.read_resource.return_value = capture_decorator("read_resource")
            mock_server_class.return_value = mock_server

            server.create_server()

        read_resource_handler = handlers["read_resource"]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                read_resource_handler("code://stats/unknown_type")
            )
            result_data = json.loads(result)
            assert "error" in result_data
            assert result_data["success"] is False
        finally:
            loop.close()

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_handle_read_resource_unknown_uri(self):
        """Test handle_read_resource with unknown URI returns error."""
        from tree_sitter_analyzer.interfaces.mcp_server import (
            TreeSitterAnalyzerMCPServer,
        )

        server = TreeSitterAnalyzerMCPServer()
        handlers = {}

        def capture_decorator(name):
            def decorator(func):
                handlers[name] = func
                return func
            return decorator

        with patch("tree_sitter_analyzer.interfaces.mcp_server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server.list_resources.return_value = capture_decorator("list_resources")
            mock_server.read_resource.return_value = capture_decorator("read_resource")
            mock_server_class.return_value = mock_server

            server.create_server()

        read_resource_handler = handlers["read_resource"]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                read_resource_handler("unknown://resource")
            )
            result_data = json.loads(result)
            assert "error" in result_data
            assert result_data["success"] is False
            assert "Resource not found" in result_data["error"]
        finally:
            loop.close()


class TestListToolsHandler:
    """Test MCP server list_tools handler."""

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_handle_list_tools(self):
        """Test handle_list_tools returns all expected tools."""
        from tree_sitter_analyzer.interfaces.mcp_server import (
            TreeSitterAnalyzerMCPServer,
        )

        server = TreeSitterAnalyzerMCPServer()
        handlers = {}

        def capture_decorator(name):
            def decorator(func):
                handlers[name] = func
                return func
            return decorator

        with patch("tree_sitter_analyzer.interfaces.mcp_server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server.list_resources.return_value = capture_decorator("list_resources")
            mock_server.read_resource.return_value = capture_decorator("read_resource")
            mock_server_class.return_value = mock_server

            server.create_server()

        list_tools_handler = handlers["list_tools"]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(list_tools_handler())
            assert len(result) == 8  # 8 tools defined
            tool_names = [t.name for t in result]
            expected_tools = [
                "analyze_file",
                "analyze_code",
                "extract_elements",
                "execute_query",
                "validate_file",
                "get_supported_languages",
                "get_available_queries",
                "get_framework_info",
            ]
            for tool_name in expected_tools:
                assert tool_name in tool_names
        finally:
            loop.close()
