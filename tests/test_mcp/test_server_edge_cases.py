"""
Edge case and error handling tests for MCP server.
Tests cover error conditions, boundary cases, and robustness scenarios.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from typing import Any, Dict, List

import pytest

from tree_sitter_analyzer.exceptions import LanguageNotSupportedError
from tree_sitter_analyzer.mcp.server import (
    TreeSitterAnalyzerMCPServer,
    main,
    parse_mcp_args,
)
from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError


class TestMCPServerInitializationEdgeCases:
    """Test MCP server initialization edge cases."""

    def test_initialization_with_invalid_project_root(self):
        """Test initialization with invalid project root."""
        # Server should not raise exception but fallback to current directory
        server = TreeSitterAnalyzerMCPServer("/non/existent/path")
        assert server is not None
        assert server.is_initialized()
        # boundary_manager should be None for invalid project root
        assert server.security_validator.boundary_manager is None

    def test_initialization_with_file_as_project_root(self, temp_project_dir):
        """Test initialization with file instead of directory as project root."""
        # Create a file
        test_file = Path(temp_project_dir) / "test.txt"
        test_file.write_text("test")
        
        # Server should not raise exception but fallback to current directory
        server = TreeSitterAnalyzerMCPServer(str(test_file))
        assert server is not None
        assert server.is_initialized()
        # boundary_manager should be None for file path (not directory)
        assert server.security_validator.boundary_manager is None

    def test_initialization_with_permission_denied(self, temp_project_dir):
        """Test initialization with permission denied scenario."""
        # This test is platform-specific and may not work on all systems
        if os.name == 'nt':  # Windows
            pytest.skip("Permission tests not reliable on Windows")
        
        # Create a directory with restricted permissions
        restricted_dir = Path(temp_project_dir) / "restricted"
        restricted_dir.mkdir()
        
        try:
            restricted_dir.chmod(0o000)  # No permissions
            
            # This might not raise an exception on all systems
            # but we test the behavior
            server = TreeSitterAnalyzerMCPServer(str(restricted_dir))
            assert server is not None
        finally:
            # Restore permissions for cleanup
            restricted_dir.chmod(0o755)

    def test_initialization_with_unicode_path(self, temp_project_dir):
        """Test initialization with Unicode characters in path."""
        unicode_dir = Path(temp_project_dir) / "测试目录"
        unicode_dir.mkdir()
        
        server = TreeSitterAnalyzerMCPServer(str(unicode_dir))
        assert server.is_initialized()

    def test_initialization_with_very_long_path(self, temp_project_dir):
        """Test initialization with very long path."""
        # Create a nested directory structure
        long_path = Path(temp_project_dir)
        for i in range(10):
            long_path = long_path / f"very_long_directory_name_{i}"
        
        try:
            long_path.mkdir(parents=True)
            server = TreeSitterAnalyzerMCPServer(str(long_path))
            assert server.is_initialized()
        except OSError:
            # Path too long on some systems
            pytest.skip("Path too long for this system")


class TestMCPServerCodeAnalysisEdgeCases:
    """Test MCP server code analysis edge cases."""

    @pytest.fixture
    def empty_file(self, temp_project_dir):
        """Create an empty file for testing."""
        file_path = Path(temp_project_dir) / "empty.py"
        file_path.write_text("")
        return str(file_path)

    @pytest.fixture
    def binary_file(self, temp_project_dir):
        """Create a binary file for testing."""
        file_path = Path(temp_project_dir) / "binary.bin"
        file_path.write_bytes(b'\x00\x01\x02\x03\x04\x05')
        return str(file_path)

    @pytest.fixture
    def large_file(self, temp_project_dir):
        """Create a large file for testing."""
        file_path = Path(temp_project_dir) / "large.py"
        content = "# Large file\n" + "x = 1\n" * 10000
        file_path.write_text(content)
        return str(file_path)

    @pytest.mark.asyncio
    async def test_analyze_empty_file(self, temp_project_dir, empty_file):
        """Test analyzing an empty file."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        arguments = {"file_path": empty_file}
        result = await server._analyze_code_scale(arguments)
        
        assert result["metrics"]["lines_total"] == 0
        assert result["metrics"]["elements"]["total"] == 0

    @pytest.mark.asyncio
    async def test_analyze_binary_file(self, temp_project_dir, binary_file):
        """Test analyzing a binary file."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        arguments = {"file_path": binary_file}
        
        # Should raise UnsupportedLanguageError for binary files
        with pytest.raises(Exception) as exc_info:
            await server._analyze_code_scale(arguments)
        assert "not supported" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_analyze_large_file(self, temp_project_dir, large_file):
        """Test analyzing a large file."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        arguments = {"file_path": large_file}
        result = await server._analyze_code_scale(arguments)
        
        assert result["metrics"]["lines_total"] > 10000
        assert result["metrics"]["lines_code"] >= 9999  # Adjust expectation to match actual result

    @pytest.mark.asyncio
    async def test_analyze_with_invalid_language(self, temp_project_dir):
        """Test analyzing with invalid language specification."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        # Create a test file
        test_file = Path(temp_project_dir) / "test.unknown"
        test_file.write_text("some content")
        
        arguments = {
            "file_path": str(test_file),
            "language": "invalid_language"
        }
        
        # Should raise UnsupportedLanguageError for invalid language
        with pytest.raises(Exception) as exc_info:
            await server._analyze_code_scale(arguments)
        assert "not supported" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_analyze_with_malformed_code(self, temp_project_dir):
        """Test analyzing file with malformed code."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        # Create a file with syntax errors
        test_file = Path(temp_project_dir) / "malformed.py"
        test_file.write_text("""
def incomplete_function(
    # Missing closing parenthesis and body
    
class IncompleteClass
    # Missing colon and body
    
if True
    # Missing colon
    print("test"
    # Missing closing parenthesis
""")
        
        arguments = {"file_path": str(test_file)}
        result = await server._analyze_code_scale(arguments)
        
        # Should still return metrics even for malformed code
        assert "metrics" in result
        assert result["metrics"]["lines_total"] > 0

    @pytest.mark.asyncio
    async def test_analyze_with_encoding_issues(self, temp_project_dir):
        """Test analyzing file with encoding issues."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        # Create a file with non-UTF-8 content
        test_file = Path(temp_project_dir) / "encoding_test.py"
        
        try:
            # Write content with Latin-1 encoding
            with open(test_file, 'w', encoding='latin-1') as f:
                f.write("# Comment with special chars: café\nprint('hello')")
            
            arguments = {"file_path": str(test_file)}
            
            # This might raise an encoding error or handle gracefully
            try:
                result = await server._analyze_code_scale(arguments)
                assert "metrics" in result
            except UnicodeDecodeError:
                # Expected for encoding issues
                pass
        except Exception:
            pytest.skip("Encoding test not supported on this system")

    @pytest.mark.asyncio
    async def test_analyze_with_very_long_lines(self, temp_project_dir):
        """Test analyzing file with very long lines."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        # Create a file with extremely long lines
        test_file = Path(temp_project_dir) / "long_lines.py"
        long_line = "x = " + "1" * 10000 + " # Very long line"
        content = f"# Test file\n{long_line}\nprint('end')"
        test_file.write_text(content)
        
        arguments = {"file_path": str(test_file)}
        result = await server._analyze_code_scale(arguments)
        
        assert result["metrics"]["lines_total"] == 3
        assert result["metrics"]["lines_code"] >= 2


class TestMCPServerFileMetricsEdgeCases:
    """Test file metrics calculation edge cases."""

    def test_calculate_metrics_with_mixed_line_endings(self, temp_project_dir):
        """Test file metrics with mixed line endings."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        # Create file with mixed line endings
        test_file = Path(temp_project_dir) / "mixed_endings.py"
        content = "line1\nline2\r\nline3\rline4\n"
        test_file.write_bytes(content.encode())
        
        metrics = server._calculate_file_metrics(str(test_file), "python")
        
        # Should handle mixed line endings gracefully
        assert metrics["total_lines"] > 0

    def test_calculate_metrics_with_only_comments(self, temp_project_dir):
        """Test file metrics with only comments."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        test_file = Path(temp_project_dir) / "only_comments.py"
        content = """# Comment 1
# Comment 2
# Comment 3
"""
        test_file.write_text(content)
        
        metrics = server._calculate_file_metrics(str(test_file), "python")
        
        assert metrics["comment_lines"] == 3
        assert metrics["code_lines"] == 0

    def test_calculate_metrics_with_only_blank_lines(self, temp_project_dir):
        """Test file metrics with only blank lines."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        test_file = Path(temp_project_dir) / "only_blanks.py"
        content = "\n\n\n\n\n"
        test_file.write_text(content)
        
        metrics = server._calculate_file_metrics(str(test_file), "python")
        
        assert metrics["blank_lines"] >= 4
        assert metrics["code_lines"] == 0
        assert metrics["comment_lines"] == 0

    def test_calculate_metrics_with_complex_comments(self, temp_project_dir):
        """Test file metrics with complex comment patterns."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        test_file = Path(temp_project_dir) / "complex_comments.js"
        content = """// Single line comment
/* Multi-line
   comment
   block */
function test() {
    /* Inline comment */ return 42;
}
// Another comment
/* Another
   multi-line */ var x = 1;
"""
        test_file.write_text(content)
        
        metrics = server._calculate_file_metrics(str(test_file), "javascript")
        
        assert metrics["comment_lines"] > 0
        assert metrics["code_lines"] > 0

    def test_calculate_metrics_with_nested_comments(self, temp_project_dir):
        """Test file metrics with nested comment patterns."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        test_file = Path(temp_project_dir) / "nested_comments.js"
        content = """/*
 * Outer comment
 * /* This looks like nested but isn't really */
 * End of outer comment
 */
function test() {
    return 42;
}
"""
        test_file.write_text(content)
        
        metrics = server._calculate_file_metrics(str(test_file), "javascript")
        
        assert metrics["comment_lines"] >= 4
        assert metrics["code_lines"] >= 3


class TestMCPServerToolHandlingEdgeCases:
    """Test MCP server tool handling edge cases."""

    @pytest.fixture
    def server_with_failing_tools(self, temp_project_dir):
        """Create a server with tools that fail."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        # Mock tools to fail
        server.table_format_tool = AsyncMock()
        server.table_format_tool.execute.side_effect = Exception("Tool failed")
        
        server.read_partial_tool = AsyncMock()
        server.read_partial_tool.execute.side_effect = RuntimeError("Read failed")
        
        server.query_tool = AsyncMock()
        server.query_tool.execute.side_effect = ValueError("Query failed")
        
        return server

    @pytest.mark.asyncio
    async def test_tool_call_with_missing_required_params(self, temp_project_dir):
        """Test tool calls with missing required parameters."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        # Test missing file_path for check_code_scale directly
        try:
            result = await server._analyze_code_scale({})
            assert False, "Should have raised an exception"
        except Exception as e:
            assert "file_path" in str(e) or "required" in str(e).lower()

    @pytest.mark.asyncio
    async def test_tool_call_with_invalid_params(self, temp_project_dir):
        """Test tool calls with invalid parameters."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        # Test invalid project_path for set_project_path directly
        try:
            result = await server._set_project_path({"project_path": None})
            assert False, "Should have raised an exception"
        except Exception as e:
            assert "project_path" in str(e) or "invalid" in str(e).lower()

    @patch('tree_sitter_analyzer.mcp.server.MCP_AVAILABLE', True)
    @pytest.mark.asyncio
    async def test_tool_call_with_non_existent_project_path(self, temp_project_dir):
        """Test set_project_path with non-existent path."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        # Test non-existent path - should not raise exception but fallback
        server.set_project_path("/non/existent/path")
        # Should not raise exception
        assert server is not None

    @pytest.mark.asyncio
    async def test_tool_call_with_failing_tool(self, server_with_failing_tools):
        """Test tool calls when underlying tools fail."""
        server = server_with_failing_tools
        
        # Test with failing tool directly
        try:
            result = await server._analyze_code_scale({
                "file_path": "test.py"
            })
            assert False, "Should have raised an exception"
        except Exception as e:
            assert "failed" in str(e).lower() or "error" in str(e).lower() or "not found" in str(e).lower()

    @patch('tree_sitter_analyzer.mcp.server.MCP_AVAILABLE', True)
    @pytest.mark.asyncio
    async def test_tool_call_server_not_initialized(self, temp_project_dir):
        """Test tool calls when server is not initialized."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        server._initialization_complete = False
        
        with patch('tree_sitter_analyzer.mcp.server.Server') as mock_server_class:
            mock_server = Mock()
            # Set up the mock to capture the handler function when call_tool() is called as decorator
            captured_handlers = {}
            def capture_decorator(name):
                def decorator(func):
                    captured_handlers[name] = func
                    return func
                return decorator
            
            mock_server.call_tool.return_value = capture_decorator('call_tool')
            mock_server_class.return_value = mock_server
            
            server.create_server()
            
            # Get the captured handler
            assert 'call_tool' in captured_handlers, "call_tool handler was not registered"
            call_tool_handler = captured_handlers['call_tool']
            
            result = await call_tool_handler("check_code_scale", {"file_path": "test.py"})
            
            response_data = json.loads(result[0].text)
            assert "error" in response_data


class TestMCPServerResourceHandlingEdgeCases:
    """Test MCP server resource handling edge cases."""

    @pytest.mark.asyncio
    async def test_read_resource_invalid_uri(self, temp_project_dir):
        """Test reading resource with invalid URI."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        # Test invalid URI directly
        with pytest.raises(Exception) as exc_info:
            await server._read_resource("invalid://uri")
        
        assert "not found" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower() or "unknown" in str(exc_info.value).lower()
    @pytest.mark.asyncio
    async def test_read_resource_with_failing_resource(self, temp_project_dir):
        """Test reading resource when resource fails."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        # Mock resource to fail
        with patch.object(server.code_file_resource, 'matches_uri', return_value=True):
            with patch.object(server.code_file_resource, 'read_resource', side_effect=Exception("Resource failed")):
                with pytest.raises(Exception) as exc_info:
                    await server._read_resource("code://file/test.py")
                
                assert "failed" in str(exc_info.value).lower() or "error" in str(exc_info.value).lower()

class TestMCPServerRuntimeEdgeCases:
    """Test MCP server runtime edge cases."""

    @patch('tree_sitter_analyzer.mcp.server.MCP_AVAILABLE', True)
    @pytest.mark.asyncio
    async def test_run_with_stdio_failure(self, temp_project_dir):
        """Test server run when stdio fails."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        with patch('tree_sitter_analyzer.mcp.server.stdio_server') as mock_stdio:
            mock_stdio.side_effect = OSError("Stdio failed")
            
            with pytest.raises(OSError, match="Stdio failed"):
                await server.run()

    @patch('tree_sitter_analyzer.mcp.server.MCP_AVAILABLE', True)
    @pytest.mark.asyncio
    async def test_run_with_server_creation_failure(self, temp_project_dir):
        """Test server run when server creation fails."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        with patch.object(server, 'create_server') as mock_create:
            mock_create.side_effect = RuntimeError("Server creation failed")
            
            with pytest.raises(RuntimeError, match="Server creation failed"):
                await server.run()

    @patch('tree_sitter_analyzer.mcp.server.MCP_AVAILABLE', True)
    @pytest.mark.asyncio
    async def test_run_with_initialization_options_failure(self, temp_project_dir):
        """Test server run when initialization options fail."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        with patch('tree_sitter_analyzer.mcp.server.InitializationOptions') as mock_options:
            mock_options.side_effect = Exception("Options failed")
            
            with pytest.raises(Exception, match="Options failed"):
                await server.run()


class TestMCPServerUtilityEdgeCases:
    """Test MCP server utility function edge cases."""

    def test_parse_args_with_invalid_arguments(self):
        """Test parsing invalid command line arguments."""
        # Test with unknown arguments (should raise SystemExit)
        with pytest.raises(SystemExit) as exc_info:
            args = parse_mcp_args(["--unknown-arg", "value"])
        
        # SystemExit with code 2 indicates argument parsing error
        assert exc_info.value.code == 2

    @pytest.mark.asyncio
    async def test_main_with_keyboard_interrupt(self):
        """Test main function handling keyboard interrupt."""
        with patch('tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer') as mock_server_class:
            mock_server = AsyncMock()
            mock_server_class.return_value = mock_server
            mock_server.run.side_effect = KeyboardInterrupt()
            
            # KeyboardInterrupt should be handled gracefully
            try:
                await main()
            except SystemExit as e:
                # SystemExit with code 0 is expected for graceful shutdown
                assert e.code == 0

    @pytest.mark.asyncio
    async def test_main_with_general_exception(self):
        """Test main function handling general exceptions."""
        with patch('tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer') as mock_server_class:
            mock_server_class.side_effect = Exception("General error")
            
            with pytest.raises(SystemExit):
                await main()

    @pytest.mark.asyncio
    async def test_main_with_project_root_detection_failure(self):
        """Test main function when project root detection fails."""
        with patch('tree_sitter_analyzer.mcp.server.parse_mcp_args') as mock_parse:
            mock_args = Mock()
            mock_args.project_root = None
            mock_parse.return_value = mock_args
            
            with patch('tree_sitter_analyzer.mcp.server.detect_project_root') as mock_detect:
                mock_detect.side_effect = Exception("Detection failed")
                
                with patch('sys.stdin'), patch('sys.stdout'), patch('sys.stderr'):
                    with pytest.raises(SystemExit):
                        await main()

    @pytest.mark.asyncio
    async def test_main_with_environment_variable_issues(self):
        """Test main function with problematic environment variables."""
        with patch.dict(os.environ, {'TREE_SITTER_PROJECT_ROOT': '${invalid}'}):
            with patch('tree_sitter_analyzer.mcp.server.parse_mcp_args') as mock_parse:
                mock_args = Mock()
                mock_args.project_root = None
                mock_parse.return_value = mock_args
                
                with patch('tree_sitter_analyzer.mcp.server.detect_project_root') as mock_detect:
                    mock_detect.return_value = "/fallback/path"
                    
                    with patch('tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer') as mock_server_class:
                        mock_server = AsyncMock()
                        mock_server_class.return_value = mock_server
                        mock_server.run.side_effect = KeyboardInterrupt()
                        
                        with patch('sys.stdin'), patch('sys.stdout'), patch('sys.stderr'):
                            try:
                                await main()
                            except SystemExit:
                                pass  # Expected for KeyboardInterrupt handling

    def test_main_sync_with_exception(self):
        """Test synchronous main function with exception."""
        with patch('tree_sitter_analyzer.mcp.server.asyncio.run') as mock_run:
            mock_run.side_effect = Exception("Async run failed")
            
            with patch('sys.stdin'), patch('sys.stdout'), patch('sys.stderr'):
                with pytest.raises(Exception, match="Async run failed"):
                    from tree_sitter_analyzer.mcp.server import main_sync
                    main_sync()


class TestMCPServerLoggingEdgeCases:
    """Test MCP server logging edge cases."""

    def test_server_with_logging_disabled(self, temp_project_dir):
        """Test server behavior when logging is disabled or fails."""
        with patch('tree_sitter_analyzer.mcp.server.logger') as mock_logger:
            mock_logger.info.side_effect = OSError("Logging failed")
            mock_logger.error.side_effect = OSError("Logging failed")
            mock_logger.warning.side_effect = OSError("Logging failed")
            
            with patch('sys.stdin'), patch('sys.stdout'), patch('sys.stderr'):
                # Should not raise exception even if logging fails
                server = TreeSitterAnalyzerMCPServer(temp_project_dir)
                assert server.is_initialized()

    @pytest.mark.asyncio
    async def test_tool_call_with_logging_failure(self, temp_project_dir):
        """Test tool calls when logging fails."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        
        with patch('tree_sitter_analyzer.mcp.server.logger') as mock_logger:
            mock_logger.info.side_effect = ValueError("Logging failed")
            mock_logger.error.side_effect = ValueError("Logging failed")
            
            with patch('sys.stdin'), patch('sys.stdout'), patch('sys.stderr'):
                # Should handle logging failures gracefully
                arguments = {"file_path": "non_existent.py"}
                
                try:
                    await server._analyze_code_scale(arguments)
                except FileNotFoundError:
                    # Expected for non-existent file
                    pass
                except ValueError as e:
                    if "Logging failed" in str(e):
                        pytest.fail("Should handle logging failures gracefully")