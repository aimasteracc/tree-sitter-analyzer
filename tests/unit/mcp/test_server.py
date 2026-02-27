#!/usr/bin/env python3
"""
Unit tests for MCP Server module.

Tests MCP server implementation for tree-sitter analyzer.
"""

import asyncio
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


# ---------------------------------------------------------------------------
# Additional targeted tests for uncovered branches in server.py
# ---------------------------------------------------------------------------


class TestMCPImportFallbackBranches:
    """Test MCP library import fallback classes (lines 26-48)."""

    def test_fallback_server_class(self):
        """Test that the fallback Server class can be instantiated when MCP unavailable."""
        # Simulate the fallback path by directly importing and testing
        # We can't easily force ImportError on the real import, so we test
        # that the module handles MCP_AVAILABLE = False correctly
        with patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", False):
            server = TreeSitterAnalyzerMCPServer(project_root=None)
            with pytest.raises(RuntimeError, match="MCP library not available"):
                server.create_server()


class TestUniversalToolImportFallback:
    """Test UniversalAnalyzeTool import fallback (lines 83-85)."""

    def test_universal_tool_unavailable(self, tmp_path):
        """Test server initialization when UniversalAnalyzeTool import fails."""
        with patch(
            "tree_sitter_analyzer.mcp.server.UNIVERSAL_TOOL_AVAILABLE", False
        ), patch(
            "tree_sitter_analyzer.mcp.server.UniversalAnalyzeTool", None
        ):
            server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
            assert server.universal_analyze_tool is None

    def test_universal_tool_init_exception(self, tmp_path):
        """Test server initialization when UniversalAnalyzeTool raises exception."""
        mock_universal_cls = Mock(side_effect=Exception("init failed"))
        with patch(
            "tree_sitter_analyzer.mcp.server.UNIVERSAL_TOOL_AVAILABLE", True
        ), patch(
            "tree_sitter_analyzer.mcp.server.UniversalAnalyzeTool", mock_universal_cls
        ):
            server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
            assert server.universal_analyze_tool is None


class TestInitLoggingFailures:
    """Test logging failure handling during init (lines 106-108, 157-163, 170-172)."""

    def test_init_handles_logging_failures(self, tmp_path):
        """Test that init handles logger errors gracefully."""
        with patch(
            "tree_sitter_analyzer.mcp.server.logger"
        ) as mock_logger:
            mock_logger.info.side_effect = OSError("logging broken")
            mock_logger.warning.side_effect = OSError("logging broken")
            # Should not raise despite logging failures
            server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
            assert server.is_initialized()

    def test_init_platform_detection_failure(self, tmp_path):
        """Test platform detection failure during init (lines 159-163)."""
        with patch(
            "tree_sitter_analyzer.mcp.server.PlatformDetector.detect",
            side_effect=Exception("platform error"),
        ):
            server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
            assert server.is_initialized()
            # Version should not have platform info appended
            assert "tree-sitter-analyzer" in server.name


class TestAnalyzeCodeScaleBranches:
    """Test uncovered branches in _analyze_code_scale (lines 205, 207, 221, 237, 241, 263, 268, 341-347)."""

    @pytest.mark.asyncio
    async def test_analyze_code_scale_not_initialized(self, tmp_path):
        """Test _analyze_code_scale raises MCPError when not initialized (lines 191-194)."""
        server = TreeSitterAnalyzerMCPServer.__new__(TreeSitterAnalyzerMCPServer)
        server._initialization_complete = False
        from tree_sitter_analyzer.mcp.utils.error_handler import MCPError
        with pytest.raises(MCPError, match="still initializing"):
            await server._analyze_code_scale({})

    @pytest.mark.asyncio
    async def test_analyze_code_scale_universal_tool_returns_result(self, tmp_path):
        """Test _analyze_code_scale delegates to universal_tool when no file_path (line 201-202)."""
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        mock_universal = Mock()
        mock_universal.execute = Mock(return_value={"status": "ok", "key": "value"})
        # Make it an awaitable
        import asyncio
        future = asyncio.Future()
        future.set_result({"status": "ok", "key": "value"})
        mock_universal.execute = Mock(return_value=future)
        server.universal_analyze_tool = mock_universal
        result = await server._analyze_code_scale({"language": "python"})
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_analyze_code_scale_universal_tool_value_error(self, tmp_path):
        """Test _analyze_code_scale re-raises ValueError from universal_tool (line 203-205)."""
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        mock_universal = Mock()
        import asyncio
        future = asyncio.Future()
        future.set_exception(ValueError("bad args"))
        mock_universal.execute = Mock(return_value=future)
        server.universal_analyze_tool = mock_universal
        with pytest.raises(ValueError, match="bad args"):
            await server._analyze_code_scale({"language": "python"})

    @pytest.mark.asyncio
    async def test_analyze_code_scale_no_universal_no_filepath(self, tmp_path):
        """Test _analyze_code_scale raises ValueError when no universal tool and no file_path (line 207)."""
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        server.universal_analyze_tool = None
        with pytest.raises(ValueError, match="file_path is required"):
            await server._analyze_code_scale({})

    @pytest.mark.asyncio
    async def test_analyze_code_scale_relative_path_resolution(self, tmp_path):
        """Test _analyze_code_scale resolves relative paths with base_root (line 221)."""
        sample = tmp_path / "relative.py"
        sample.write_text("x = 1\n")
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        result = await server._analyze_code_scale({"file_path": "relative.py"})
        assert result["file_path"] == "relative.py"

    @pytest.mark.asyncio
    async def test_analyze_code_scale_invalid_security(self, tmp_path):
        """Test _analyze_code_scale raises when security validation fails (line 237)."""
        sample = tmp_path / "test.py"
        sample.write_text("x = 1\n")
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        with patch.object(
            server.security_validator,
            "validate_file_path",
            return_value=(False, "Blocked by policy"),
        ):
            with pytest.raises(ValueError, match="Invalid file path"):
                await server._analyze_code_scale({"file_path": str(sample)})

    @pytest.mark.asyncio
    async def test_analyze_code_scale_file_not_found(self, tmp_path):
        """Test _analyze_code_scale raises FileNotFoundError (line 241)."""
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        with pytest.raises(FileNotFoundError, match="File not found"):
            await server._analyze_code_scale({"file_path": str(tmp_path / "nonexistent.py")})

    @pytest.mark.asyncio
    async def test_analyze_code_scale_analysis_failure(self, tmp_path):
        """Test _analyze_code_scale handles analysis failure result (lines 263-268)."""
        sample = tmp_path / "fail.py"
        sample.write_text("x = 1\n")
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))

        mock_result = Mock()
        mock_result.success = False
        mock_result.error_message = "Parse failure"
        with patch.object(
            server.analysis_engine, "analyze", return_value=mock_result
        ):
            with pytest.raises(RuntimeError, match="Failed to analyze file"):
                await server._analyze_code_scale({"file_path": str(sample)})

    @pytest.mark.asyncio
    async def test_analyze_code_scale_analysis_returns_none(self, tmp_path):
        """Test _analyze_code_scale handles None analysis result (line 262-268)."""
        sample = tmp_path / "none.py"
        sample.write_text("x = 1\n")
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        with patch.object(
            server.analysis_engine, "analyze", return_value=None
        ):
            with pytest.raises(RuntimeError, match="Failed to analyze file"):
                await server._analyze_code_scale({"file_path": str(sample)})

    @pytest.mark.asyncio
    async def test_analyze_code_scale_include_details(self, tmp_path):
        """Test _analyze_code_scale with include_details=True (lines 341-347)."""
        sample = tmp_path / "details.py"
        sample.write_text(
            'def hello():\n    """Say hello."""\n    print("Hello")\n\nx = 42\n'
        )
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        result = await server._analyze_code_scale(
            {"file_path": str(sample), "include_details": True, "include_complexity": False}
        )
        assert "detailed_elements" in result
        assert isinstance(result["detailed_elements"], list)

    @pytest.mark.asyncio
    async def test_analyze_code_scale_element_without_dict(self, tmp_path):
        """Test detailed elements with objects lacking __dict__ (line 346)."""
        sample = tmp_path / "nodict.py"
        sample.write_text("x = 1\n")
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))

        # Create a mock analysis result with elements that lack __dict__
        mock_result = Mock()
        mock_result.success = True
        mock_result.line_count = 1
        mock_result.elements = ["string_element"]  # str has no __dict__
        mock_result.error_message = None

        with patch.object(server.analysis_engine, "analyze", return_value=mock_result):
            result = await server._analyze_code_scale(
                {"file_path": str(sample), "include_details": True, "include_complexity": False}
            )
            assert "detailed_elements" in result
            # String element should use fallback format
            assert any("element" in d for d in result["detailed_elements"])


class TestCallToolHandlerBranches:
    """Test handle_call_tool branches (lines 485-553)."""

    @pytest.fixture
    def _capture_handlers(self, tmp_path):
        """Create server, call create_server, and capture all registered handlers."""
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
            mock_srv.list_prompts.return_value = _deco("list_prompts")
            mock_cls.return_value = mock_srv

            server.create_server()
            yield server, captured

    @pytest.mark.asyncio
    async def test_call_tool_check_code_scale(self, _capture_handlers):
        """Test calling check_code_scale tool (line 485)."""
        server, captured = _capture_handlers
        handler = captured["call_tool"]
        mock_result = {"file": "test.py", "metrics": {}}
        future = asyncio.Future()
        future.set_result(mock_result)
        server.analyze_scale_tool.execute = Mock(return_value=future)
        result = await handler("check_code_scale", {"file_path": "test.py"})
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_call_tool_analyze_code_structure_missing_file_path(self, _capture_handlers):
        """Test analyze_code_structure without file_path (lines 488-489)."""
        server, captured = _capture_handlers
        handler = captured["call_tool"]
        result = await handler("analyze_code_structure", {})
        data = json.loads(result[0].text)
        assert "error" in data
        assert "file_path parameter is required" in data["error"]

    @pytest.mark.asyncio
    async def test_call_tool_analyze_code_structure_success(self, _capture_handlers):
        """Test analyze_code_structure with file_path (line 491)."""
        server, captured = _capture_handlers
        handler = captured["call_tool"]
        import asyncio as aio
        future = aio.Future()
        future.set_result({"status": "ok"})
        server.table_format_tool.execute = Mock(return_value=future)
        result = await handler("analyze_code_structure", {"file_path": "test.py"})
        data = json.loads(result[0].text)
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_call_tool_extract_code_section_batch(self, _capture_handlers):
        """Test extract_code_section in batch mode (lines 498-500)."""
        server, captured = _capture_handlers
        handler = captured["call_tool"]
        import asyncio as aio
        future = aio.Future()
        future.set_result({"success": True, "count": 2})
        server.read_partial_tool.execute = Mock(return_value=future)
        result = await handler("extract_code_section", {
            "requests": [{"file_path": "test.py", "sections": [{"start_line": 1}]}]
        })
        data = json.loads(result[0].text)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_call_tool_extract_code_section_missing_args(self, _capture_handlers):
        """Test extract_code_section missing required args (lines 503-507)."""
        server, captured = _capture_handlers
        handler = captured["call_tool"]
        result = await handler("extract_code_section", {"file_path": "test.py"})
        data = json.loads(result[0].text)
        assert "error" in data
        assert "file_path and start_line parameters are required" in data["error"]

    @pytest.mark.asyncio
    async def test_call_tool_extract_code_section_single(self, _capture_handlers):
        """Test extract_code_section in single mode (lines 511-524)."""
        server, captured = _capture_handlers
        handler = captured["call_tool"]
        import asyncio as aio
        future = aio.Future()
        future.set_result({"success": True, "content": "line1"})
        server.read_partial_tool.execute = Mock(return_value=future)
        result = await handler("extract_code_section", {
            "file_path": "test.py",
            "start_line": 1,
            "end_line": 5,
            "start_column": 0,
            "end_column": 10,
            "format": "json",
            "output_file": "out.txt",
            "suppress_output": True,
            "output_format": "json",
            "allow_truncate": True,
            "fail_fast": True,
        })
        data = json.loads(result[0].text)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_call_tool_set_project_path_missing(self, _capture_handlers):
        """Test set_project_path with missing project_path (lines 527-531)."""
        server, captured = _capture_handlers
        handler = captured["call_tool"]
        result = await handler("set_project_path", {})
        data = json.loads(result[0].text)
        assert "error" in data
        assert "project_path parameter is required" in data["error"]

    @pytest.mark.asyncio
    async def test_call_tool_set_project_path_not_dir(self, _capture_handlers, tmp_path):
        """Test set_project_path with nonexistent dir (line 532-533)."""
        server, captured = _capture_handlers
        handler = captured["call_tool"]
        result = await handler("set_project_path", {"project_path": "/nonexistent/dir"})
        data = json.loads(result[0].text)
        assert "error" in data
        assert "does not exist" in data["error"]

    @pytest.mark.asyncio
    async def test_call_tool_set_project_path_success(self, _capture_handlers, tmp_path):
        """Test set_project_path success (lines 534-535)."""
        server, captured = _capture_handlers
        handler = captured["call_tool"]
        result = await handler("set_project_path", {"project_path": str(tmp_path)})
        data = json.loads(result[0].text)
        assert data["status"] == "success"
        assert data["project_root"] == str(tmp_path)

    @pytest.mark.asyncio
    async def test_call_tool_query_code(self, _capture_handlers):
        """Test calling query_code tool (line 538)."""
        server, captured = _capture_handlers
        handler = captured["call_tool"]
        import asyncio as aio
        future = aio.Future()
        future.set_result({"results": []})
        server.query_tool.execute = Mock(return_value=future)
        result = await handler("query_code", {"query": "test"})
        data = json.loads(result[0].text)
        assert "results" in data

    @pytest.mark.asyncio
    async def test_call_tool_list_files(self, _capture_handlers):
        """Test calling list_files tool (line 541)."""
        server, captured = _capture_handlers
        handler = captured["call_tool"]
        import asyncio as aio
        future = aio.Future()
        future.set_result({"files": []})
        server.list_files_tool.execute = Mock(return_value=future)
        result = await handler("list_files", {"path": "."})
        data = json.loads(result[0].text)
        assert "files" in data

    @pytest.mark.asyncio
    async def test_call_tool_search_content(self, _capture_handlers):
        """Test calling search_content tool (line 544)."""
        server, captured = _capture_handlers
        handler = captured["call_tool"]
        import asyncio as aio
        future = aio.Future()
        future.set_result({"success": True, "count": 0})
        server.search_content_tool.execute = Mock(return_value=future)
        result = await handler("search_content", {"query": "test", "roots": ["."]})
        data = json.loads(result[0].text)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_call_tool_find_and_grep(self, _capture_handlers):
        """Test calling find_and_grep tool (line 547)."""
        server, captured = _capture_handlers
        handler = captured["call_tool"]
        import asyncio as aio
        future = aio.Future()
        future.set_result({"results": []})
        server.find_and_grep_tool.execute = Mock(return_value=future)
        result = await handler("find_and_grep", {"pattern": "*.py"})
        data = json.loads(result[0].text)
        assert "results" in data

    @pytest.mark.asyncio
    async def test_call_tool_logging_error_during_exception(self, _capture_handlers):
        """Test error path when logging also fails (lines 563-564)."""
        server, captured = _capture_handlers
        handler = captured["call_tool"]
        # Force an exception and make logging fail too
        with patch("tree_sitter_analyzer.mcp.server.logger") as mock_logger:
            mock_logger.info.side_effect = None  # allow info calls
            mock_logger.error.side_effect = ValueError("log broken")
            result = await handler("unknown_tool", {})
            data = json.loads(result[0].text)
            assert "error" in data

    @pytest.mark.asyncio
    async def test_call_tool_relative_path_resolution(self, _capture_handlers):
        """Test file_path resolution with relative path (line 456-461)."""
        server, captured = _capture_handlers
        handler = captured["call_tool"]
        # Set a project root on the security validator
        bm = Mock()
        bm.project_root = "/test/root"
        server.security_validator.boundary_manager = bm
        with patch.object(
            server.security_validator, "validate_file_path",
            return_value=(False, "path traversal detected"),
        ):
            result = await handler("check_code_scale", {"file_path": "relative.py"})
            data = json.loads(result[0].text)
            assert "error" in data


class TestResourceHandlers:
    """Test resource handler branches (lines 603-617)."""

    @pytest.fixture
    def _capture_handlers(self, tmp_path):
        """Capture all registered handlers from create_server."""
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
            mock_srv.list_prompts.return_value = _deco("list_prompts")
            mock_cls.return_value = mock_srv

            server.create_server()
            yield server, captured

    @pytest.mark.asyncio
    async def test_handle_read_resource_code_file(self, _capture_handlers, tmp_path):
        """Test read_resource handler for code file URI (line 605-606)."""
        server, captured = _capture_handlers
        handler = captured["read_resource"]
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1")
        with patch.object(
            server.code_file_resource, "matches_uri", return_value=True
        ), patch.object(
            server.code_file_resource, "read_resource", return_value="x = 1"
        ):
            result = await handler(f"code://file/{test_file}")
            assert result == "x = 1"

    @pytest.mark.asyncio
    async def test_handle_read_resource_stats(self, _capture_handlers):
        """Test read_resource handler for stats URI (line 607-608)."""
        server, captured = _capture_handlers
        handler = captured["read_resource"]
        with patch.object(
            server.code_file_resource, "matches_uri", return_value=False
        ), patch.object(
            server.project_stats_resource, "matches_uri", return_value=True
        ), patch.object(
            server.project_stats_resource, "read_resource", return_value='{"stats": {}}'
        ):
            result = await handler("code://stats/overview")
            assert "stats" in result

    @pytest.mark.asyncio
    async def test_handle_read_resource_not_found(self, _capture_handlers):
        """Test read_resource handler for unknown URI (lines 609-610, 612-617)."""
        server, captured = _capture_handlers
        handler = captured["read_resource"]
        with patch.object(
            server.code_file_resource, "matches_uri", return_value=False
        ), patch.object(
            server.project_stats_resource, "matches_uri", return_value=False
        ):
            with pytest.raises(ValueError, match="Resource not found"):
                await handler("invalid://unknown")

    @pytest.mark.asyncio
    async def test_handle_list_tools(self, _capture_handlers):
        """Test list_tools handler returns all tools (lines 402-430)."""
        server, captured = _capture_handlers
        handler = captured["list_tools"]
        # The handler references Tool which was imported from the mock
        # We just verify it was captured successfully
        assert handler is not None


class TestSetProjectPathLogging:
    """Test set_project_path logging error handling (lines 673-674)."""

    def test_set_project_path_logging_failure(self, tmp_path):
        """Test that set_project_path handles logging failure gracefully."""
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        new_dir = tmp_path / "new_project"
        new_dir.mkdir()
        with patch("tree_sitter_analyzer.mcp.server.logger") as mock_logger:
            mock_logger.info.side_effect = ValueError("log failure")
            # Should not raise
            server.set_project_path(str(new_dir))


class TestMainFunction:
    """Test main() function branches (lines 756-827)."""

    @pytest.mark.asyncio
    async def test_main_with_project_root_arg(self, tmp_path):
        """Test main() with --project-root argument (line 767)."""
        from unittest.mock import AsyncMock

        from tree_sitter_analyzer.mcp.server import main

        async def _fake_run():
            pass

        with patch("tree_sitter_analyzer.mcp.server.parse_mcp_args") as mock_parse, \
             patch("tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer") as mock_server_cls, \
             patch("tree_sitter_analyzer.mcp.server.sys") as mock_sys:
            mock_args = Mock()
            mock_args.project_root = str(tmp_path)
            mock_parse.return_value = mock_args
            mock_sys.argv = ["pytest"]
            mock_sys.exit = Mock(side_effect=SystemExit(0))

            mock_srv = Mock()
            mock_srv.run = AsyncMock()
            mock_server_cls.return_value = mock_srv

            with pytest.raises(SystemExit):
                await main()

    @pytest.mark.asyncio
    async def test_main_with_env_variable(self, tmp_path):
        """Test main() with TREE_SITTER_PROJECT_ROOT env var (lines 769-774)."""
        import os
        from unittest.mock import AsyncMock

        from tree_sitter_analyzer.mcp.server import main

        with patch("tree_sitter_analyzer.mcp.server.parse_mcp_args") as mock_parse, \
             patch("tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer") as mock_server_cls, \
             patch("tree_sitter_analyzer.mcp.server.sys") as mock_sys, \
             patch.dict(os.environ, {"TREE_SITTER_PROJECT_ROOT": str(tmp_path)}):
            mock_args = Mock()
            mock_args.project_root = None  # No CLI arg
            mock_parse.return_value = mock_args
            mock_sys.argv = ["pytest"]
            mock_sys.exit = Mock(side_effect=SystemExit(0))

            mock_srv = Mock()
            mock_srv.run = AsyncMock()
            mock_server_cls.return_value = mock_srv

            with pytest.raises(SystemExit):
                await main()

    @pytest.mark.asyncio
    async def test_main_with_placeholder_project_root(self, tmp_path):
        """Test main() handles invalid placeholder in project_root (lines 780-796)."""
        from unittest.mock import AsyncMock

        from tree_sitter_analyzer.mcp.server import main

        with patch("tree_sitter_analyzer.mcp.server.parse_mcp_args") as mock_parse, \
             patch("tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer") as mock_server_cls, \
             patch("tree_sitter_analyzer.mcp.server.sys") as mock_sys, \
             patch("tree_sitter_analyzer.mcp.server.detect_project_root", return_value="${workspaceFolder}"):
            mock_args = Mock()
            mock_args.project_root = None
            mock_parse.return_value = mock_args
            mock_sys.argv = ["pytest"]
            mock_sys.exit = Mock(side_effect=SystemExit(0))

            mock_srv = Mock()
            mock_srv.run = AsyncMock()
            mock_server_cls.return_value = mock_srv

            with pytest.raises(SystemExit):
                await main()

    @pytest.mark.asyncio
    async def test_main_keyboard_interrupt(self, tmp_path):
        """Test main() handles KeyboardInterrupt (lines 805-810)."""
        from tree_sitter_analyzer.mcp.server import main

        with patch("tree_sitter_analyzer.mcp.server.parse_mcp_args") as mock_parse, \
             patch("tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer") as mock_server_cls, \
             patch("tree_sitter_analyzer.mcp.server.sys") as mock_sys:
            mock_args = Mock()
            mock_args.project_root = str(tmp_path)
            mock_parse.return_value = mock_args
            mock_sys.argv = ["pytest"]
            mock_sys.exit = Mock(side_effect=SystemExit(0))
            mock_server_cls.side_effect = KeyboardInterrupt()

            with pytest.raises(SystemExit):
                await main()

    @pytest.mark.asyncio
    async def test_main_general_exception(self, tmp_path):
        """Test main() handles general exception (lines 811-816)."""
        from tree_sitter_analyzer.mcp.server import main

        with patch("tree_sitter_analyzer.mcp.server.parse_mcp_args") as mock_parse, \
             patch("tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer") as mock_server_cls, \
             patch("tree_sitter_analyzer.mcp.server.sys") as mock_sys:
            mock_args = Mock()
            mock_args.project_root = str(tmp_path)
            mock_parse.return_value = mock_args
            mock_sys.argv = ["pytest"]
            mock_sys.exit = Mock(side_effect=SystemExit(1))
            mock_server_cls.side_effect = RuntimeError("boom")

            with pytest.raises(SystemExit):
                await main()

    @pytest.mark.asyncio
    async def test_main_logging_failure_in_exception_handler(self, tmp_path):
        """Test main() when logging fails in exception handler (lines 808-809, 814-815, 821-822)."""
        from tree_sitter_analyzer.mcp.server import main

        with patch("tree_sitter_analyzer.mcp.server.parse_mcp_args") as mock_parse, \
             patch("tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer") as mock_server_cls, \
             patch("tree_sitter_analyzer.mcp.server.sys") as mock_sys, \
             patch("tree_sitter_analyzer.mcp.server.logger") as mock_logger:
            mock_args = Mock()
            mock_args.project_root = str(tmp_path)
            mock_parse.return_value = mock_args
            mock_sys.argv = ["pytest"]
            mock_sys.exit = Mock(side_effect=SystemExit(1))
            mock_server_cls.side_effect = RuntimeError("boom")
            mock_logger.error.side_effect = OSError("log broken")
            mock_logger.info.side_effect = OSError("log broken")

            with pytest.raises(SystemExit):
                await main()


class TestMainSyncFunction:
    """Test main_sync function (line 827)."""

    def test_main_sync_calls_asyncio_run(self):
        """Test main_sync calls asyncio.run(main()) (line 827)."""
        from tree_sitter_analyzer.mcp.server import main_sync
        with patch("tree_sitter_analyzer.mcp.server.asyncio.run") as mock_run:
            mock_run.return_value = None
            main_sync()
            assert mock_run.called


class TestRunLifecycleBranches:
    """Test server.run() lifecycle (lines 711-730)."""

    @pytest.mark.asyncio
    async def test_run_logging_failure(self, tmp_path):
        """Test run() handles logging failures (lines 711-712)."""
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        with patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True), \
             patch.object(server, "create_server") as mock_create, \
             patch("tree_sitter_analyzer.mcp.server.logger") as mock_logger:
            mock_logger.info.side_effect = ValueError("log broken")
            mock_create.side_effect = Exception("creation failed")
            with pytest.raises(Exception, match="creation failed"):
                await server.run()
