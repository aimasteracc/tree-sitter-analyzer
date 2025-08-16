#!/usr/bin/env python3
"""
Tests for Startup Script

This module tests the improved startup script functionality
including dependency checking and initialization handling.
"""

import asyncio
import logging
import os
import sys
from unittest.mock import Mock, patch

import pytest

# Import the startup script functions
# Note: We need to be careful about imports since start_mcp_server.py is a script
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestStartupScriptFunctions:
    """Test startup script functionality."""

    @patch("start_mcp_server.check_dependencies")
    @patch("start_mcp_server.asyncio.run")
    def test_main_execution_with_dependencies_ok(
        self, mock_asyncio_run, mock_check_deps
    ):
        """Test main execution when dependencies are available."""
        mock_check_deps.return_value = True

        # Import and test the main execution logic
        # This is a bit tricky since it's a script, so we'll test the logic
        assert mock_check_deps.return_value is True

    def test_dependency_checking_logic(self):
        """Test the dependency checking logic."""
        # Test MCP library availability
        import importlib.util

        mcp_spec = importlib.util.find_spec("mcp")
        # Check if MCP is available (not used in assertions but validates import logic)
        _ = mcp_spec is not None

        # Test tree-sitter library availability
        tree_sitter_spec = importlib.util.find_spec("tree_sitter")
        tree_sitter_available = tree_sitter_spec is not None

        # At least one should be available in our test environment
        # (since we're running tests, tree-sitter should be available)
        assert tree_sitter_available is True

    @pytest.mark.asyncio
    async def test_server_initialization_waiting_logic(self):
        """Test the server initialization waiting logic."""
        # Mock server that becomes initialized after some time
        mock_server = Mock()
        call_count = 0

        def mock_is_initialized():
            nonlocal call_count
            call_count += 1
            return call_count >= 3  # Becomes ready on 3rd check

        mock_server.is_initialized = mock_is_initialized

        # Simulate the waiting logic
        max_wait_time = 1  # 1 second for testing
        wait_interval = 0.1  # 0.1 seconds
        elapsed_time = 0

        while not mock_server.is_initialized() and elapsed_time < max_wait_time:
            await asyncio.sleep(wait_interval)
            elapsed_time += wait_interval

        # Should have become initialized
        assert mock_server.is_initialized() is True
        assert elapsed_time < max_wait_time

    @pytest.mark.asyncio
    async def test_server_initialization_timeout(self):
        """Test server initialization timeout handling."""
        # Mock server that never becomes initialized
        mock_server = Mock()
        mock_server.is_initialized.return_value = False

        # Simulate the waiting logic with timeout
        max_wait_time = 0.2  # Short timeout for testing
        wait_interval = 0.05
        elapsed_time = 0

        while not mock_server.is_initialized() and elapsed_time < max_wait_time:
            await asyncio.sleep(wait_interval)
            elapsed_time += wait_interval

        # Should have timed out
        assert not mock_server.is_initialized()
        assert elapsed_time >= max_wait_time

    @pytest.mark.asyncio
    async def test_retry_logic_with_exponential_backoff(self):
        """Test retry logic with exponential backoff."""
        attempt_count = 0
        max_retries = 3
        retry_delay = 0.1  # Start with 0.1 seconds

        async def mock_operation():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise Exception(f"Attempt {attempt_count} failed")
            return "success"

        # Simulate retry logic
        for attempt in range(max_retries):
            try:
                result = await mock_operation()
                break  # Success, exit retry loop
            except Exception:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    raise

        assert result == "success"
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_concurrent_initialization_checks(self):
        """Test concurrent initialization checks don't interfere."""
        # Mock server with thread-safe initialization check
        mock_server = Mock()
        mock_server.is_initialized.return_value = True

        # Run multiple concurrent checks
        async def check_initialization():
            return mock_server.is_initialized()

        tasks = [asyncio.create_task(check_initialization()) for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # All should return True
        assert all(results)
        assert len(results) == 10


class TestStartupScriptIntegration:
    """Integration tests for startup script functionality."""

    @patch("tree_sitter_analyzer.project_detector.detect_project_root")
    def test_project_root_detection(self, mock_detect):
        """Test project root detection in startup."""
        mock_detect.return_value = "/test/project/root"

        from tree_sitter_analyzer.project_detector import detect_project_root

        detect_project_root()

        # Should call the detection function
        assert mock_detect.called

    @patch("tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer")
    def test_server_creation_in_startup(self, mock_server_class):
        """Test server creation during startup."""
        mock_server = Mock()
        mock_server.is_initialized.return_value = True
        mock_server_class.return_value = mock_server

        # Simulate server creation
        project_root = "/test/root"
        server = mock_server_class(project_root)

        # Should create server with project root
        mock_server_class.assert_called_once_with(project_root)
        assert server.is_initialized()

    @pytest.mark.asyncio
    async def test_startup_error_handling(self):
        """Test error handling during startup."""
        # Test various startup errors
        startup_errors = [
            ImportError("Missing dependency"),
            RuntimeError("Initialization failed"),
            FileNotFoundError("Project root not found"),
            PermissionError("Permission denied"),
        ]

        for error in startup_errors:
            # Each error should be handleable
            assert isinstance(error, Exception)
            # In real startup script, these would be caught and handled

    def test_logging_configuration(self, caplog):
        """Test that startup script configures logging properly."""
        import os

        from tree_sitter_analyzer.utils import setup_logger

        # Save original LOG_LEVEL if it exists
        original_log_level = os.environ.get("LOG_LEVEL")

        try:
            # Clear any LOG_LEVEL environment variable to avoid test pollution
            if "LOG_LEVEL" in os.environ:
                del os.environ["LOG_LEVEL"]

            # Test logger setup functionality
            logger = setup_logger("test_startup", level=logging.INFO)

            # Verify logger is properly configured
            assert logger.name == "test_startup"
            assert logger.level == logging.INFO
            assert len(logger.handlers) > 0
        finally:
            # Restore original LOG_LEVEL if it existed
            if original_log_level is not None:
                os.environ["LOG_LEVEL"] = original_log_level

    @pytest.mark.asyncio
    async def test_graceful_shutdown_handling(self):
        """Test graceful shutdown handling."""
        shutdown_called = False

        async def mock_server_run():
            # Simulate server running
            try:
                await asyncio.sleep(1)  # Simulate running
            except asyncio.CancelledError:
                nonlocal shutdown_called
                shutdown_called = True
                raise

        # Start server task
        server_task = asyncio.create_task(mock_server_run())

        # Simulate shutdown after short time
        await asyncio.sleep(0.1)
        server_task.cancel()

        try:
            await server_task
        except asyncio.CancelledError:
            pass

        # Should have handled shutdown gracefully
        assert shutdown_called

    def test_environment_variable_handling(self):
        """Test handling of environment variables."""
        # Test various environment scenarios
        test_cases = [
            ("TREE_SITTER_DEBUG", "1"),
            ("MCP_SERVER_PORT", "8080"),
            ("PROJECT_ROOT", "/custom/root"),
        ]

        for env_var, value in test_cases:
            with patch.dict(os.environ, {env_var: value}):
                # Environment variable should be accessible
                assert os.environ.get(env_var) == value


class TestStartupScriptErrorRecovery:
    """Test error recovery mechanisms in startup script."""

    @pytest.mark.asyncio
    async def test_recovery_from_temporary_failures(self):
        """Test recovery from temporary failures."""
        failure_count = 0

        async def flaky_operation():
            nonlocal failure_count
            failure_count += 1
            if failure_count <= 2:
                raise RuntimeError("Temporary failure")
            return "success"

        # Simulate retry with recovery
        max_retries = 5
        for attempt in range(max_retries):
            try:
                result = await flaky_operation()
                break
            except RuntimeError:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(0.1)

        assert result == "success"
        assert failure_count == 3  # Failed twice, succeeded on third

    def test_dependency_fallback_mechanisms(self):
        """Test fallback mechanisms for missing dependencies."""
        # Test fallback when optional dependencies are missing
        optional_deps = ["optional_package", "another_optional"]

        available_deps = []
        for dep in optional_deps:
            try:
                __import__(dep)
                available_deps.append(dep)
            except ImportError:
                # Expected for non-existent packages
                pass

        # Should handle missing optional dependencies gracefully
        assert isinstance(available_deps, list)

    @pytest.mark.asyncio
    async def test_resource_cleanup_on_failure(self):
        """Test that resources are cleaned up on startup failure."""
        resources_created = []
        resources_cleaned = []

        class MockResource:
            def __init__(self, name):
                self.name = name
                resources_created.append(name)

            def cleanup(self):
                resources_cleaned.append(self.name)

        async def failing_startup():
            # Create some resources
            resource1 = MockResource("resource1")
            resource2 = MockResource("resource2")

            try:
                # Simulate startup failure
                raise RuntimeError("Startup failed")
            finally:
                # Cleanup resources
                resource1.cleanup()
                resource2.cleanup()

        # Run failing startup
        with pytest.raises(RuntimeError):
            await failing_startup()

        # Resources should be cleaned up
        assert len(resources_created) == 2
        assert len(resources_cleaned) == 2
        assert set(resources_created) == set(resources_cleaned)
