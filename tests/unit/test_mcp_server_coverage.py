import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

# Mock mcp module if not available
try:
    from mcp.types import Resource, TextContent, Tool

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

    # Define dummy classes for testing when MCP is not installed
    class Tool:
        def __init__(self, name, description, inputSchema):
            self.name = name
            self.description = description
            self.inputSchema = inputSchema

    class TextContent:
        def __init__(self, type, text):
            self.type = type
            self.text = text

    class Resource:
        def __init__(self, uri, name, description, mimeType):
            self.uri = uri
            self.name = name
            self.description = description
            self.mimeType = mimeType


from tree_sitter_analyzer.interfaces.mcp_server import TreeSitterAnalyzerMCPServer


class TestMCPServerCoverage(unittest.TestCase):
    def setUp(self):
        if not MCP_AVAILABLE:
            # Patch sys.modules to include mcp modules if they are missing
            # This is needed for the imports in mcp_server.py to work if we force the flag
            pass

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.interfaces.mcp_server.Server")
    def test_list_tools_handler(self, mock_server_cls):
        """Test list_tools handler logic"""
        mock_server_instance = MagicMock()
        mock_server_cls.return_value = mock_server_instance

        # Capture the list_tools handler
        list_tools_handler = None

        def list_tools_decorator():
            def decorator(func):
                nonlocal list_tools_handler
                list_tools_handler = func
                return func

            return decorator

        mock_server_instance.list_tools.side_effect = list_tools_decorator

        server = TreeSitterAnalyzerMCPServer()
        server.create_server()

        # Execute the captured handler
        if list_tools_handler:
            tools = asyncio.run(list_tools_handler())
            self.assertTrue(len(tools) > 0)
            tool_names = [t.name for t in tools]
            self.assertIn("analyze_file", tool_names)
            self.assertIn("analyze_code", tool_names)

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.interfaces.mcp_server.Server")
    @patch("tree_sitter_analyzer.interfaces.mcp_server.api")
    def test_call_tool_handler(self, mock_api, mock_server_cls):
        """Test call_tool handler logic"""
        mock_server_instance = MagicMock()
        mock_server_cls.return_value = mock_server_instance

        # Capture the call_tool handler
        call_tool_handler = None

        def call_tool_decorator():
            def decorator(func):
                nonlocal call_tool_handler
                call_tool_handler = func
                return func

            return decorator

        mock_server_instance.call_tool.side_effect = call_tool_decorator

        server = TreeSitterAnalyzerMCPServer()
        server.create_server()

        if call_tool_handler:
            # Test analyze_file
            mock_api.analyze_file.return_value = {"result": "success"}
            result = asyncio.run(
                call_tool_handler("analyze_file", {"file_path": "test.py"})
            )
            self.assertEqual(result[0].type, "text")
            self.assertIn('"result": "success"', result[0].text)

            # Test analyze_code
            mock_api.analyze_code.return_value = {"result": "code"}
            result = asyncio.run(
                call_tool_handler(
                    "analyze_code", {"source_code": "code", "language": "py"}
                )
            )
            self.assertIn('"result": "code"', result[0].text)

            # Test unknown tool
            result = asyncio.run(call_tool_handler("unknown_tool", {}))
            error_data = json.loads(result[0].text)
            self.assertIn("error", error_data)
            self.assertFalse(error_data["success"])

            # Test exception in tool execution
            mock_api.analyze_file.side_effect = Exception("API Error")
            result = asyncio.run(
                call_tool_handler("analyze_file", {"file_path": "fail.py"})
            )
            error_data = json.loads(result[0].text)
            self.assertEqual(error_data["error"], "API Error")

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.interfaces.mcp_server.Server")
    def test_list_resources_handler(self, mock_server_cls):
        """Test list_resources handler logic"""
        mock_server_instance = MagicMock()
        mock_server_cls.return_value = mock_server_instance

        list_resources_handler = None

        def list_resources_decorator():
            def decorator(func):
                nonlocal list_resources_handler
                list_resources_handler = func
                return func

            return decorator

        mock_server_instance.list_resources.side_effect = list_resources_decorator

        server = TreeSitterAnalyzerMCPServer()
        server.create_server()

        if list_resources_handler:
            resources = asyncio.run(list_resources_handler())
            self.assertTrue(len(resources) > 0)
            # URIs may be URL-encoded, check for either encoded or plain format
            uris = [str(r.uri) for r in resources]
            self.assertTrue(
                any("code://file/" in uri for uri in uris),
                f"Expected 'code://file/' in URIs: {uris}",
            )

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.interfaces.mcp_server.Server")
    @patch("tree_sitter_analyzer.interfaces.mcp_server.api")
    def test_read_resource_handler(self, mock_api, mock_server_cls):
        """Test read_resource handler logic"""
        mock_server_instance = MagicMock()
        mock_server_cls.return_value = mock_server_instance

        read_resource_handler = None

        def read_resource_decorator():
            def decorator(func):
                nonlocal read_resource_handler
                read_resource_handler = func
                return func

            return decorator

        mock_server_instance.read_resource.side_effect = read_resource_decorator

        server = TreeSitterAnalyzerMCPServer()
        server.create_server()

        if read_resource_handler:
            # Test code://file/
            mock_api.analyze_file.return_value = {"file": "content"}
            result = asyncio.run(read_resource_handler("code://file/test.py"))
            self.assertIn('"file": "content"', result)
            mock_api.analyze_file.assert_called_with("test.py")

            # Test code://stats/framework
            mock_api.get_framework_info.return_value = {"version": "1.0"}
            result = asyncio.run(read_resource_handler("code://stats/framework"))
            self.assertIn('"version": "1.0"', result)

            # Test code://stats/languages
            mock_api.get_supported_languages.return_value = ["py"]
            result = asyncio.run(read_resource_handler("code://stats/languages"))
            # JSON may be formatted with indentation
            self.assertIn('"supported_languages"', result)
            self.assertIn('"py"', result)

            # Test unknown stats type
            result = asyncio.run(read_resource_handler("code://stats/unknown"))
            error_data = json.loads(result)
            self.assertIn("error", error_data)

            # Test unknown uri scheme
            result = asyncio.run(read_resource_handler("unknown://uri"))
            error_data = json.loads(result)
            self.assertIn("error", error_data)
            self.assertIn("Resource not found", error_data["error"])

            # Test exception handling
            mock_api.analyze_file.side_effect = Exception("Read Error")
            result = asyncio.run(read_resource_handler("code://file/error.py"))
            error_data = json.loads(result)
            self.assertEqual(error_data["error"], "Read Error")
