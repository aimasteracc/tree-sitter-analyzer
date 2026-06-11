"""
Comprehensive tests for MCP server functionality — initialization, code analysis, file metrics, and creation.
"""

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tree_sitter_analyzer.mcp.server import (
    TreeSitterAnalyzerMCPServer,
)
from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError


class TestTreeSitterAnalyzerMCPServerInitialization:
    """Test MCP server initialization and setup."""

    def test_server_initialization_success(self, temp_project_dir):
        """Test successful server initialization."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        assert server.is_initialized()
        # Check project root through security validator
        actual_project_root = getattr(
            getattr(server.security_validator, "boundary_manager", None),
            "project_root",
            None,
        )
        assert actual_project_root == str(temp_project_dir)
        assert server.name == "tree-sitter-analyzer-mcp"
        assert server.version is not None
        assert hasattr(server, "analysis_engine")
        assert hasattr(server, "security_validator")

    def test_server_initialization_with_tools(self, temp_project_dir):
        """Test server initialization includes all required tools."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        # Check core tools
        assert hasattr(server, "query_tool")
        assert hasattr(server, "read_partial_tool")
        assert hasattr(server, "table_format_tool")
        assert hasattr(server, "analyze_scale_tool")
        assert hasattr(server, "list_files_tool")
        assert hasattr(server, "search_content_tool")
        assert hasattr(server, "find_and_grep_tool")

    def test_server_initialization_with_resources(self, temp_project_dir):
        """Test server initialization includes required resources."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        assert hasattr(server, "code_file_resource")
        assert hasattr(server, "project_stats_resource")

    def test_server_initialization_with_universal_tool(self, temp_project_dir):
        """Test server initialization with optional universal tool."""
        with patch("tree_sitter_analyzer.mcp.server.UniversalAnalyzeTool") as mock_tool:
            mock_instance = Mock()
            mock_tool.return_value = mock_instance

            server = TreeSitterAnalyzerMCPServer(temp_project_dir)

            assert hasattr(server, "universal_analyze_tool")
            assert server.universal_analyze_tool == mock_instance

    def test_server_initialization_without_universal_tool(self, temp_project_dir):
        """Test server initialization when universal tool is not available."""
        with patch(
            "tree_sitter_analyzer.mcp.server.UniversalAnalyzeTool",
            side_effect=ImportError,
        ):
            server = TreeSitterAnalyzerMCPServer(temp_project_dir)

            assert server.universal_analyze_tool is None

    def test_ensure_initialized_success(self, temp_project_dir):
        """Test _ensure_initialized when server is initialized."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        # Should not raise any exception
        server._ensure_initialized()

    def test_ensure_initialized_failure(self, temp_project_dir):
        """Test _ensure_initialized when server is not initialized."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        server._initialization_complete = False

        with pytest.raises(RuntimeError, match="Server not fully initialized"):
            server._ensure_initialized()


class TestTreeSitterAnalyzerMCPServerCodeAnalysis:
    """Test MCP server code analysis functionality."""

    @pytest.fixture
    def sample_python_file(self, temp_project_dir):
        """Create a sample Python file for testing."""
        file_path = Path(temp_project_dir) / "sample.py"
        content = '''
def hello_world():
    """Say hello to the world."""
    print("Hello, World!")

class Calculator:
    """A simple calculator class."""

    def add(self, a, b):
        """Add two numbers."""
        return a + b

    def multiply(self, a, b):
        """Multiply two numbers."""
        return a * b

# This is a comment
x = 42
'''
        file_path.write_text(content)
        return str(file_path)

    @pytest.mark.asyncio
    async def test_analyze_code_scale_success(
        self, temp_project_dir, sample_python_file
    ):
        """Test successful code scale analysis."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        arguments = {
            "file_path": sample_python_file,
            "include_complexity": True,
            "include_details": False,
        }

        result = await server._analyze_code_scale(arguments)

        assert "file_path" in result
        assert "language" in result
        assert "metrics" in result
        assert result["language"] == "python"

        metrics = result["metrics"]
        assert "lines_total" in metrics
        assert "lines_code" in metrics
        assert "lines_comment" in metrics
        assert "lines_blank" in metrics
        assert "elements" in metrics
        assert "complexity" in metrics

    @pytest.mark.asyncio
    async def test_analyze_code_scale_with_details(
        self, temp_project_dir, sample_python_file
    ):
        """Test code scale analysis with detailed elements."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        arguments = {
            "file_path": sample_python_file,
            "include_complexity": True,
            "include_details": True,
        }

        result = await server._analyze_code_scale(arguments)

        assert "detailed_elements" in result
        assert isinstance(result["detailed_elements"], list)

    @pytest.mark.asyncio
    async def test_analyze_code_scale_missing_file_path(self, temp_project_dir):
        """Test code scale analysis with missing file_path."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        arguments = {}

        with pytest.raises(
            (ValueError, AnalysisError),
            match="file_path is required|Operation failed: file_path is required",
        ):
            await server._analyze_code_scale(arguments)

    @pytest.mark.asyncio
    async def test_analyze_code_scale_file_not_found(self, temp_project_dir):
        """Test code scale analysis with non-existent file."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        arguments = {"file_path": "non_existent_file.py"}

        with pytest.raises(FileNotFoundError):
            await server._analyze_code_scale(arguments)

    @pytest.mark.asyncio
    async def test_analyze_code_scale_not_initialized(self, temp_project_dir):
        """Test code scale analysis when server is not initialized."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        server._initialization_complete = False

        arguments = {"file_path": "test.py"}

        try:
            await server._analyze_code_scale(arguments)
            assert True
        except Exception as e:
            assert (
                "error" in str(e).lower()
                or "not found" in str(e).lower()
                or "required" in str(e).lower()
                or "initializing" in str(e).lower()
            )

    @pytest.mark.asyncio
    async def test_analyze_code_scale_with_universal_tool(self, temp_project_dir):
        """Test code scale analysis delegation to universal tool."""
        mock_universal_tool = AsyncMock()
        mock_universal_tool.execute.return_value = {"result": "from_universal_tool"}

        server = TreeSitterAnalyzerMCPServer(temp_project_dir)
        server.universal_analyze_tool = mock_universal_tool

        arguments = {}  # No file_path to trigger universal tool

        result = await server._analyze_code_scale(arguments)

        assert result == {"result": "from_universal_tool"}
        mock_universal_tool.execute.assert_called_once_with(arguments)


class TestTreeSitterAnalyzerMCPServerFileMetrics:
    """Test MCP server file metrics calculation."""

    def test_calculate_file_metrics_python(self, temp_project_dir):
        """Test file metrics calculation for Python file."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        test_file = Path(temp_project_dir) / "test.py"
        content = '''# This is a comment
def hello():
    """Docstring"""
    print("Hello")

# Another comment
x = 42

'''
        test_file.write_text(content)

        metrics = server._calculate_file_metrics(str(test_file), "python")

        assert metrics["total_lines"] == 8
        assert metrics["code_lines"] == 3
        assert metrics["comment_lines"] == 2
        assert metrics["blank_lines"] == 3

    def test_calculate_file_metrics_javascript(self, temp_project_dir):
        """Test file metrics calculation for JavaScript file."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        test_file = Path(temp_project_dir) / "test.js"
        content = """// Single line comment
function hello() {
    /* Multi-line
       comment */
    console.log("Hello");
}

// Another comment
const x = 42;
"""
        test_file.write_text(content)

        metrics = server._calculate_file_metrics(str(test_file), "javascript")

        assert metrics["total_lines"] == 9
        assert metrics["code_lines"] == 3
        assert metrics["comment_lines"] == 4

    def test_calculate_file_metrics_java(self, temp_project_dir):
        """Test file metrics calculation for Java file."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        test_file = Path(temp_project_dir) / "Test.java"
        content = """/**
 * JavaDoc comment
 */
public class Test {
    // Single line comment
    public void hello() {
        System.out.println("Hello");
    }
}
"""
        test_file.write_text(content)

        metrics = server._calculate_file_metrics(str(test_file), "java")

        assert metrics["total_lines"] == 9
        assert metrics["code_lines"] == 4
        assert metrics["comment_lines"] == 4

    def test_calculate_file_metrics_multiline_comments(self, temp_project_dir):
        """Test file metrics with complex multiline comments."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        test_file = Path(temp_project_dir) / "test.js"
        content = """/*
 * Multi-line comment
 * with multiple lines
 */
function test() {
    /* Inline comment */ return 42;
}
"""
        test_file.write_text(content)

        metrics = server._calculate_file_metrics(str(test_file), "javascript")

        assert metrics["comment_lines"] == 5

    def test_calculate_file_metrics_error_handling(self, temp_project_dir):
        """Test file metrics calculation error handling."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        metrics = server._calculate_file_metrics("non_existent.py", "python")

        assert metrics["total_lines"] == 0
        assert metrics["code_lines"] == 0
        assert metrics["comment_lines"] == 0
        assert metrics["blank_lines"] == 0


class TestTreeSitterAnalyzerMCPServerCreation:
    """Test MCP server creation and configuration."""

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    def test_create_server_success(self, temp_project_dir):
        """Test successful server creation."""
        with patch("tree_sitter_analyzer.mcp.server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server_class.return_value = mock_server

            server = TreeSitterAnalyzerMCPServer(temp_project_dir)
            result = server.create_server()

            assert result == mock_server
            mock_server_class.assert_called_once_with(server.name)

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", False)
    def test_create_server_mcp_unavailable(self, temp_project_dir):
        """Test server creation when MCP is unavailable."""
        server = TreeSitterAnalyzerMCPServer(temp_project_dir)

        with pytest.raises(RuntimeError, match="MCP library not available"):
            server.create_server()

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    def test_create_server_tool_registration(self, temp_project_dir):
        """Test that tools are properly registered."""
        with patch("tree_sitter_analyzer.mcp.server.Server") as mock_server_class:
            mock_server = Mock()
            mock_server_class.return_value = mock_server

            server = TreeSitterAnalyzerMCPServer(temp_project_dir)
            server.create_server()

            # Verify decorators were called
            assert mock_server.list_tools.called
            assert mock_server.call_tool.called
            assert mock_server.list_resources.called
            assert mock_server.read_resource.called

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @pytest.mark.asyncio
    async def test_handle_list_tools(self, temp_project_dir):
        """Test tool listing functionality."""
        with patch("tree_sitter_analyzer.mcp.server.Server") as mock_server_class:
            mock_server = Mock()
            captured_handlers = {}

            def capture_decorator(name):
                def decorator(func):
                    captured_handlers[name] = func
                    return func

                return decorator

            mock_server.list_tools.return_value = capture_decorator("list_tools")
            mock_server_class.return_value = mock_server

            server = TreeSitterAnalyzerMCPServer(temp_project_dir)
            server.create_server()

            assert "list_tools" in captured_handlers, (
                "list_tools handler was not registered"
            )
            list_tools_handler = captured_handlers["list_tools"]
            tools = await list_tools_handler()

            # Wave C2: the listed surface is the 8 facades + set_project_path.
            assert len(tools) == 9
            tool_names = [tool.name for tool in tools]
            for facade in (
                "search",
                "nav",
                "structure",
                "health",
                "edit",
                "project",
                "index",
                "viz",
            ):
                assert facade in tool_names, facade
            assert "set_project_path" in tool_names

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @pytest.mark.asyncio
    async def test_handle_list_resources(self, temp_project_dir):
        """Test resource listing functionality."""
        with patch("tree_sitter_analyzer.mcp.server.Server") as mock_server_class:
            mock_server = Mock()
            captured_handlers = {}

            def capture_decorator(name):
                def decorator(func):
                    captured_handlers[name] = func
                    return func

                return decorator

            mock_server.list_resources.return_value = capture_decorator(
                "list_resources"
            )
            mock_server_class.return_value = mock_server

            server = TreeSitterAnalyzerMCPServer(temp_project_dir)
            server.create_server()

            assert "list_resources" in captured_handlers, (
                "list_resources handler was not registered"
            )
            list_resources_handler = captured_handlers["list_resources"]
            resources = await list_resources_handler()

            assert len(resources) == 3
            resource_names = [resource.name for resource in resources]
            assert "code_file" in resource_names
            assert "project_stats" in resource_names
            assert "Hyphae selector result" in resource_names
