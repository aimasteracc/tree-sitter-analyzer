#!/usr/bin/env python3
"""Tests for codegraph_symbol_search MCP tool — FTS5-powered instant symbol lookup."""

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.symbol_search_tool import CodeGraphSymbolSearchTool


@pytest.fixture
def indexed_project(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()

    (project / "app.py").write_text(
        "class UserService:\n"
        "    def get_user(self, user_id):\n"
        "        return self._find_user(user_id)\n"
        "\n"
        "    def _find_user(self, user_id):\n"
        "        pass\n"
        "\n"
        "def handle_request(request):\n"
        "    svc = UserService()\n"
        "    return svc.get_user(1)\n"
    )

    (project / "utils.py").write_text(
        "def format_user(user):\n"
        "    return str(user)\n"
        "\n"
        "def validate_input(data):\n"
        "    return bool(data)\n"
    )

    cache = ASTCache(str(project))
    cache.index_project(max_files=100)
    cache.close()
    return project


class TestCodeGraphSymbolSearchToolDefinition:
    def test_tool_name(self):
        tool = CodeGraphSymbolSearchTool()
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_symbol_search"

    def test_schema_requires_query(self):
        tool = CodeGraphSymbolSearchTool()
        schema = tool.get_tool_schema()
        assert "query" in schema["properties"]
        assert "query" in schema["required"]

    def test_schema_has_kind_filter(self):
        tool = CodeGraphSymbolSearchTool()
        schema = tool.get_tool_schema()
        kind_prop = schema["properties"]["kind"]
        assert "function" in kind_prop["enum"]
        assert "class" in kind_prop["enum"]


class TestCodeGraphSymbolSearchValidation:
    def test_validate_requires_query(self):
        tool = CodeGraphSymbolSearchTool()
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments({})

    def test_validate_passes_with_query(self):
        tool = CodeGraphSymbolSearchTool()
        assert tool.validate_arguments({"query": "UserService"}) is True


@pytest.mark.asyncio
class TestCodeGraphSymbolSearchExecution:
    async def test_exact_match(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "UserService", "output_format": "json"})
        assert result["success"] is True
        assert result["match_count"] >= 1
        names = [r["name"] for r in result["results"]]
        assert "UserService" in names

    async def test_exposes_canonical_count_key(self, indexed_project):
        # Wave 1b (audit search-06): symbol search must also expose the stable
        # canonical `count` key (already emitted by search action=content) so an
        # agent can read the result count consistently across both actions.
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "UserService", "output_format": "json"})
        assert result["count"] == result["match_count"]

    async def test_fuzzy_match(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "~user", "output_format": "json"})
        assert result["success"] is True
        assert result["match_count"] >= 1

    async def test_wildcard_match(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "handle_*", "output_format": "json"})
        assert result["success"] is True
        names = [r["name"] for r in result["results"]]
        assert "handle_request" in names

    async def test_language_filter(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute(
            {"query": "UserService", "language": "python", "output_format": "json"}
        )
        assert result["success"] is True
        assert result.get("language_filter") == "python"

    async def test_kind_filter_function(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute(
            {"query": "~user", "kind": "function", "output_format": "json"}
        )
        assert result["success"] is True
        for r in result["results"]:
            assert r["kind"] == "function"

    async def test_kind_filter_class(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute(
            {"query": "UserService", "kind": "class", "output_format": "json"}
        )
        assert result["success"] is True
        for r in result["results"]:
            assert r["kind"] == "class"

    async def test_limit(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "~", "limit": 1, "output_format": "json"})
        assert result["success"] is True
        assert result["match_count"] <= 1

    async def test_no_match(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute(
            {"query": "NonExistentSymbol", "output_format": "json"}
        )
        assert result["success"] is True
        assert result["match_count"] == 0

    async def test_result_has_file_and_line(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "UserService", "output_format": "json"})
        assert result["match_count"] >= 1
        hit = result["results"][0]
        assert "file" in hit
        assert "line" in hit
        assert "code" in hit
        assert hit["line"] > 0

    async def test_next_step_points_to_bulk_explore(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "UserService", "output_format": "json"})
        assert "codegraph_explore" in result["next_step"]

    async def test_top_match_inlines_source_body(self, indexed_project):
        """P2: top matches carry an inlined verbatim source body (no Read)."""
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "get_user", "output_format": "json"})
        assert result["match_count"] >= 1
        hit = next(r for r in result["results"] if r["name"] == "get_user")
        assert "body" in hit, "top match must carry inlined body"
        assert "content" in hit["body"]
        assert "def get_user" in hit["body"]["content"]
        assert "_find_user" in hit["body"]["content"]

    async def test_search_deterrent_next_step(self, indexed_project):
        """P2: a deterrent tells the agent to answer from inlined bodies."""
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "get_user", "output_format": "json"})
        assert "no Read needed" in result["next_step"]

    async def test_search_body_survives_toon(self, indexed_project):
        """P2: inlined body survives TOON serialization (MCP default)."""
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "get_user", "output_format": "toon"})
        assert result.get("format") == "toon"
        assert "def get_user" in result["toon_content"]

    async def test_toon_output_format(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "UserService", "output_format": "toon"})
        assert result["success"] is True
        assert "toon_content" in result

    async def test_data_source_field(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "UserService", "output_format": "json"})
        assert "data_source" in result
        assert result["data_source"] in ("fts5", "linear_scan")

    async def test_relevance_score_on_fts5_results(self, indexed_project):
        """BM25 FTS5 results carry relevance_score in [0, 1] — README 'ahead' claim."""
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "format_user", "output_format": "json"})
        assert result["success"] is True
        assert result["match_count"] >= 1, "fixture must have a format_user symbol"
        # Indexed project always has FTS5 via ASTCache.index_project
        assert result["data_source"] == "fts5", (
            f"expected fts5 data source, got {result['data_source']}"
        )
        for hit in result["results"]:
            assert "relevance_score" in hit, (
                "FTS5 results must carry relevance_score (README 'ahead' claim)"
            )
            score = hit["relevance_score"]
            assert 0.0 <= score <= 1.0, f"score out of range: {score}"

    async def test_plain_query_cascade_fuzzy_finds_typo(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute(
            {"query": "HandlerRequest", "output_format": "json"}
        )

        assert result["success"] is True
        names = [r["name"] for r in result["results"]]
        assert "handle_request" in names
        fuzzy_hits = [r for r in result["results"] if r["name"] == "handle_request"]
        assert fuzzy_hits[0]["match_tier"] == "fuzzy"

    async def test_fts5_results_sorted_by_relevance_descending(self, indexed_project):
        """FTS5 results are ordered best-match first, not by file path."""
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute(
            {"query": "user", "limit": 10, "output_format": "json"}
        )
        assert result["success"] is True
        assert result["data_source"] == "fts5", (
            f"expected fts5 data source, got {result['data_source']}"
        )
        if result["match_count"] >= 2:
            scores = [
                r["relevance_score"]
                for r in result["results"]
                if "relevance_score" in r
            ]
            assert scores == sorted(scores, reverse=True), (
                "FTS5 results must be sorted by relevance_score descending"
            )

    async def test_definition_ranks_first_imports_folded(self):
        """Issue #443: definitions rank first, duplicate imports folded to one.

        A symbol with 1 definition + N imports should return:
        - First result: the definition (kind != import)
        - Second result: folded imports (kind=import, import_count==N)
        """
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            # 1 real definition
            (project / "core.py").write_text(
                "def apply_toon_format(data):\n    return data\n"
            )

            # 7 files that import the same function
            for i in range(7):
                (project / f"importer_{i}.py").write_text(
                    f"from core import apply_toon_format\n"
                    f"\n"
                    f"def use_it_{i}():\n"
                    f"    return apply_toon_format('test')\n"
                )

            cache = ASTCache(str(project))
            cache.index_project(max_files=100)
            cache.close()

            tool = CodeGraphSymbolSearchTool(str(project))
            # Windows: the tool's lazy ASTCache holds index.db open —
            # TemporaryDirectory cleanup needs it closed (WinError 32).
            try:
                result = await tool.execute(
                    {"query": "apply_toon_format", "output_format": "json"}
                )

                assert result["success"] is True
                results = result["results"]

                # Should have exactly 2 entries: 1 definition + 1 folded import
                assert len(results) == 2, (
                    f"Expected 2 results (1 def + 1 folded import), "
                    f"got {len(results)}: {[r['name'] for r in results]}"
                )

                # First result is the definition
                definition = results[0]
                assert definition["kind"] == "function", (
                    f"First result should be function definition, got {definition['kind']}"
                )
                assert definition["file"].endswith("core.py"), (
                    f"Definition should be in core.py, got {definition['file']}"
                )
                assert definition.get("import_count") is None, (
                    "Definition should not have import_count"
                )

                # Second result is folded imports
                import_entry = results[1]
                assert import_entry["kind"] == "import", (
                    f"Second result should be import kind, got {import_entry['kind']}"
                )
                assert import_entry.get("import_count") == 7, (
                    f"Import entry should have import_count==7, got {import_entry.get('import_count')}"
                )
                assert len(import_entry.get("import_files", [])) == 7, (
                    f"Folded import should track all 7 importing files, "
                    f"got {len(import_entry.get('import_files', []))}"
                )
                # Codex P2: file_count must include every folded import file
                # (7 importers + 1 definition file = 8).
                assert result["file_count"] == 8
            finally:
                if tool._cache is not None:
                    tool._cache.close()


@pytest.mark.asyncio
class TestCodeGraphSymbolSearchNoCache:
    async def test_search_on_empty_project(self, tmp_path):
        project = tmp_path / "empty_proj"
        project.mkdir()
        tool = CodeGraphSymbolSearchTool(str(project))
        result = await tool.execute({"query": "anything", "output_format": "json"})
        assert result["success"] is True
        assert result["match_count"] == 0


class TestCodeGraphSymbolSearchSourceContext:
    def test_exact_search_uses_linear_fallback_without_fts5(self):
        class LinearOnlyCache:
            fts5_available = False

            def search_symbols(self, query, language=None):
                assert query == "UserService"
                assert language == "python"
                return [
                    {
                        "name": "UserService",
                        "kind": "class",
                        "file": "app.py",
                        "language": "python",
                        "line": 1,
                    },
                    {
                        "name": "user_service",
                        "kind": "variable",
                        "file": "app.py",
                        "language": "python",
                        "line": 2,
                    },
                ]

        tool = CodeGraphSymbolSearchTool()

        results = tool._exact_search(
            LinearOnlyCache(),
            "UserService",
            language="python",
            kind="class",
            limit=5,
        )

        assert [result["name"] for result in results] == ["UserService"]

    def test_fts_to_results_keeps_optional_metadata_optional(self):
        tool = CodeGraphSymbolSearchTool()

        results = tool._fts_to_results(
            [
                {
                    "name": "plain",
                    "kind": "function",
                    "file": "app.py",
                    "language": "python",
                    "line": 1,
                    "end_line": 3,
                },
                {
                    "name": "tiered",
                    "kind": "function",
                    "file": "app.py",
                    "language": "python",
                    "line": 5,
                    "end_line": 8,
                    "match_tier": "fts5",
                    "relevance_score": 0.7,
                },
            ],
            kind="any",
            limit=5,
        )

        assert "match_tier" not in results[0]
        assert results[1]["match_tier"] == "fts5"
        assert results[1]["relevance_score"] == 0.7

    def test_add_source_context_skips_invalid_line_numbers(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        results = [{"file": "app.py", "line": 0}]

        tool._add_source_context(results)

        assert "code" not in results[0]

    def test_read_line_requires_project_root_and_file_path(self):
        tool = CodeGraphSymbolSearchTool()

        assert tool._read_line("app.py", 1) == ""

    def test_read_line_degrades_for_missing_or_short_files(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))

        assert tool._read_line("missing.py", 1) == ""
        assert tool._read_line("app.py", 999) == ""


class TestCodeGraphSymbolSearchRegistration:
    """Wave C2: these capabilities are now facade actions, not top-level tools.
    symbol_search → search.symbol; callers/callees → nav.callers/callees
    (bespoke, scope-discriminated)."""

    def test_tool_registered_in_server(self):
        from tree_sitter_analyzer.mcp.server import _create_tool_registry

        _, tools = _create_tool_registry(None)
        assert "search" in tools
        assert "symbol" in tools["search"].action_map
        assert (
            type(tools["search"].action_map["symbol"]).__name__
            == "CodeGraphSymbolSearchTool"
        )

    def test_callers_registered_in_server(self):
        from tree_sitter_analyzer.mcp.server import _create_tool_registry

        _, tools = _create_tool_registry(None)
        assert "callers" in tools["nav"].bespoke_map

    def test_callees_registered_in_server(self):
        from tree_sitter_analyzer.mcp.server import _create_tool_registry

        _, tools = _create_tool_registry(None)
        assert "callees" in tools["nav"].bespoke_map


# ---------------------------------------------------------------------------
# Issue #540 — Leg 2: positive-int validation for limit
# ---------------------------------------------------------------------------


class TestSymbolSearchLimitValidation:
    """validate_arguments must reject limit <= 0."""

    def test_negative_limit_raises(self):
        tool = CodeGraphSymbolSearchTool()
        with pytest.raises(ValueError, match="limit"):
            tool.validate_arguments({"query": "foo", "limit": -5})

    def test_zero_limit_raises(self):
        tool = CodeGraphSymbolSearchTool()
        with pytest.raises(ValueError, match="limit"):
            tool.validate_arguments({"query": "foo", "limit": 0})

    def test_positive_limit_passes(self):
        tool = CodeGraphSymbolSearchTool()
        # Must not raise
        tool.validate_arguments({"query": "foo", "limit": 1})
