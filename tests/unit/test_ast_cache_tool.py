"""Unit tests for mcp/tools/ast_cache_tool — MCP tool for AST cache operations."""

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool


class TestASTCacheToolInit:
    """Tests for ASTCacheTool initialization."""

    def test_default_init(self):
        tool = ASTCacheTool()
        assert not tool.cache_initialized

    def test_init_with_project_root(self):
        tool = ASTCacheTool(project_root="/tmp/project")
        assert tool.project_root == "/tmp/project"

    def test_set_project_path_resets_cache(self, tmp_path):
        tool = ASTCacheTool(project_root=str(tmp_path))
        tool._cache = MagicMock()  # noqa: SLF001 — test setup write
        tool.set_project_path(str(tmp_path / "sub"))
        assert not tool.cache_initialized


class TestGetCache:
    """Tests for get_cache lazy initialization."""

    def test_raises_without_project_root(self):
        tool = ASTCacheTool()
        with pytest.raises(ValueError, match="Project root not set"):
            tool.get_cache()

    def test_creates_cache_with_project_root(self, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache

        tool = ASTCacheTool(project_root=str(tmp_path))
        cache = tool.get_cache()
        assert cache is not None
        assert isinstance(cache, ASTCache)

    def test_reuses_existing_cache(self, tmp_path):
        tool = ASTCacheTool(project_root=str(tmp_path))
        cache1 = tool.get_cache()
        cache2 = tool.get_cache()
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

    def test_mode_is_optional_in_schema(self):
        # Wave 1b (audit index-10): mode is resolved at runtime (search when a
        # query is supplied, else stats), so it must NOT be required — else a
        # strict MCP client rejects a valid {query: X} call before dispatch.
        tool = ASTCacheTool()
        schema = tool.get_tool_schema()
        assert "mode" in schema["properties"]
        assert "mode" not in schema.get("required", [])

    def test_resolve_mode_defaults_to_search_with_query(self):
        # index-10: cache query=X with no mode searches instead of silently
        # returning stats and dropping the query.
        assert ASTCacheTool._resolve_mode({"query": "Foo"}) == "search"
        assert ASTCacheTool._resolve_mode({}) == "stats"
        assert ASTCacheTool._resolve_mode({"mode": "stats", "query": "Foo"}) == "stats"

    def test_symbol_declared_in_schema(self):
        # #575: symbol (the facade's canonical id) must be a declared param so
        # the facade whitelist forwards it instead of stripping it → stats.
        assert "symbol" in ASTCacheTool().get_tool_schema()["properties"]

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


class TestSymbolAliasesQuery:
    """#575: `cache symbol=X` must search for the symbol, not silently fall back
    to stats (the facade stripped symbol → no query → mode=stats → wrong answer)."""

    def test_symbol_aliases_query_into_search_mode(self, tmp_path):
        import asyncio

        (tmp_path / "m.py").write_text(
            "class Widget:\n    def go(self):\n        pass\n"
        )
        tool = ASTCacheTool(project_root=str(tmp_path))
        asyncio.run(tool.execute({"mode": "index"}))  # build the cache
        result = asyncio.run(tool.execute({"symbol": "Widget"}))
        assert result["mode"] == "search"
        assert result["query"] == "Widget"

    def test_explicit_query_wins_over_symbol(self, tmp_path):
        import asyncio

        (tmp_path / "m.py").write_text("class Widget:\n    pass\n")
        tool = ASTCacheTool(project_root=str(tmp_path))
        asyncio.run(tool.execute({"mode": "index"}))
        result = asyncio.run(tool.execute({"symbol": "Widget", "query": "other"}))
        assert result["query"] == "other"


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
        tool._cache = mock_cache  # noqa: SLF001 — test setup write
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
        # G2: when fts5_available=True and query >= 2 chars, the ranked path
        # is used — stub fts_search_ranked as well.
        mock_cache.fts_search.return_value = [{"name": "MyClass"}]
        mock_cache.fts_search_ranked.return_value = [{"name": "MyClass"}]
        mock_cache.search_symbols.return_value = [{"name": "MyClass"}]
        mock_cache.fts5_available = True
        result = await tool.execute({"mode": "search", "query": "MyClass"})
        assert result["count"] == 1
        assert result["query"] == "MyClass"

    @pytest.mark.asyncio
    async def test_empty_search_with_fts5_says_no_match_not_populate(
        self, tool_with_mock_cache
    ):
        """Wave 1b (audit index-05): an empty result while FTS5 is available is a
        genuine no-match — guide to broaden, NOT 'populate the FTS index'."""
        tool, mock_cache = tool_with_mock_cache
        mock_cache.fts_search.return_value = []
        mock_cache.fts_search_ranked.return_value = []
        mock_cache.fts5_available = True
        result = await tool.execute({"mode": "search", "query": "zzznomatch"})
        assert result["count"] == 0
        ns = result["agent_summary"]["next_step"]
        assert "No symbols match" in ns
        assert "populate" not in ns.lower()

    @pytest.mark.asyncio
    async def test_empty_search_without_fts5_says_rebuild(self, tool_with_mock_cache):
        """index-05: when FTS5 is unavailable, the rebuild hint is correct."""
        tool, mock_cache = tool_with_mock_cache
        mock_cache.fts_search.return_value = []
        mock_cache.fts_search_ranked.return_value = []
        mock_cache.fts5_available = False
        result = await tool.execute({"mode": "search", "query": "zzznomatch"})
        assert result["count"] == 0
        assert "FTS5 unavailable" in result["agent_summary"]["next_step"]

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
        mock_cache.index_project.return_value = {"indexed": 50}
        # DF-9: verify get_stats is called to retrieve total symbol count
        mock_cache.get_stats.return_value = {"total_symbols": 100, "total_files": 50}
        result = await tool.execute({"mode": "index", "max_files": 100, "force": True})
        assert result["success"] is True
        mock_cache.index_project.assert_called_once_with(
            max_files=100,
            force=True,
            include_activation=False,
            language_filter=None,
        )
        # DF-9: verify summary includes the symbol count
        assert "symbols=100" in result["summary_line"]

    @pytest.mark.asyncio
    async def test_index_project_threads_language_filter(self, tool_with_mock_cache):
        """#1018: --ast-cache-language / language arg reaches index_project."""
        tool, mock_cache = tool_with_mock_cache
        mock_cache.index_project.return_value = {"indexed": 1}
        mock_cache.get_stats.return_value = {"total_symbols": 1, "total_files": 1}
        result = await tool.execute(
            {"mode": "index", "max_files": 100, "language": "python"}
        )
        assert result["success"] is True
        mock_cache.index_project.assert_called_once_with(
            max_files=100,
            force=False,
            include_activation=False,
            language_filter="python",
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
            language_filter=None,
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


class TestAstCacheSearchTruncated:
    """#737: ast_cache mode=search must report truncated=True when results hit the limit."""

    @pytest.mark.asyncio
    async def test_search_not_truncated_when_below_limit(self, tmp_path):
        tool = ASTCacheTool(str(tmp_path))
        mock_cache = MagicMock()
        mock_cache.fts_search_ranked.return_value = [{"name": "foo"}]
        mock_cache.fts5_available = True
        mock_cache.project_root = str(tmp_path)
        with patch.object(tool, "_get_cache", return_value=mock_cache):
            result = await tool.execute({"mode": "search", "query": "foo", "limit": 10})
        assert result["count"] == 1
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_search_truncated_when_results_equal_limit(self, tmp_path):
        tool = ASTCacheTool(str(tmp_path))
        mock_cache = MagicMock()
        mock_cache.fts_search_ranked.return_value = [
            {"name": f"sym{i}"} for i in range(5)
        ]
        mock_cache.fts5_available = True
        mock_cache.project_root = str(tmp_path)
        with patch.object(tool, "_get_cache", return_value=mock_cache):
            result = await tool.execute({"mode": "search", "query": "sym", "limit": 5})
        assert result["count"] == 5
        assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_search_truncated_measured_before_split_expansion(self, tmp_path):
        """#737: truncated is measured on raw_results BEFORE _apply_legacy_import_split.

        A single raw row whose name is 'a,b' expands to 2 after split.
        If truncated were measured after split, count==2 with limit==2 would
        falsely report truncated=True — but the DB only returned 1 row.
        """
        tool = ASTCacheTool(str(tmp_path))
        mock_cache = MagicMock()
        # 1 raw row that will be split into 2 by _apply_legacy_import_split
        mock_cache.fts_search.return_value = [{"name": "a, b", "type": "import"}]
        mock_cache.fts_search_ranked.return_value = [{"name": "a, b", "type": "import"}]
        mock_cache.fts5_available = True
        mock_cache.project_root = str(tmp_path)
        with patch.object(tool, "_get_cache", return_value=mock_cache):
            # limit=2 — raw_results has 1 row < 2, so truncated must be False
            result = await tool.execute({"mode": "search", "query": "a", "limit": 2})
        assert result["truncated"] is False
