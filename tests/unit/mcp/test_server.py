#!/usr/bin/env python3
"""
Unit tests for MCP Server module.

Tests MCP server implementation for tree-sitter analyzer.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer, parse_mcp_args


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
        with pytest.raises(ValueError, match="Resource not found"):
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
