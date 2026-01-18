#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.mcp.server module.

Basic test suite for the MCP server functionality.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from tree_sitter_analyzer.mcp.server import (
    MCP_AVAILABLE,
    TreeSitterAnalyzerMCPServer,
    main,
)


class TestMCPServerBasic:
    """Basic tests for MCP server."""

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.mcp.server.get_analysis_engine")
    @patch("tree_sitter_analyzer.mcp.server.setup_logger")
    def test_server_initialization(self, mock_logger, mock_engine):
        """Test server initialization."""
        mock_engine.return_value = Mock()
        mock_logger.return_value = Mock()

        server = TreeSitterAnalyzerMCPServer()

        assert server.server is None
        assert server.analysis_engine is not None
        from tree_sitter_analyzer.mcp import MCP_INFO

        assert server.name == "tree-sitter-analyzer-mcp"
        # 版本号应与主体一致
        assert server.version.startswith(MCP_INFO["version"])

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.mcp.server.get_analysis_engine")
    @patch("tree_sitter_analyzer.mcp.server.setup_logger")
    def test_set_project_path(self, mock_logger, mock_engine):
        """Test setting project path."""
        mock_engine.return_value = Mock()
        mock_logger.return_value = Mock()

        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path("/test/path")

        # Should not raise any exceptions
        assert True

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", False)
    def test_create_server_mcp_unavailable(self):
        """Test server creation when MCP is unavailable."""
        with (
            patch("tree_sitter_analyzer.mcp.server.get_analysis_engine"),
            patch("tree_sitter_analyzer.mcp.server.setup_logger"),
        ):
            server = TreeSitterAnalyzerMCPServer()

            with pytest.raises(RuntimeError, match="MCP library not available"):
                server.create_server()

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", False)
    def test_run_mcp_unavailable(self):
        """Test run when MCP is unavailable."""
        with (
            patch("tree_sitter_analyzer.mcp.server.get_analysis_engine"),
            patch("tree_sitter_analyzer.mcp.server.setup_logger"),
        ):
            server = TreeSitterAnalyzerMCPServer()

            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                with pytest.raises(RuntimeError, match="MCP library not available"):
                    loop.run_until_complete(server.run())
            finally:
                loop.close()


class TestMCPServerWithMCP:
    """Tests for MCP server when MCP is available."""

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.mcp.server.Server")
    @patch("tree_sitter_analyzer.mcp.server.get_analysis_engine")
    @patch("tree_sitter_analyzer.mcp.server.setup_logger")
    def test_create_server_success(self, mock_logger, mock_engine, mock_server_class):
        """Test successful server creation."""
        mock_engine.return_value = Mock()
        mock_logger.return_value = Mock()
        mock_server = Mock()
        mock_server_class.return_value = mock_server

        server = TreeSitterAnalyzerMCPServer()
        result = server.create_server()

        assert result == mock_server
        assert server.server == mock_server
        mock_server_class.assert_called_once_with("tree-sitter-analyzer-mcp")

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.mcp.server.stdio_server")
    @patch("tree_sitter_analyzer.mcp.server.InitializationOptions")
    @patch("tree_sitter_analyzer.mcp.server.Server")
    @patch("tree_sitter_analyzer.mcp.server.get_analysis_engine")
    @patch("tree_sitter_analyzer.mcp.server.setup_logger")
    def test_run_server_basic(
        self,
        mock_logger,
        mock_engine,
        mock_server_class,
        mock_init_options,
        mock_stdio_server,
    ):
        """Test basic server running."""
        mock_engine.return_value = Mock()
        mock_logger.return_value = Mock()

        mock_server = Mock()
        mock_server.run = AsyncMock()
        mock_server_class.return_value = mock_server

        mock_streams = (AsyncMock(), AsyncMock())
        mock_stdio_server.return_value.__aenter__ = AsyncMock(return_value=mock_streams)
        mock_stdio_server.return_value.__aexit__ = AsyncMock(return_value=None)

        # Make server.run complete quickly
        async def quick_run(*args, **kwargs):
            await asyncio.sleep(0.01)

        mock_server.run.side_effect = quick_run

        server = TreeSitterAnalyzerMCPServer()

        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.run())
        finally:
            loop.close()

        mock_init_options.assert_called_once()
        mock_server.run.assert_called_once()


class TestAnalyzeCodeScale:
    """Test analyze code scale functionality."""

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.mcp.server.get_analysis_engine")
    @patch("tree_sitter_analyzer.mcp.server.setup_logger")
    def test_analyze_code_scale_method(self, mock_logger, mock_engine):
        """Test _analyze_code_scale method delegates to analyze_scale_tool."""
        # Mock dependencies
        mock_engine.return_value = Mock()
        mock_logger.return_value = Mock()

        server = TreeSitterAnalyzerMCPServer()

        # Mock the analyze_scale_tool.execute() to return expected result
        expected_result = {
            "metrics": {
                "elements": {"classes": 1, "methods": 1},
            }
        }
        server.analyze_scale_tool = Mock()
        server.analyze_scale_tool.execute = AsyncMock(return_value=expected_result)

        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                server._analyze_code_scale({"file_path": "test.py"})
            )
            # Check the result matches what the tool returned
            assert result == expected_result
            assert "metrics" in result
            assert "elements" in result["metrics"]
            assert result["metrics"]["elements"]["classes"] == 1
            assert result["metrics"]["elements"]["methods"] == 1
            # Verify the tool was called with the correct arguments
            server.analyze_scale_tool.execute.assert_called_once_with(
                {"file_path": "test.py"}
            )
        finally:
            loop.close()


class TestMainFunction:
    """Test main function."""

    @patch("tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer")
    @patch("tree_sitter_analyzer.mcp.server.logger")
    def test_main_keyboard_interrupt(self, mock_logger, mock_server_class):
        """Test main function handles KeyboardInterrupt."""
        mock_server = Mock()
        mock_server.run = AsyncMock(side_effect=KeyboardInterrupt())
        mock_server_class.return_value = mock_server

        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            with pytest.raises(SystemExit) as exc_info:
                loop.run_until_complete(main())
            assert exc_info.value.code == 0
        finally:
            loop.close()

        mock_server_class.assert_called_once()
        # Check that both messages were logged
        mock_logger.info.assert_any_call("Server stopped by user")
        mock_logger.info.assert_called_with("MCP server shutdown complete")

    @patch("tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer")
    @patch("tree_sitter_analyzer.mcp.server.logger")
    def test_main_exception_handling(self, mock_logger, mock_server_class):
        """Test main function handles exceptions."""
        mock_server_class.side_effect = Exception("Test error")

        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            with pytest.raises(SystemExit):
                loop.run_until_complete(main())
        finally:
            loop.close()

        mock_logger.error.assert_called()


class TestToolsAndResources:
    """Test tools and resources functionality."""

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.mcp.server.get_analysis_engine")
    @patch("tree_sitter_analyzer.mcp.server.setup_logger")
    def test_tools_initialization(self, mock_logger, mock_engine):
        """Test that tools are properly initialized."""
        mock_engine.return_value = Mock()
        mock_logger.return_value = Mock()

        server = TreeSitterAnalyzerMCPServer()

        # Test that the three core tools are initialized
        assert server.read_partial_tool is not None  # extract_code_section
        assert server.table_format_tool is not None  # analyze_code_structure
        assert server.analysis_engine is not None  # used by check_code_scale

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.mcp.server.get_analysis_engine")
    @patch("tree_sitter_analyzer.mcp.server.setup_logger")
    def test_resources_initialization(self, mock_logger, mock_engine):
        """Test that resources are properly initialized."""
        mock_engine.return_value = Mock()
        mock_logger.return_value = Mock()

        server = TreeSitterAnalyzerMCPServer()

        assert server.code_file_resource is not None
        assert server.project_stats_resource is not None


class TestMCPAvailability:
    """Test MCP availability detection."""

    def test_mcp_available_constant(self):
        """Test MCP_AVAILABLE constant is properly set."""
        assert isinstance(MCP_AVAILABLE, bool)


class TestFallbackClasses:
    """Test fallback classes when MCP is not available."""

    def test_mcp_availability_handling(self):
        """Test that MCP availability is properly handled."""
        # Just test that the module can be imported and MCP_AVAILABLE is a boolean
        from tree_sitter_analyzer.mcp.server import MCP_AVAILABLE

        assert isinstance(MCP_AVAILABLE, bool)
