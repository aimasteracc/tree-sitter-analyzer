#!/usr/bin/env python3
"""
Tests for MCP Server Initialization

This module tests the initialization process and state management
of the MCP server, including the fixes we recently implemented.
"""

import asyncio
import logging
import os
import tempfile
from unittest.mock import AsyncMock, Mock

import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.utils.error_handler import (
    ErrorCategory,
    ErrorSeverity,
    MCPError,
)


class TestMCPServerInitialization:
    """Test MCP server initialization and state management."""

    def test_server_initialization_state(self):
        """Test that server properly tracks initialization state."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server = TreeSitterAnalyzerMCPServer(temp_dir)

            # Server should be initialized after construction
            assert server.is_initialized() is True
            assert server._initialization_complete is True

    def test_server_initialization_logging(self, caplog):
        """Test that initialization produces proper log messages."""
        # Set log level to INFO for tree_sitter_analyzer logger
        caplog.set_level(logging.INFO, logger="tree_sitter_analyzer")
        caplog.set_level(logging.INFO, logger="tree_sitter_analyzer.mcp.server")

        with tempfile.TemporaryDirectory() as temp_dir:
            server = TreeSitterAnalyzerMCPServer(temp_dir)

            # Check for initialization log messages
            assert "Starting MCP server initialization..." in caplog.text
            assert "MCP server initialization complete" in caplog.text

    def test_ensure_initialized_when_ready(self):
        """Test _ensure_initialized when server is ready."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server = TreeSitterAnalyzerMCPServer(temp_dir)

            # Should not raise any exception
            server._ensure_initialized()

    def test_ensure_initialized_when_not_ready(self):
        """Test _ensure_initialized when server is not ready."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server = TreeSitterAnalyzerMCPServer(temp_dir)

            # Manually set initialization to false to simulate uninitialized state
            server._initialization_complete = False

            # Should raise RuntimeError
            with pytest.raises(RuntimeError, match="Server not fully initialized"):
                server._ensure_initialized()

    @pytest.mark.asyncio
    async def test_analyze_code_scale_with_initialization_check(self):
        """Test that analyze_code_scale checks initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server = TreeSitterAnalyzerMCPServer(temp_dir)

            # Mock the universal_analyze_tool to avoid actual analysis
            server.universal_analyze_tool = Mock()
            server.universal_analyze_tool.execute = AsyncMock(
                return_value={"result": "test"}
            )

            # Should work when initialized
            result = await server._analyze_code_scale({"test": "args"})
            assert result == {"result": "test"}
            server.universal_analyze_tool.execute.assert_called_once_with(
                {"test": "args"}
            )

    @pytest.mark.asyncio
    async def test_analyze_code_scale_fails_when_not_initialized(self):
        """Test that analyze_code_scale fails when not initialized."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server = TreeSitterAnalyzerMCPServer(temp_dir)

            # Set server as not initialized
            server._initialization_complete = False

            # Should raise MCPError (converted by decorator)
            with pytest.raises(MCPError, match="Server is still initializing"):
                await server._analyze_code_scale({"test": "args"})

    def test_server_metadata_after_initialization(self):
        """Test that server metadata is properly set after initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server = TreeSitterAnalyzerMCPServer(temp_dir)

            # Check metadata
            assert server.name == "tree-sitter-analyzer-mcp"
            assert server.version is not None
            assert len(server.version) > 0

    def test_components_initialized_properly(self):
        """Test that all server components are initialized."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server = TreeSitterAnalyzerMCPServer(temp_dir)

            # Check that all components are initialized
            assert server.analysis_engine is not None
            assert server.security_validator is not None
            assert server.read_partial_tool is not None
            assert server.universal_analyze_tool is not None
            assert server.table_format_tool is not None
            assert server.code_file_resource is not None
            assert server.project_stats_resource is not None

    @pytest.mark.asyncio
    async def test_server_run_method_exists(self):
        """Test that server has a run method."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server = TreeSitterAnalyzerMCPServer(temp_dir)

            # Check that run method exists and is callable
            assert hasattr(server, "run")
            assert callable(server.run)

    def test_initialization_with_none_project_root(self):
        """Test initialization with None project root."""
        server = TreeSitterAnalyzerMCPServer(None)

        # Should still initialize successfully
        assert server.is_initialized() is True
        assert server.analysis_engine is not None

    def test_initialization_with_invalid_project_root(self):
        """Test initialization with invalid project root."""
        # Use a non-existent directory
        invalid_path = "/nonexistent/path/that/should/not/exist"

        # Should raise SecurityError (security validator rejects invalid paths)
        with pytest.raises(Exception):  # Could be SecurityError or other exception
            TreeSitterAnalyzerMCPServer(invalid_path)


class TestMCPServerErrorHandling:
    """Test MCP server error handling improvements."""

    @pytest.mark.asyncio
    async def test_initialization_error_handling_in_decorator(self):
        """Test that the error handling decorator properly handles initialization errors."""
        from tree_sitter_analyzer.mcp.utils.error_handler import handle_mcp_errors

        # Create a mock function that raises initialization error
        @handle_mcp_errors("test_operation")
        async def mock_function():
            raise RuntimeError(
                "Server not fully initialized. Please wait for initialization to complete."
            )

        # Should convert to MCPError
        with pytest.raises(MCPError) as exc_info:
            await mock_function()

        assert "Server is still initializing" in str(exc_info.value)
        assert exc_info.value.category == ErrorCategory.CONFIGURATION
        assert exc_info.value.severity == ErrorSeverity.LOW

    @pytest.mark.asyncio
    async def test_other_runtime_errors_not_converted(self):
        """Test that other RuntimeErrors are not converted to initialization errors."""
        from tree_sitter_analyzer.mcp.utils.error_handler import handle_mcp_errors

        # Create a mock function that raises different runtime error
        @handle_mcp_errors("test_operation")
        async def mock_function():
            raise RuntimeError("Some other runtime error")

        # Should not convert to initialization error
        with pytest.raises(RuntimeError, match="Some other runtime error"):
            await mock_function()


class TestMCPServerIntegration:
    """Integration tests for MCP server functionality."""

    def test_server_creation_and_basic_functionality(self):
        """Test basic server creation and functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test file
            test_file = os.path.join(temp_dir, "test.py")
            with open(test_file, "w") as f:
                f.write("def hello(): pass")

            server = TreeSitterAnalyzerMCPServer(temp_dir)

            # Server should be ready
            assert server.is_initialized()

            # Components should be functional
            if server.security_validator.boundary_manager:
                assert (
                    server.security_validator.boundary_manager.project_root == temp_dir
                )

    @pytest.mark.asyncio
    async def test_server_handles_concurrent_initialization_checks(self):
        """Test that server handles concurrent initialization checks properly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server = TreeSitterAnalyzerMCPServer(temp_dir)

            # Run multiple concurrent initialization checks
            tasks = [
                asyncio.create_task(asyncio.to_thread(server._ensure_initialized))
                for _ in range(10)
            ]

            # All should complete without error
            await asyncio.gather(*tasks)

            # Server should still be initialized
            assert server.is_initialized()
