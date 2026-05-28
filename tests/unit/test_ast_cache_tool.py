"""Unit tests for mcp/tools/ast_cache_tool — MCP tool for AST cache operations."""

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool


class TestASTCacheToolInit:
    """Tests for ASTCacheTool initialization."""

    def test_default_init(self):
        tool = ASTCacheTool()
        assert tool._cache is None

    def test_init_with_project_root(self):
        tool = ASTCacheTool(project_root="/tmp/project")
        assert tool.project_root == "/tmp/project"

    def test_set_project_path_resets_cache(self, tmp_path):
        tool = ASTCacheTool(project_root=str(tmp_path))
        tool._cache = MagicMock()
        tool.set_project_path(str(tmp_path / "sub"))
        assert tool._cache is None


class TestGetCache:
    """Tests for _get_cache lazy initialization."""

    def test_raises_without_project_root(self):
        tool = ASTCacheTool()
        with pytest.raises(ValueError, match="Project root not set"):
            tool._get_cache()

    def test_creates_cache_with_project_root(self, tmp_path):
        tool = ASTCacheTool(project_root=str(tmp_path))
        cache = tool._get_cache()
        assert cache is not None

    def test_reuses_existing_cache(self, tmp_path):
        tool = ASTCacheTool(project_root=str(tmp_path))
        cache1 = tool._get_cache()
        cache2 = tool._get_cache()
        assert cache1 is cache2


class TestGetToolDefinition:
    """Tests for get_tool_definition."""

    def test_definition_shape(self):
        tool = ASTCacheTool()
        defn = tool.get_tool_definition()
        assert defn["name"] == "ast_cache"
        assert "inputSchema" in defn
        assert "index" in defn["description"]
        assert "modes" in defn["description"].lower() or "Modes" in defn["description"]


class TestGetToolSchema:
    """Tests for get_tool_schema."""

    def test_schema_has_required_mode(self):
        tool = ASTCacheTool()
        schema = tool.get_tool_schema()
        assert "mode" in schema["properties"]
        assert "mode" in schema["required"]

    def test_valid_modes(self):
        tool = ASTCacheTool()
        schema = tool.get_tool_schema()
        modes = schema["properties"]["mode"]["enum"]
        # ``changes`` and ``sync`` were added post-consolidation for the
        # incremental-sync workflow. ``fts_search`` was collapsed into
        # ``search`` (J1) — it remains accepted at the validate boundary
        # for back-compat but is no longer advertised in the schema enum.
        # ``watch_start`` / ``watch_stop`` / ``watch_status`` were wired
        # into the tool by the 2026-05-24 PL-A pass (FileWatcherDaemon
        # backing).
        assert set(modes) == {
            "index",
            "lookup",
            "search",
            "sync",
            "changes",
            "stats",
            "invalidate",
            "watch_start",
            "watch_stop",
            "watch_status",
        }


class TestValidateArguments:
    """Tests for validate_arguments."""

    def test_valid_stats_mode(self):
        tool = ASTCacheTool()
        assert tool.validate_arguments({"mode": "stats"}) is True

    def test_invalid_mode(self):
        tool = ASTCacheTool()
        with pytest.raises(ValueError, match="Invalid mode"):
            tool.validate_arguments({"mode": "destroy"})

    def test_lookup_requires_file_path(self):
        tool = ASTCacheTool()
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"mode": "lookup"})

    def test_invalidate_requires_file_path(self):
        tool = ASTCacheTool()
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"mode": "invalidate"})

    def test_search_requires_query(self):
        tool = ASTCacheTool()
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments({"mode": "search"})

    def test_fts_search_requires_query(self):
        tool = ASTCacheTool()
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments({"mode": "fts_search"})

    def test_valid_lookup_with_file_path(self):
        tool = ASTCacheTool()
        assert (
            tool.validate_arguments({"mode": "lookup", "file_path": "test.py"}) is True
        )

    def test_valid_search_with_query(self):
        tool = ASTCacheTool()
        assert tool.validate_arguments({"mode": "search", "query": "MyClass"}) is True


class TestExecute:
    """Tests for execute method — uses mocked cache."""

    @pytest.fixture
    def tool_with_mock_cache(self, tmp_path):
        tool = ASTCacheTool(project_root=str(tmp_path))
        mock_cache = MagicMock()
        tool._cache = mock_cache
        return tool, mock_cache

    @pytest.mark.asyncio
    async def test_stats_mode(self, tool_with_mock_cache):
        tool, mock_cache = tool_with_mock_cache
        mock_cache.get_stats.return_value = {"files_indexed": 10, "symbols": 50}
        result = await tool.execute({"mode": "stats"})
        assert result["success"] is True
        assert result["mode"] == "stats"
        assert result["files_indexed"] == 10

    @pytest.mark.asyncio
    async def test_lookup_found(self, tool_with_mock_cache):
        tool, mock_cache = tool_with_mock_cache
        mock_cache.lookup.return_value = {"symbols": [{"name": "foo"}]}
        with patch.object(
            tool, "resolve_and_validate_file_path", return_value="/abs/test.py"
        ):
            result = await tool.execute({"mode": "lookup", "file_path": "test.py"})
        assert result["success"] is True
        assert result["mode"] == "lookup"

    @pytest.mark.asyncio
    async def test_lookup_not_found(self, tool_with_mock_cache):
        tool, mock_cache = tool_with_mock_cache
        mock_cache.lookup.return_value = None
        with patch.object(
            tool, "resolve_and_validate_file_path", return_value="/abs/test.py"
        ):
            result = await tool.execute({"mode": "lookup", "file_path": "test.py"})
        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_search_mode(self, tool_with_mock_cache):
        tool, mock_cache = tool_with_mock_cache
        # J1: ``search`` is now backed by ``fts_search`` (which delegates
        # to a LIKE scan when FTS5 is unavailable). Stub both so the test
        # works regardless of the runtime implementation.
        mock_cache.fts_search.return_value = [{"name": "MyClass"}]
        mock_cache.search_symbols.return_value = [{"name": "MyClass"}]
        mock_cache.fts5_available = True
        result = await tool.execute({"mode": "search", "query": "MyClass"})
        assert result["count"] == 1
        assert result["query"] == "MyClass"

    @pytest.mark.asyncio
    async def test_fts_search_mode(self, tool_with_mock_cache):
        tool, mock_cache = tool_with_mock_cache
        mock_cache.fts_search.return_value = [{"name": "MyClass", "rank": -1.0}]
        mock_cache.fts5_available = True
        result = await tool.execute(
            {"mode": "fts_search", "query": "MyClass", "limit": 10}
        )
        assert result["count"] == 1
        # J1: ``fts_search`` is now a deprecated alias — the response
        # should surface that fact so callers can migrate.
        assert "deprecated_alias" in result

    @pytest.mark.asyncio
    async def test_index_single_file(self, tool_with_mock_cache):
        tool, mock_cache = tool_with_mock_cache
        mock_cache.index_file.return_value = {"indexed": True}
        with patch.object(
            tool, "resolve_and_validate_file_path", return_value="/abs/test.py"
        ):
            result = await tool.execute({"mode": "index", "file_path": "test.py"})
        assert result["success"] is True
        mock_cache.index_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_index_project(self, tool_with_mock_cache):
        tool, mock_cache = tool_with_mock_cache
        mock_cache.index_project.return_value = {"files_indexed": 50}
        result = await tool.execute({"mode": "index", "max_files": 100, "force": True})
        assert result["success"] is True
        mock_cache.index_project.assert_called_once_with(
            max_files=100,
            force=True,
            include_activation=False,
        )

    @pytest.mark.asyncio
    async def test_index_project_can_include_activation(self, tool_with_mock_cache):
        tool, mock_cache = tool_with_mock_cache
        mock_cache.index_project.return_value = {"files_indexed": 50}
        result = await tool.execute(
            {
                "mode": "index",
                "max_files": 100,
                "include_activation": True,
            }
        )
        assert result["success"] is True
        mock_cache.index_project.assert_called_once_with(
            max_files=100,
            force=False,
            include_activation=True,
        )

    @pytest.mark.asyncio
    async def test_invalidate_mode(self, tool_with_mock_cache):
        tool, mock_cache = tool_with_mock_cache
        mock_cache.invalidate.return_value = True
        with patch.object(
            tool, "resolve_and_validate_file_path", return_value="/abs/test.py"
        ):
            result = await tool.execute({"mode": "invalidate", "file_path": "test.py"})
        assert result["invalidated"] is True
