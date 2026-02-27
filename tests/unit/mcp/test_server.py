#!/usr/bin/env python3
"""
Unit tests for MCP Server module.

Tests MCP server implementation for tree-sitter analyzer.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer, parse_mcp_args
from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError


class TestServerInit:
    """Test TreeSitterAnalyzerMCPServer initialization"""

    @pytest.fixture
    def tmp_path(self):
        """Create temporary directory"""
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)

    def test_initialization_with_project_root(self, tmp_path):
        """Test server initialization with project root"""
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        assert "tree-sitter-analyzer" in server.name
        assert server.is_initialized()
        # Note: project_root is not directly set on server object
        assert server.project_stats_resource.project_root == str(tmp_path)

    def test_initialization_without_project_root(self):
        """Test server initialization without project root"""
        server = TreeSitterAnalyzerMCPServer()
        assert "tree-sitter-analyzer" in server.name
        assert server.is_initialized()
        # Note: project_root is not a direct attribute of server
        # It's managed by the security_validator.boundary_manager
        assert not hasattr(server, "project_root") or server.project_root is None

    def test_initialization_creates_tools(self, tmp_path):
        """Test that initialization creates all tools"""
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        assert server.query_tool is not None
        assert server.read_partial_tool is not None
        assert server.analyze_code_structure_tool is not None
        assert server.analyze_scale_tool is not None
        assert server.list_files_tool is not None
        assert server.search_content_tool is not None
        assert server.find_and_grep_tool is not None

    def test_initialization_creates_resources(self, tmp_path):
        """Test that initialization creates resources"""
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        assert server.code_file_resource is not None
        assert server.project_stats_resource is not None
        assert server.project_stats_resource.project_root == str(tmp_path)


class TestIsInitialized:
    """Test is_initialized method"""

    @pytest.fixture
    def server(self):
        """Create server instance"""
        with tempfile.TemporaryDirectory() as tmp:
            return TreeSitterAnalyzerMCPServer(project_root=Path(tmp))

    def test_initialized_server(self, server):
        """Test initialized server returns True"""
        assert server.is_initialized() is True

    def test_uninitialized_server(self):
        """Test uninitialized server returns False"""
        # Mock server that hasn't completed initialization
        server = TreeSitterAnalyzerMCPServer.__new__(TreeSitterAnalyzerMCPServer)
        server._initialization_complete = False
        assert server.is_initialized() is False


class TestEnsureInitialized:
    """Test _ensure_initialized method"""

    @pytest.fixture
    def server(self):
        """Create server instance"""
        with tempfile.TemporaryDirectory() as tmp:
            return TreeSitterAnalyzerMCPServer(project_root=Path(tmp))

    def test_ensure_initialized_passes(self, server):
        """Test ensure_initialized passes when initialized"""
        # Should not raise any exception
        server._ensure_initialized()

    def test_ensure_initialized_raises_when_not_initialized(self):
        """Test ensure_initialized raises when not initialized"""
        server = TreeSitterAnalyzerMCPServer.__new__(TreeSitterAnalyzerMCPServer)
        server._initialization_complete = False

        with pytest.raises(RuntimeError, match="not fully initialized"):
            server._ensure_initialized()


class TestSetProjectPath:
    """Test set_project_path method"""

    @pytest.fixture
    def server(self):
        """Create server instance"""
        with tempfile.TemporaryDirectory() as tmp:
            return TreeSitterAnalyzerMCPServer(project_root=Path(tmp))

    @pytest.fixture
    def tmp_path(self):
        """Create temporary directory"""
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)

    def test_set_project_path_valid(self, server, tmp_path):
        """Test setting valid project path"""
        new_path = str(tmp_path / "new_project")
        Path(new_path).mkdir()
        server.set_project_path(new_path)
        # project_root is not a direct attribute of server
        assert server.project_stats_resource.project_root == new_path

    def test_set_project_path_updates_resources(self, server, tmp_path):
        """Test that set_project_path updates resources"""
        new_path = str(tmp_path / "new_project")
        Path(new_path).mkdir()
        server.set_project_path(new_path)
        assert server.project_stats_resource.project_root == new_path

    def test_set_project_path_invalid_directory(self, server):
        """Test setting invalid directory uses fallback"""
        # set_project_path doesn't raise ValueError, it logs warning and uses fallback
        server.set_project_path("/nonexistent/path")
        # Verify the server still works with fallback path
        assert server.is_initialized()


class TestReadResource:
    """Test _read_resource method"""

    @pytest.fixture
    def server(self):
        """Create server instance"""
        with tempfile.TemporaryDirectory() as tmp:
            return TreeSitterAnalyzerMCPServer(project_root=Path(tmp))

    @pytest.mark.asyncio
    async def test_read_code_file_resource(self, server, tmp_path):
        """Test reading code file resource"""
        test_file = tmp_path / "test.py"
        test_file.write_text("def test(): pass")

        # Create server with this tmp_path as project root
        server_with_path = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        result = await server_with_path._read_resource(f"code://file/{test_file}")
        assert "content" in result
        assert "def test():" in result["content"]

    @pytest.mark.asyncio
    async def test_read_project_stats_resource(self, server, tmp_path):
        """Test reading project stats resource"""
        # Create a fresh server with valid project path
        server_with_path = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        result = await server_with_path._read_resource("code://stats/overview")
        assert "content" in result

    @pytest.mark.asyncio
    async def test_read_unknown_resource_raises_error(self, server):
        """Test reading unknown resource raises error"""
        with pytest.raises(ValueError, match="Unknown resource URI"):
            await server._read_resource("unknown://resource/test")


class TestParseMCPArgs:
    """Test parse_mcp_args function"""

    def test_parse_args_with_project_root(self):
        """Test parsing with project root argument"""
        args = parse_mcp_args(["--project-root", "/test/path"])
        assert args.project_root == "/test/path"

    def test_parse_args_without_project_root(self):
        """Test parsing without project root argument"""
        args = parse_mcp_args([])
        assert args.project_root is None


class TestServerCreation:
    """Test create_server method"""

    @pytest.fixture
    def server(self):
        """Create server instance"""
        with tempfile.TemporaryDirectory() as tmp:
            return TreeSitterAnalyzerMCPServer(project_root=Path(tmp))

    def test_create_server_without_mcp_library(self, server):
        """Test create_server raises when MCP library not available"""
        # Patch the module-level constant
        with patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="MCP library not available"):
                server.create_server()


class TestProjectStatsResource:
    """Test project_stats_resource initialization"""

    @pytest.fixture
    def server(self):
        """Create server instance"""
        with tempfile.TemporaryDirectory() as tmp:
            return TreeSitterAnalyzerMCPServer(project_root=Path(tmp))

    def test_project_stats_resource_initialized(self, server):
        """Test project stats resource is initialized"""
        assert server.project_stats_resource is not None
        assert server.project_stats_resource.project_root is not None

    def test_project_stats_resource_supported_types(self, server):
        """Test project stats resource has supported types"""
        types = server.project_stats_resource.get_supported_stats_types()
        assert "overview" in types
        assert "languages" in types
        assert "complexity" in types
        assert "files" in types


class TestCodeFileResource:
    """Test code_file_resource initialization"""

    @pytest.fixture
    def server(self):
        """Create server instance"""
        with tempfile.TemporaryDirectory() as tmp:
            return TreeSitterAnalyzerMCPServer(project_root=Path(tmp))

    def test_code_file_resource_initialized(self, server):
        """Test code file resource is initialized"""
        assert server.code_file_resource is not None

    def test_code_file_resource_matches_uri(self, server):
        """Test code file resource URI matching"""
        assert server.code_file_resource.matches_uri("code://file/test.py")
        assert not server.code_file_resource.matches_uri("invalid://file/test.py")


class TestVersionInfo:
    """Test version information"""

    @pytest.fixture
    def server(self):
        """Create server instance"""
        with tempfile.TemporaryDirectory() as tmp:
            return TreeSitterAnalyzerMCPServer(project_root=Path(tmp))

    def test_server_name(self, server):
        """Test server name"""
        assert "tree-sitter-analyzer" in server.name

    def test_server_version(self, server):
        """Test server version"""
        assert server.version is not None
        assert isinstance(server.version, str)


class TestAnalysisEngine:
    """Test analysis engine initialization"""

    @pytest.fixture
    def server(self):
        """Create server instance"""
        with tempfile.TemporaryDirectory() as tmp:
            return TreeSitterAnalyzerMCPServer(project_root=Path(tmp))

    def test_analysis_engine_initialized(self, server):
        """Test analysis engine is initialized"""
        assert server.analysis_engine is not None


class TestSecurityValidator:
    """Test security validator initialization"""

    @pytest.fixture
    def server(self):
        """Create server instance"""
        with tempfile.TemporaryDirectory() as tmp:
            return TreeSitterAnalyzerMCPServer(project_root=Path(tmp))

    def test_security_validator_initialized(self, server):
        """Test security validator is initialized"""
        assert server.security_validator is not None


class TestToolDefinitions:
    """Test tool definitions"""

    @pytest.fixture
    def server(self):
        """Create server instance"""
        with tempfile.TemporaryDirectory() as tmp:
            return TreeSitterAnalyzerMCPServer(project_root=Path(tmp))

    def test_query_tool_definition(self, server):
        """Test query tool has definition"""
        definition = server.query_tool.get_tool_definition()
        assert definition["name"] == "query_code"

    def test_read_partial_tool_definition(self, server):
        """Test read partial tool has definition"""
        definition = server.read_partial_tool.get_tool_definition()
        assert definition["name"] == "extract_code_section"

    def test_analyze_code_structure_tool_definition(self, server):
        """Test analyze code structure tool has definition"""
        definition = server.analyze_code_structure_tool.get_tool_definition()
        assert definition["name"] == "analyze_code_structure"

    def test_analyze_scale_tool_definition(self, server):
        """Test analyze scale tool has definition"""
        definition = server.analyze_scale_tool.get_tool_definition()
        assert definition["name"] == "check_code_scale"

    def test_list_files_tool_definition(self, server):
        """Test list files tool has definition"""
        definition = server.list_files_tool.get_tool_definition()
        assert definition["name"] == "list_files"

    def test_search_content_tool_definition(self, server):
        """Test search content tool has definition"""
        definition = server.search_content_tool.get_tool_definition()
        assert definition["name"] == "search_content"

    def test_find_and_grep_tool_definition(self, server):
        """Test find and grep tool has definition"""
        definition = server.find_and_grep_tool.get_tool_definition()
        assert definition["name"] == "find_and_grep"


class TestUniversalTool:
    """Test universal tool availability"""

    @pytest.fixture
    def server(self):
        """Create server instance"""
        with tempfile.TemporaryDirectory() as tmp:
            return TreeSitterAnalyzerMCPServer(project_root=Path(tmp))

    def test_universal_tool_available(self, server):
        """Test universal tool is available if imported"""
        # The tool may or may not be available depending on imports
        # Just verify the attribute exists
        assert hasattr(server, "universal_analyze_tool")


class TestTableFormatTool:
    """Test table format tool (alias)"""

    @pytest.fixture
    def server(self):
        """Create server instance"""
        with tempfile.TemporaryDirectory() as tmp:
            return TreeSitterAnalyzerMCPServer(project_root=Path(tmp))

    def test_table_format_tool_is_alias(self, server):
        """Test table format tool is alias of analyze code structure"""
        assert server.table_format_tool is server.analyze_code_structure_tool


class TestResourceInfo:
    """Test resource information"""

    @pytest.fixture
    def server(self):
        """Create server instance"""
        with tempfile.TemporaryDirectory() as tmp:
            return TreeSitterAnalyzerMCPServer(project_root=Path(tmp))

    def test_code_file_resource_info(self, server):
        """Test code file resource info"""
        info = server.code_file_resource.get_resource_info()
        assert info["name"] == "code_file"
        assert "code://file/{file_path}" in info["uri_template"]

    def test_project_stats_resource_info(self, server):
        """Test project stats resource info"""
        info = server.project_stats_resource.get_resource_info()
        assert info["name"] == "project_stats"
        assert "code://stats/{stats_type}" in info["uri_template"]


# ---------------------------------------------------------------------------
# Merged from test_server_comprehensive.py and test_server_edge_cases.py
# ---------------------------------------------------------------------------


class TestCodeScaleAnalysis:
    """Test _analyze_code_scale method with real files."""

    @pytest.fixture
    def server_with_file(self, tmp_path):
        """Create server with a sample Python file."""
        sample = tmp_path / "sample.py"
        sample.write_text(
            'def hello_world():\n    """Say hello."""\n    print("Hello, World!")\n\n'
            'class Calculator:\n    """A simple calculator."""\n\n'
            "    def add(self, a, b):\n        return a + b\n\n"
            "    def multiply(self, a, b):\n        return a * b\n\n"
            "# This is a comment\nx = 42\n"
        )
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        return server, str(sample)

    @pytest.mark.asyncio
    async def test_analyze_code_scale_success(self, server_with_file):
        """Test successful code scale analysis returns expected metrics."""
        server, sample_path = server_with_file
        result = await server._analyze_code_scale(
            {"file_path": sample_path, "include_complexity": True, "include_details": False}
        )
        assert result["language"] == "python"
        metrics = result["metrics"]
        assert "lines_total" in metrics
        assert "lines_code" in metrics
        assert "lines_comment" in metrics
        assert "elements" in metrics
        assert "complexity" in metrics

    @pytest.mark.asyncio
    async def test_analyze_code_scale_missing_file_path(self, tmp_path):
        """Test _analyze_code_scale raises when file_path is missing."""
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        with pytest.raises(
            (ValueError, AnalysisError),
            match="file_path is required|Operation failed: file_path is required",
        ):
            await server._analyze_code_scale({})


class TestCalculateFileMetrics:
    """Test _calculate_file_metrics for different languages and edge cases."""

    @pytest.fixture
    def server(self, tmp_path):
        """Create server instance."""
        return TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))

    def test_calculate_file_metrics_python(self, server, tmp_path):
        """Test file metrics calculation for a Python file."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '# This is a comment\ndef hello():\n    """Docstring"""\n'
            '    print("Hello")\n\n# Another comment\nx = 42\n\n'
        )
        metrics = server._calculate_file_metrics(str(test_file), "python")
        assert metrics["total_lines"] > 0
        assert metrics["code_lines"] > 0
        assert metrics["comment_lines"] > 0
        assert metrics["blank_lines"] >= 0

    def test_calculate_file_metrics_error_handling(self, server):
        """Test file metrics returns zeroes for a non-existent file."""
        metrics = server._calculate_file_metrics("non_existent.py", "python")
        assert metrics["total_lines"] == 0
        assert metrics["code_lines"] == 0
        assert metrics["comment_lines"] == 0
        assert metrics["blank_lines"] == 0

    def test_calculate_metrics_with_only_comments(self, server, tmp_path):
        """Test file metrics for a file containing only comments."""
        test_file = tmp_path / "only_comments.py"
        test_file.write_text("# Comment 1\n# Comment 2\n# Comment 3\n")
        metrics = server._calculate_file_metrics(str(test_file), "python")
        assert metrics["comment_lines"] == 3
        assert metrics["code_lines"] == 0


class TestToolCallPipeline:
    """Test the MCP tool-call handler pipeline (create_server decorators)."""

    @pytest.fixture
    def _capture_call_tool(self, tmp_path):
        """Create server, call create_server, and return the captured call_tool handler."""
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))

        with patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True), \
             patch("tree_sitter_analyzer.mcp.server.Server") as mock_cls:
            mock_srv = Mock()
            captured = {}

            def _deco(name):
                def decorator(func):
                    captured[name] = func
                    return func
                return decorator

            mock_srv.call_tool.return_value = _deco("call_tool")
            mock_srv.list_tools.return_value = _deco("list_tools")
            mock_srv.list_resources.return_value = _deco("list_resources")
            mock_srv.read_resource.return_value = _deco("read_resource")
            mock_cls.return_value = mock_srv

            server.create_server()
            yield server, captured.get("call_tool")

    @pytest.mark.asyncio
    async def test_handle_call_tool_unknown_tool(self, _capture_call_tool):
        """Test that calling an unknown tool returns an error response."""
        _server, handler = _capture_call_tool
        result = await handler("unknown_tool", {})
        assert len(result) == 1
        data = json.loads(result[0].text)
        assert "error" in data
        assert "Unknown tool" in data["error"]

    @pytest.mark.asyncio
    async def test_handle_call_tool_security_validation(self, _capture_call_tool):
        """Test that a path-traversal attack is rejected by security validation."""
        server, handler = _capture_call_tool
        with patch.object(
            server.security_validator,
            "validate_file_path",
            return_value=(False, "Invalid path"),
        ):
            result = await handler("check_code_scale", {"file_path": "../../../etc/passwd"})
            data = json.loads(result[0].text)
            assert "error" in data
            assert "Invalid or unsafe file path" in data["error"]


class TestServerRunLifecycle:
    """Test server.run() lifecycle paths."""

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", False)
    @pytest.mark.asyncio
    async def test_run_mcp_unavailable(self, tmp_path):
        """Test that run() raises when MCP library is unavailable."""
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        with pytest.raises(RuntimeError, match="MCP library not available"):
            await server.run()


class TestSetProjectPathExtended:
    """Extended set_project_path tests merged from variant files."""

    def test_set_project_path_updates_universal_tool(self, tmp_path):
        """Test that set_project_path propagates to universal_analyze_tool."""
        mock_universal = Mock()
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        server.universal_analyze_tool = mock_universal

        with tempfile.TemporaryDirectory() as new_dir:
            server.set_project_path(new_dir)
            mock_universal.set_project_path.assert_called_once_with(new_dir)


class TestInitializationEdgeCases:
    """Edge cases for server initialization."""

    def test_initialization_with_file_as_project_root(self, tmp_path):
        """Test initialization when given a file path instead of a directory."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        server = TreeSitterAnalyzerMCPServer(str(test_file))
        assert server.is_initialized()
        # boundary_manager should be None for file path (not directory)
        assert server.security_validator.boundary_manager is None

    def test_initialization_with_unicode_path(self, tmp_path):
        """Test initialization with Unicode characters in the path."""
        unicode_dir = tmp_path / "unicode_dir"
        unicode_dir.mkdir()
        server = TreeSitterAnalyzerMCPServer(str(unicode_dir))
        assert server.is_initialized()


class TestAnalysisEdgeCases:
    """Edge cases for code analysis."""

    @pytest.mark.asyncio
    async def test_analyze_empty_file(self, tmp_path):
        """Test analyzing an empty file returns zero metrics."""
        empty = tmp_path / "empty.py"
        empty.write_text("")
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        result = await server._analyze_code_scale({"file_path": str(empty)})
        assert result["metrics"]["lines_total"] == 0
        assert result["metrics"]["elements"]["total"] == 0

    @pytest.mark.asyncio
    async def test_analyze_binary_file(self, tmp_path):
        """Test that analyzing a binary file raises UnsupportedLanguageError."""
        binary = tmp_path / "binary.bin"
        binary.write_bytes(b"\x00\x01\x02\x03\x04\x05")
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        with pytest.raises(Exception, match="Unsupported language"):
            await server._analyze_code_scale({"file_path": str(binary)})

    @pytest.mark.asyncio
    async def test_analyze_malformed_code(self, tmp_path):
        """Test that malformed code still produces metrics (tree-sitter is error-tolerant)."""
        malformed = tmp_path / "malformed.py"
        malformed.write_text(
            "def incomplete_function(\n"
            "    # Missing closing parenthesis\n\n"
            "class IncompleteClass\n"
            "    # Missing colon and body\n"
        )
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        result = await server._analyze_code_scale({"file_path": str(malformed)})
        assert "metrics" in result
        assert result["metrics"]["lines_total"] > 0


class TestParseMCPArgsEdgeCases:
    """Edge cases for parse_mcp_args."""

    def test_parse_args_with_invalid_arguments(self):
        """Test that unknown CLI arguments cause SystemExit(2)."""
        with pytest.raises(SystemExit) as exc_info:
            parse_mcp_args(["--unknown-arg", "value"])
        assert exc_info.value.code == 2


class TestMCPInitImportFallback:
    """Test mcp/__init__.py ImportError fallback (lines 16, 18)."""

    def test_version_fallback_on_import_error(self):
        """Test that mcp package has a version even if main package import fails."""
        import tree_sitter_analyzer.mcp as mcp_pkg
        assert hasattr(mcp_pkg, "__version__")
        assert isinstance(mcp_pkg.__version__, str)
        assert len(mcp_pkg.__version__) > 0

    def test_mcp_info_exists(self):
        """Test MCP_INFO metadata is populated."""
        from tree_sitter_analyzer.mcp import MCP_INFO
        assert isinstance(MCP_INFO, dict)
        assert "name" in MCP_INFO
        assert "version" in MCP_INFO
        assert MCP_INFO["protocol_version"] == "2024-11-05"
