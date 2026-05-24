"""
Comprehensive tests for MCP server — tool handling, project path, runtime, utilities.
"""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tree_sitter_analyzer.mcp.server import (
    TreeSitterAnalyzerMCPServer,
    main,
    main_sync,
    parse_mcp_args,
)


def _capture_call_tool_handler(server):
    """Helper: patch Server, call create_server(), return captured call_tool handler."""
    with patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True):
        with patch("tree_sitter_analyzer.mcp.server.Server") as mock_server_class:
            mock_server = Mock()
            captured_handlers = {}

            def capture_decorator(name):
                def decorator(func):
                    captured_handlers[name] = func
                    return func

                return decorator

            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server_class.return_value = mock_server

            server.create_server()

            assert "call_tool" in captured_handlers, (
                "call_tool handler was not registered"
            )
            return captured_handlers["call_tool"]


class TestTreeSitterAnalyzerMCPServerToolHandling:
    """Test MCP server tool call handling."""

    @pytest.fixture
    def mock_server_with_tools(self, temp_project_dir):
        """Create a server with mocked tools."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        # Mock all tools
        server.table_format_tool = AsyncMock()
        server.read_partial_tool = AsyncMock()
        server.query_tool = AsyncMock()
        server.list_files_tool = AsyncMock()
        server.search_content_tool = AsyncMock()
        server.find_and_grep_tool = AsyncMock()

        # Mock set_project_path as synchronous methods to avoid warnings
        server.table_format_tool.set_project_path = Mock()
        server.read_partial_tool.set_project_path = Mock()
        server.query_tool.set_project_path = Mock()
        server.list_files_tool.set_project_path = Mock()
        server.search_content_tool.set_project_path = Mock()
        server.find_and_grep_tool.set_project_path = Mock()

        return server

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @pytest.mark.asyncio
    async def test_handle_call_tool_check_code_scale(
        self, mock_server_with_tools, temp_project_dir
    ):
        """Test check_code_scale tool call."""
        server = mock_server_with_tools

        # Create a test file
        test_file = Path(temp_project_dir) / "test.py"
        test_file.write_text("def hello():\n    pass\n")

        with patch("tree_sitter_analyzer.mcp.server.Server") as mock_server_class:
            mock_server = Mock()
            captured_handlers = {}

            def capture_decorator(name):
                def decorator(func):
                    captured_handlers[name] = func
                    return func

                return decorator

            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server_class.return_value = mock_server

            server.create_server()

            assert "call_tool" in captured_handlers, (
                "call_tool handler was not registered"
            )
            call_tool_handler = captured_handlers["call_tool"]

            # Don't mock _analyze_code_scale - let it run with the real file
            arguments = {"file_path": str(test_file)}
            result = await call_tool_handler("check_code_scale", arguments)

            assert len(result) == 1
            assert result[0].type == "text"
            response_data = json.loads(result[0].text)

            # Verify the response contains expected fields
            assert "success" in response_data
            assert response_data["success"] is True
            assert "file_path" in response_data
            assert "language" in response_data
            assert response_data["language"] == "python"

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @pytest.mark.asyncio
    async def test_handle_call_tool_analyze_code_structure(
        self, mock_server_with_tools
    ):
        """Test analyze_code_structure tool call."""
        server = mock_server_with_tools
        server.table_format_tool.execute.return_value = {"table": "formatted"}

        with patch("tree_sitter_analyzer.mcp.server.Server") as mock_server_class:
            mock_server = Mock()
            captured_handlers = {}

            def capture_decorator(name):
                def decorator(func):
                    captured_handlers[name] = func
                    return func

                return decorator

            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server_class.return_value = mock_server

            server.create_server()

            assert "call_tool" in captured_handlers, (
                "call_tool handler was not registered"
            )
            call_tool_handler = captured_handlers["call_tool"]

            arguments = {"file_path": "test.py", "format_type": "full"}
            result = await call_tool_handler("analyze_code_structure", arguments)

            server.table_format_tool.execute.assert_called_once()
            assert len(result) == 1

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @pytest.mark.asyncio
    async def test_handle_call_tool_extract_code_section(self, mock_server_with_tools):
        """Test extract_code_section tool call."""
        server = mock_server_with_tools
        server.read_partial_tool.execute.return_value = {"content": "extracted"}

        with patch("tree_sitter_analyzer.mcp.server.Server") as mock_server_class:
            mock_server = Mock()
            captured_handlers = {}

            def capture_decorator(name):
                def decorator(func):
                    captured_handlers[name] = func
                    return func

                return decorator

            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server_class.return_value = mock_server

            server.create_server()

            assert "call_tool" in captured_handlers, (
                "call_tool handler was not registered"
            )
            call_tool_handler = captured_handlers["call_tool"]

            arguments = {"file_path": "test.py", "start_line": 1, "end_line": 10}
            result = await call_tool_handler("extract_code_section", arguments)

            server.read_partial_tool.execute.assert_called_once()
            assert len(result) == 1

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @pytest.mark.asyncio
    async def test_handle_call_tool_extract_code_section_batch_requests(
        self, mock_server_with_tools
    ):
        """Test extract_code_section tool call with batch requests
        (no file_path/start_line required at server layer)."""
        server = mock_server_with_tools
        server.read_partial_tool.execute.return_value = {
            "format": "toon",
            "toon_content": "BATCH",
            "success": True,
            "count_files": 1,
            "count_sections": 1,
        }

        with patch("tree_sitter_analyzer.mcp.server.Server") as mock_server_class:
            mock_server = Mock()
            captured_handlers = {}

            def capture_decorator(name):
                def decorator(func):
                    captured_handlers[name] = func
                    return func

                return decorator

            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server_class.return_value = mock_server

            server.create_server()

            assert "call_tool" in captured_handlers, (
                "call_tool handler was not registered"
            )
            call_tool_handler = captured_handlers["call_tool"]

            arguments = {
                "requests": [
                    {
                        "file_path": "test.py",
                        "sections": [{"start_line": 1, "end_line": 2, "label": "x"}],
                    }
                ]
            }
            result = await call_tool_handler("extract_code_section", arguments)

            server.read_partial_tool.execute.assert_called_once_with(arguments)
            assert len(result) == 1
            response_data = json.loads(result[0].text)
            assert response_data["format"] == "toon"
            assert response_data["toon_content"] == "BATCH"

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @pytest.mark.asyncio
    async def test_handle_call_tool_set_project_path(
        self, mock_server_with_tools, temp_project_dir
    ):
        """Test set_project_path tool call."""
        server = mock_server_with_tools

        with (
            patch("tree_sitter_analyzer.mcp.server.Server") as mock_server_class,
            patch(
                "tree_sitter_analyzer.mcp.server_utils.tool_registration.TextContent"
            ) as mock_text_content,
        ):
            # Mock TextContent to return a simple object with text attribute
            mock_text_content_instance = Mock()
            mock_text_content_instance.text = ""
            mock_text_content.return_value = mock_text_content_instance
            mock_text_content_instance = Mock()
            mock_text_content_instance.text = ""
            mock_text_content.return_value = mock_text_content_instance

            mock_server = Mock()
            captured_handlers = {}

            def capture_decorator(name):
                def decorator(func):
                    captured_handlers[name] = func
                    return func

                return decorator

            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server_class.return_value = mock_server

            server.create_server()

            assert "call_tool" in captured_handlers, (
                "call_tool handler was not registered"
            )
            call_tool_handler = captured_handlers["call_tool"]

            arguments = {"project_path": str(temp_project_dir)}
            result = await call_tool_handler("set_project_path", arguments)

            assert len(result) == 1
            # Since we're mocking TextContent, we need to check the call arguments
            mock_text_content.assert_called_once()
            call_args = mock_text_content.call_args
            response_text = call_args[1]["text"]  # Get the text argument
            response_data = json.loads(response_text)
            assert response_data["status"] == "success"
            assert response_data["project_root"] == str(temp_project_dir)

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @pytest.mark.asyncio
    async def test_handle_call_tool_unknown_tool(self, mock_server_with_tools):
        """Test handling of unknown tool calls."""
        server = mock_server_with_tools

        with patch("tree_sitter_analyzer.mcp.server.Server") as mock_server_class:
            mock_server = Mock()
            captured_handlers = {}

            def capture_decorator(name):
                def decorator(func):
                    captured_handlers[name] = func
                    return func

                return decorator

            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server_class.return_value = mock_server

            server.create_server()

            assert "call_tool" in captured_handlers, (
                "call_tool handler was not registered"
            )
            call_tool_handler = captured_handlers["call_tool"]

            arguments = {}
            result = await call_tool_handler("unknown_tool", arguments)

            assert len(result) == 1
            response_data = json.loads(result[0].text)
            assert "error" in response_data
            assert "Unknown tool" in response_data["error"]

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @pytest.mark.asyncio
    async def test_handle_call_tool_security_validation(self, mock_server_with_tools):
        """Test security validation in tool calls."""
        server = mock_server_with_tools

        # Mock security validator to reject the path
        with patch.object(
            server.security_validator,
            "validate_file_path",
            return_value=(False, "Invalid path"),
        ):
            with patch("tree_sitter_analyzer.mcp.server.Server") as mock_server_class:
                mock_server = Mock()
                captured_handlers = {}

                def capture_decorator(name):
                    def decorator(func):
                        captured_handlers[name] = func
                        return func

                    return decorator

                mock_server.call_tool.return_value = capture_decorator("call_tool")
                mock_server_class.return_value = mock_server

                server.create_server()

                assert "call_tool" in captured_handlers, (
                    "call_tool handler was not registered"
                )
                call_tool_handler = captured_handlers["call_tool"]

                arguments = {"file_path": "../../../etc/passwd"}
                result = await call_tool_handler("check_code_scale", arguments)

                assert len(result) == 1
                response_data = json.loads(result[0].text)
                assert "error" in response_data
                assert "Invalid or unsafe file path" in response_data["error"]


class TestTreeSitterAnalyzerMCPServerProjectPath:
    """Test MCP server project path management."""

    def test_set_project_path_success(self, temp_project_dir):
        """Test successful project path setting."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        # Create another temp directory
        import tempfile

        with tempfile.TemporaryDirectory() as new_project_dir:
            server.set_project_path(new_project_dir)

            # Verify all components were updated
            assert server.project_stats_resource.project_root == new_project_dir

    def test_set_project_path_with_universal_tool(self, temp_project_dir):
        """Test project path setting with universal tool."""
        mock_universal_tool = Mock()

        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        server.universal_analyze_tool = mock_universal_tool

        import tempfile

        with tempfile.TemporaryDirectory() as new_project_dir:
            server.set_project_path(new_project_dir)

            mock_universal_tool.set_project_path.assert_called_once_with(
                new_project_dir
            )

    def test_set_project_path_without_universal_tool(self, temp_project_dir):
        """Test project path setting without universal tool."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        server.universal_analyze_tool = None

        import tempfile

        with tempfile.TemporaryDirectory() as new_project_dir:
            # Should not raise any exception
            server.set_project_path(new_project_dir)


class TestTreeSitterAnalyzerMCPServerRuntime:
    """Test MCP server runtime functionality."""

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @pytest.mark.asyncio
    async def test_run_success(self, temp_project_dir):
        """Test successful server run."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        with patch("tree_sitter_analyzer.mcp.server.stdio_server") as mock_stdio:
            mock_read_stream = Mock()
            mock_write_stream = Mock()
            mock_stdio.return_value.__aenter__.return_value = (
                mock_read_stream,
                mock_write_stream,
            )

            with patch.object(server, "create_server") as mock_create:
                mock_mcp_server = AsyncMock()
                mock_create.return_value = mock_mcp_server

                # Mock the run to avoid infinite loop
                mock_mcp_server.run.side_effect = KeyboardInterrupt()

                with pytest.raises(KeyboardInterrupt):
                    await server.run()

                mock_mcp_server.run.assert_called_once()

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", False)
    @pytest.mark.asyncio
    async def test_run_mcp_unavailable(self, temp_project_dir):
        """Test server run when MCP is unavailable."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        with pytest.raises(RuntimeError, match="MCP library not available"):
            await server.run()

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @pytest.mark.asyncio
    async def test_run_with_exception(self, temp_project_dir):
        """Test server run with exception handling."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        with patch("tree_sitter_analyzer.mcp.server.stdio_server") as mock_stdio:
            mock_stdio.side_effect = Exception("Test error")

            with pytest.raises(Exception, match="Test error"):
                await server.run()


class TestMCPServerUtilities:
    """Test MCP server utility functions."""

    def test_parse_mcp_args_default(self):
        """Test parsing MCP arguments with defaults."""
        args = parse_mcp_args([])

        assert args.project_root is None

    def test_parse_mcp_args_with_project_root(self):
        """Test parsing MCP arguments with project root."""
        args = parse_mcp_args(["--project-root", "/path/to/project"])

        assert args.project_root == "/path/to/project"

    @pytest.mark.asyncio
    async def test_main_with_args(self):
        """Test main function with command line arguments."""
        with patch("tree_sitter_analyzer.mcp.server.parse_mcp_args") as mock_parse:
            mock_args = Mock()
            mock_args.project_root = "/test/path"
            mock_parse.return_value = mock_args

            with patch(
                "tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer"
            ) as mock_server_class:
                mock_server = AsyncMock()
                mock_server_class.return_value = mock_server
                mock_server.run.side_effect = KeyboardInterrupt()

                with pytest.raises(SystemExit):
                    await main()

    @pytest.mark.asyncio
    async def test_main_with_env_var(self):
        """Test main function with environment variable."""
        with patch.dict(os.environ, {"TREE_SITTER_PROJECT_ROOT": "/env/path"}):
            with patch("tree_sitter_analyzer.mcp.server.parse_mcp_args") as mock_parse:
                mock_args = Mock()
                mock_args.project_root = None
                mock_parse.return_value = mock_args

                with patch("tree_sitter_analyzer.mcp.server.PathClass") as mock_path:
                    mock_path.cwd.return_value.joinpath.return_value.exists(
                        return_value=True
                    )

                    with patch(
                        "tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer"
                    ) as mock_server_class:
                        mock_server = AsyncMock()
                        mock_server_class.return_value = mock_server
                        mock_server.run.side_effect = KeyboardInterrupt()

                        with pytest.raises(SystemExit):
                            await main()

    @pytest.mark.asyncio
    async def test_main_with_auto_detection(self):
        """Test main function with auto-detected project root."""
        with patch("tree_sitter_analyzer.mcp.server.parse_mcp_args") as mock_parse:
            mock_args = Mock()
            mock_args.project_root = None
            mock_parse.return_value = mock_args

            with patch(
                "tree_sitter_analyzer.mcp.server.detect_project_root"
            ) as mock_detect:
                mock_detect.return_value = "/detected/path"

                with patch(
                    "tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer"
                ) as mock_server_class:
                    mock_server = AsyncMock()
                    mock_server_class.return_value = mock_server
                    mock_server.run.side_effect = KeyboardInterrupt()

                    with pytest.raises(SystemExit):
                        await main()

    @pytest.mark.asyncio
    async def test_main_with_invalid_placeholder(self):
        """Test main function with invalid placeholder in project root."""
        with patch("tree_sitter_analyzer.mcp.server.parse_mcp_args") as mock_parse:
            mock_args = Mock()
            mock_args.project_root = "${workspaceFolder}"
            mock_parse.return_value = mock_args

            with patch(
                "tree_sitter_analyzer.mcp.server.detect_project_root"
            ) as mock_detect:
                mock_detect.return_value = "/detected/path"

                with patch(
                    "tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer"
                ) as mock_server_class:
                    mock_server = AsyncMock()
                    mock_server_class.return_value = mock_server
                    mock_server.run.side_effect = KeyboardInterrupt()

                    with pytest.raises(SystemExit):
                        await main()

    def test_main_sync(self):
        """Test synchronous main function."""
        with patch("tree_sitter_analyzer.mcp.server.asyncio.run") as mock_run:
            # Mock asyncio.run to prevent actual coroutine creation
            mock_run.return_value = None
            main_sync()
            mock_run.assert_called_once()
            # Verify that main() coroutine was passed to asyncio.run
            args, kwargs = mock_run.call_args
            assert len(args) == 1
            # The argument should be a coroutine, but we don't await it in the test
            import inspect

            assert inspect.iscoroutine(args[0])
            args[0].close()
            # Clean up the coroutine to prevent warning
            args[0].close()

    @pytest.mark.asyncio
    async def test_main_exception_handling(self):
        """Test main function exception handling."""
        with patch("tree_sitter_analyzer.mcp.server.parse_mcp_args") as mock_parse:
            mock_parse.side_effect = Exception("Parse error")

            with pytest.raises(SystemExit):
                await main()
