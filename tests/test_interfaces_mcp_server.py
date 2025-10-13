#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.interfaces.mcp_server module.

Comprehensive test suite for the MCP server interface functionality.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tree_sitter_analyzer import __version__
from tree_sitter_analyzer.interfaces.mcp_server import (
    MCP_AVAILABLE,
    TreeSitterAnalyzerMCPServer,
    main,
)


class TestMCPAvailability:
    """Test MCP library availability detection."""

    def test_mcp_available_constant(self):
        """Test MCP_AVAILABLE constant is properly set."""
        # This will be True if mcp is installed, False otherwise
        assert isinstance(MCP_AVAILABLE, bool)


class TestTreeSitterAnalyzerMCPServerInitialization:
    """Test MCP server initialization."""

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.interfaces.mcp_server.log_info")
    def test_server_initialization_success(self, mock_log_info):
        """Test successful server initialization when MCP is available."""
        server = TreeSitterAnalyzerMCPServer()

        assert server.server is None
        assert server.name == "tree-sitter-analyzer"
        assert server.version == __version__
        mock_log_info.assert_called_once_with(
            f"Initializing tree-sitter-analyzer v{__version__}"
        )

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", False)
    def test_server_initialization_mcp_unavailable(self):
        """Test server initialization fails when MCP is unavailable."""
        with pytest.raises(ImportError, match="MCP library not available"):
            TreeSitterAnalyzerMCPServer()


class TestMCPServerCreation:
    """Test MCP server creation and configuration."""

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.interfaces.mcp_server.Server")
    @patch("tree_sitter_analyzer.interfaces.mcp_server.log_info")
    def test_create_server_success(self, mock_log_info, mock_server_class):
        """Test successful server creation."""
        mock_server = Mock()
        mock_server_class.return_value = mock_server

        server = TreeSitterAnalyzerMCPServer()
        result = server.create_server()

        assert result == mock_server
        assert server.server == mock_server
        mock_server_class.assert_called_once_with("tree-sitter-analyzer")
        mock_log_info.assert_any_call("MCP server created successfully")

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.interfaces.mcp_server.Server")
    def test_server_tool_registration(self, mock_server_class):
        """Test that tools are properly registered."""
        mock_server = Mock()
        mock_server_class.return_value = mock_server

        server = TreeSitterAnalyzerMCPServer()
        server.create_server()

        # Verify decorators were called
        assert mock_server.list_tools.called
        assert mock_server.call_tool.called
        assert mock_server.list_resources.called
        assert mock_server.read_resource.called


class TestServerProperties:
    """Test server properties and basic functionality."""

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_server_properties(self):
        """Test server properties are set correctly."""
        server = TreeSitterAnalyzerMCPServer()

        assert server.name == "tree-sitter-analyzer"
        assert server.version == __version__
        assert server.server is None

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.interfaces.mcp_server.Server")
    def test_server_creation_sets_server_property(self, mock_server_class):
        """Test that create_server sets the server property."""
        mock_server = Mock()
        mock_server_class.return_value = mock_server

        server = TreeSitterAnalyzerMCPServer()
        assert server.server is None

        server.create_server()
        assert server.server == mock_server


class TestMainFunctionBasic:
    """Test main function basic functionality."""

    @patch("tree_sitter_analyzer.interfaces.mcp_server.TreeSitterAnalyzerMCPServer")
    @patch("tree_sitter_analyzer.interfaces.mcp_server.log_info")
    @patch("tree_sitter_analyzer.interfaces.mcp_server.log_error")
    def test_main_keyboard_interrupt(
        self, mock_log_error, mock_log_info, mock_server_class
    ):
        """Test main function handles KeyboardInterrupt."""
        mock_server = Mock()
        mock_server.run = AsyncMock(side_effect=KeyboardInterrupt())
        mock_server_class.return_value = mock_server

        # Run main in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(main())
        finally:
            loop.close()

        mock_server_class.assert_called_once()
        mock_log_info.assert_called_with("Server stopped by user")
        mock_log_error.assert_not_called()

    @patch("tree_sitter_analyzer.interfaces.mcp_server.TreeSitterAnalyzerMCPServer")
    @patch("tree_sitter_analyzer.interfaces.mcp_server.log_error")
    def test_main_exception_handling(self, mock_log_error, mock_server_class):
        """Test main function handles exceptions."""
        mock_server_class.side_effect = Exception("Test error")

        # Run main in event loop and expect SystemExit
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            with pytest.raises(SystemExit):
                loop.run_until_complete(main())
        finally:
            loop.close()

        mock_log_error.assert_called()


class TestServerRunMethod:
    """Test server run method."""

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.interfaces.mcp_server.stdio_server")
    @patch("tree_sitter_analyzer.interfaces.mcp_server.InitializationOptions")
    @patch("tree_sitter_analyzer.interfaces.mcp_server.Server")
    @patch("tree_sitter_analyzer.interfaces.mcp_server.log_info")
    def test_run_method_basic(
        self, mock_log_info, mock_server_class, mock_init_options, mock_stdio_server
    ):
        """Test run method basic functionality."""
        # Use regular Mock instead of AsyncMock for server decorators
        mock_server = Mock()
        mock_server.run = AsyncMock()
        mock_server_class.return_value = mock_server

        # Mock stdio_server context manager to complete quickly
        mock_streams = (AsyncMock(), AsyncMock())
        mock_stdio_server.return_value.__aenter__ = AsyncMock(return_value=mock_streams)
        mock_stdio_server.return_value.__aexit__ = AsyncMock(return_value=None)

        # Make server.run complete quickly
        async def quick_run(*args, **kwargs):
            await asyncio.sleep(0.01)  # Very short delay

        mock_server.run.side_effect = quick_run

        server = TreeSitterAnalyzerMCPServer()

        # Test run method
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.run())
        finally:
            loop.close()

        mock_log_info.assert_any_call(
            f"Starting MCP server: tree-sitter-analyzer v{__version__}"
        )
        mock_init_options.assert_called_once()


class TestErrorHandling:
    """Test error handling scenarios."""

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.interfaces.mcp_server.stdio_server")
    @patch("tree_sitter_analyzer.interfaces.mcp_server.Server")
    @patch("tree_sitter_analyzer.interfaces.mcp_server.log_error")
    def test_run_method_exception_handling(
        self, mock_log_error, mock_server_class, mock_stdio_server
    ):
        """Test run method handles exceptions."""
        # Use regular Mock instead of AsyncMock for server decorators
        mock_server = Mock()
        mock_server.run = AsyncMock()
        mock_server_class.return_value = mock_server

        # Make stdio_server raise an exception
        mock_stdio_server.side_effect = Exception("Server error")

        server = TreeSitterAnalyzerMCPServer()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            with pytest.raises(Exception, match="Server error"):
                loop.run_until_complete(server.run())
        finally:
            loop.close()

        mock_log_error.assert_called()


class TestLoggingIntegration:
    """Test logging integration."""

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.interfaces.mcp_server.log_info")
    def test_initialization_logging(self, mock_log_info):
        """Test that initialization logs correctly."""
        TreeSitterAnalyzerMCPServer()
        mock_log_info.assert_called_once_with(
            f"Initializing tree-sitter-analyzer v{__version__}"
        )

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.interfaces.mcp_server.Server")
    @patch("tree_sitter_analyzer.interfaces.mcp_server.log_info")
    def test_server_creation_logging(self, mock_log_info, mock_server_class):
        """Test that server creation logs correctly."""
        mock_server = Mock()
        mock_server_class.return_value = mock_server

        server = TreeSitterAnalyzerMCPServer()
        server.create_server()

        mock_log_info.assert_any_call("MCP server created successfully")


class TestModuleImports:
    """Test module imports and dependencies."""

    def test_module_imports(self):
        """Test that required modules can be imported."""
        # Test that the module can be imported
        from tree_sitter_analyzer.interfaces import mcp_server

        assert hasattr(mcp_server, "TreeSitterAnalyzerMCPServer")
        assert hasattr(mcp_server, "MCP_AVAILABLE")
        assert hasattr(mcp_server, "main")

    def test_mcp_availability_detection(self):
        """Test MCP availability detection logic."""
        # The MCP_AVAILABLE constant should be a boolean
        assert isinstance(MCP_AVAILABLE, bool)

        # If MCP is available, we should be able to create a server
        if MCP_AVAILABLE:
            with patch("tree_sitter_analyzer.interfaces.mcp_server.log_info"):
                server = TreeSitterAnalyzerMCPServer()
                assert server.name == "tree-sitter-analyzer"


class TestServerConfiguration:
    """Test server configuration and setup."""

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.interfaces.mcp_server.Server")
    def test_server_name_configuration(self, mock_server_class):
        """Test server name is configured correctly."""
        mock_server = Mock()
        mock_server_class.return_value = mock_server

        server = TreeSitterAnalyzerMCPServer()
        server.create_server()

        mock_server_class.assert_called_once_with("tree-sitter-analyzer")

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.interfaces.mcp_server.InitializationOptions")
    @patch("tree_sitter_analyzer.interfaces.mcp_server.Server")
    def test_initialization_options_configuration(
        self, mock_server_class, mock_init_options
    ):
        """Test initialization options are configured correctly."""
        # Use regular Mock instead of AsyncMock for server decorators
        mock_server = Mock()
        mock_server.run = AsyncMock()
        mock_server_class.return_value = mock_server

        server = TreeSitterAnalyzerMCPServer()

        # Mock stdio_server to avoid actual server startup
        with patch(
            "tree_sitter_analyzer.interfaces.mcp_server.stdio_server"
        ) as mock_stdio:
            mock_streams = (AsyncMock(), AsyncMock())
            mock_stdio.return_value.__aenter__ = AsyncMock(return_value=mock_streams)
            mock_stdio.return_value.__aexit__ = AsyncMock(return_value=None)

            # Make server.run complete quickly
            async def quick_run(*args, **kwargs):
                await asyncio.sleep(0.01)  # Very short delay

            mock_server.run.side_effect = quick_run

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(server.run())
            finally:
                loop.close()

        # Verify InitializationOptions was called with correct parameters
        mock_init_options.assert_called_once()
        call_args = mock_init_options.call_args[1]
        assert call_args["server_name"] == "tree-sitter-analyzer"
        assert call_args["server_version"] == __version__
        assert "capabilities" in call_args


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_multiple_server_instances(self):
        """Test creating multiple server instances."""
        with patch("tree_sitter_analyzer.interfaces.mcp_server.log_info"):
            server1 = TreeSitterAnalyzerMCPServer()
            server2 = TreeSitterAnalyzerMCPServer()

            assert server1.name == server2.name
            assert server1.version == server2.version
            assert server1 is not server2

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.interfaces.mcp_server.Server")
    def test_create_server_multiple_calls(self, mock_server_class):
        """Test calling create_server multiple times."""
        mock_server1 = Mock()
        mock_server2 = Mock()
        mock_server_class.side_effect = [mock_server1, mock_server2]

        server = TreeSitterAnalyzerMCPServer()

        result1 = server.create_server()
        assert result1 == mock_server1
        assert server.server == mock_server1

        result2 = server.create_server()
        assert result2 == mock_server2
        assert server.server == mock_server2  # Should update to new server

        assert mock_server_class.call_count == 2


class TestAsyncBehavior:
    """Test async behavior and coroutines."""

    def test_main_is_coroutine(self):
        """Test that main function is a coroutine."""
        import inspect

        assert inspect.iscoroutinefunction(main)

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    def test_run_is_coroutine(self):
        """Test that run method is a coroutine."""
        import inspect

        server = TreeSitterAnalyzerMCPServer()
        assert inspect.iscoroutinefunction(server.run)


class TestIntegrationScenarios:
    """Test integration scenarios."""

    @patch("tree_sitter_analyzer.interfaces.mcp_server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.interfaces.mcp_server.Server")
    @patch("tree_sitter_analyzer.interfaces.mcp_server.log_info")
    def test_full_server_lifecycle(self, mock_log_info, mock_server_class):
        """Test full server lifecycle from creation to setup."""
        mock_server = Mock()
        mock_server_class.return_value = mock_server

        # Create server instance
        server = TreeSitterAnalyzerMCPServer()
        assert server.server is None

        # Create MCP server
        result = server.create_server()
        assert result == mock_server
        assert server.server == mock_server

        # Verify all expected calls were made
        mock_server_class.assert_called_once_with("tree-sitter-analyzer")
        mock_log_info.assert_any_call(f"Initializing tree-sitter-analyzer v{__version__}")
        mock_log_info.assert_any_call("MCP server created successfully")

        # Verify decorators were registered
        assert mock_server.list_tools.called
        assert mock_server.call_tool.called
        assert mock_server.list_resources.called
        assert mock_server.read_resource.called
