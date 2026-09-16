"""Tests for codegraph_symbol_search MCP tool — FTS5-powered instant symbol lookup."""

import os
from pathlib import Path
from typing import Any

import pytest

from tests.unit._navigation_test_support import (
    INDEXED_SOURCE as _INDEXED_SOURCE,
)
from tests.unit._navigation_test_support import (
    MOVED_SOURCE as _MOVED_SOURCE,
)
from tests.unit._navigation_test_support import (
    FTSAndLinearCache,
    build_indexed_project,
)
from tests.unit._navigation_test_support import (
    assert_no_mixed_source as _assert_no_mixed_source,
)
from tests.unit._navigation_test_support import (
    published_search as _published_search,
)
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.symbol_search_tool import CodeGraphSymbolSearchTool


@pytest.fixture
def indexed_project(tmp_path):
    return build_indexed_project(tmp_path)


class TestCodeGraphSymbolSearchToolDefinition:
    def test_tool_name(self):
        tool = CodeGraphSymbolSearchTool()
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_symbol_search"

    @pytest.mark.parametrize(
        ("section", "key", "value"),
        [
            ("properties", "query", None),
            ("required", "query", None),
            ("properties", "kind", "function"),
            ("properties", "kind", "class"),
        ],
    )
    def test_schema_contract(self, section, key, value):
        section_value = CodeGraphSymbolSearchTool().get_tool_schema()[section]
        assert key in section_value
        if value is not None:
            assert value in section_value[key]["enum"]


class TestCodeGraphSymbolSearchValidation:
    @pytest.mark.parametrize("arguments", [{}, {"query": "UserService"}])
    def test_validate_query(self, arguments):
        if arguments:
            assert CodeGraphSymbolSearchTool().validate_arguments(arguments) is True
        else:
            with pytest.raises(ValueError, match="query is required"):
                CodeGraphSymbolSearchTool().validate_arguments(arguments)


@pytest.mark.asyncio
class TestCodeGraphSymbolSearchExecution:
    async def test_operational_index_update_and_query_without_snapshot_manifest(
        self, tmp_path
    ):
        # PR #1350/#1352：v17 操作平面仍不依赖快照认证；这不是 Windows 原生模拟验收。
        from tree_sitter_analyzer.cache.schema_extensions import CURRENT_SCHEMA_VERSION
        from tree_sitter_analyzer.incremental_sync import IncrementalSync

        source = tmp_path / "app.py"
        source.write_text("def original(): return 1\n", encoding="utf-8")
        cache = ASTCache(str(tmp_path))
        tool = CodeGraphSymbolSearchTool(str(tmp_path))
        try:
            assert cache.index_file(str(source))["status"] == "indexed"
            conn = cache.get_conn()
            assert (
                conn.execute("SELECT MAX(version) FROM ast_schema_version").fetchone()[
                    0
                ]
                == CURRENT_SCHEMA_VERSION
                == 17
            )
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM ast_index_snapshot_manifest"
                ).fetchone()[0]
                == 0
            )
            first = await tool.execute({"query": "original", "output_format": "json"})
            assert (first["success"], [row["name"] for row in first["results"]]) == (
                True,
                ["original"],
            )
            source.write_text("def replacement(): return 22\n", encoding="utf-8")
            sync = IncrementalSync(cache).sync(certify_manifest=False)
            assert (sync.updated_files, sync.errors) == (1, 0)
            second = await tool.execute(
                {"query": "replacement", "output_format": "json"}
            )
            assert (second["success"], [row["name"] for row in second["results"]]) == (
                True,
                ["replacement"],
            )
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM ast_index_snapshot_manifest"
                ).fetchone()[0]
                == 0
            )
        finally:
            cache.close()
            if tool._cache is not None:
                tool._cache.close()

    async def test_exact_match(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "UserService", "output_format": "json"})
        assert result["success"] is True
        assert result["match_count"] == 1
        names = [r["name"] for r in result["results"]]
        assert "UserService" in names

    async def test_exposes_canonical_count_key(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "UserService", "output_format": "json"})
        assert result["count"] == result["match_count"]

    async def test_fuzzy_match(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "~user", "output_format": "json"})
        assert result["success"] is True
        assert result["match_count"] == 4

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
        assert result["match_count"] == 1
        hit = result["results"][0]
        assert "file" in hit
        assert "line" in hit
        assert "code" not in hit
        assert hit["line"] == 1

    async def test_next_step_points_to_bulk_explore(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "UserService", "output_format": "json"})
        assert "structure action=explore" in result["next_step"]

    async def test_top_match_inlines_source_body(self, tmp_path):
        _source, facade, symbol = await _published_search(tmp_path)
        result = await facade.execute(
            {"action": "symbol", "query": "target", "output_format": "json"}
        )
        assert result["match_count"] == 1
        hit = next(r for r in result["results"] if r["name"] == "target")
        assert "body" in hit, "top match must carry inlined body"
        assert "content" in hit["body"]
        assert "def target" in hit["body"]["content"]
        assert "INDEXED_MARKER" in hit["body"]["content"]
        symbol._cache.close()

    async def test_public_search_does_not_mix_old_coordinates_with_moved_source(
        self, tmp_path, monkeypatch
    ):
        source, facade, symbol = await _published_search(tmp_path)
        original_search = symbol._search

        def search_then_save(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            rows = original_search(*args, **kwargs)
            source.write_text(_MOVED_SOURCE, encoding="utf-8")
            return rows

        monkeypatch.setattr(symbol, "_search", search_then_save)
        try:
            result = await facade.execute(
                {"action": "symbol", "query": "target", "output_format": "json"}
            )
            _assert_no_mixed_source(result)
        finally:
            if symbol._cache is not None:
                symbol._cache.close()

    @pytest.mark.skipif(
        os.name != "posix",
        reason="tracked:C1 safe descriptor source capture is POSIX-only",
    )
    async def test_public_search_body_rejects_transient_source_aba(
        self, tmp_path, monkeypatch
    ):
        from tree_sitter_analyzer import source_oracle

        source, facade, symbol = await _published_search(tmp_path)
        original_capture = source_oracle.safe_workspace_path
        observed_transient_read = False
        legacy_reader_called = False

        from tree_sitter_analyzer.mcp.tools import call_path_enrich

        def legacy_live_read(path: str) -> list[str]:
            nonlocal legacy_reader_called
            legacy_reader_called = True
            source.write_text(_MOVED_SOURCE, encoding="utf-8")
            try:
                return Path(path).read_text(encoding="utf-8").splitlines()
            finally:
                source.write_text(_INDEXED_SOURCE, encoding="utf-8")

        def capture_during_transient_save(root: str, path: str, **kwargs: Any) -> Any:
            nonlocal observed_transient_read
            if path != "sample.py" or observed_transient_read:
                return original_capture(root, path, **kwargs)
            observed_transient_read = True
            source.write_text(_MOVED_SOURCE, encoding="utf-8")
            try:
                return original_capture(root, path, **kwargs)
            finally:
                source.write_text(_INDEXED_SOURCE, encoding="utf-8")

        monkeypatch.setattr(
            source_oracle, "safe_workspace_path", capture_during_transient_save
        )
        monkeypatch.setattr(call_path_enrich, "read_file_lines", legacy_live_read)
        try:
            result = await facade.execute(
                {"action": "symbol", "query": "target", "output_format": "json"}
            )
            _assert_no_mixed_source(result)
            assert observed_transient_read is True
            assert legacy_reader_called is False
            assert source.read_text(encoding="utf-8") == _INDEXED_SOURCE
        finally:
            if symbol._cache is not None:
                symbol._cache.close()

    async def test_search_deterrent_next_step(self, tmp_path):
        _source, facade, symbol = await _published_search(tmp_path)
        result = await facade.execute(
            {"action": "symbol", "query": "target", "output_format": "json"}
        )
        assert "no Read needed" in result["next_step"]
        symbol._cache.close()

    @pytest.mark.parametrize("query", ["~arge", "tar*", "missing", "z"])
    async def test_certified_search_modes_share_the_owner_connection(
        self, tmp_path, query, monkeypatch
    ):
        _source, facade, symbol = await _published_search(tmp_path)

        def reject_legacy(*_args: Any, **_kwargs: Any) -> Any:
            pytest.fail("search silently fell back to the live ASTCache connection")

        legacy_cache = symbol._get_cache()
        for name in (
            "get_conn",
            "search_symbols_cascade",
            "fts_search",
            "fts_search_ranked",
            "_search_symbols_linear",
        ):
            monkeypatch.setattr(legacy_cache, name, reject_legacy)
        result = await facade.execute(
            {"action": "symbol", "query": query, "output_format": "json"}
        )
        assert result["success"] is True
        if query in {"~arge", "tar*"}:
            assert [row["name"] for row in result["results"]] == ["target"]
            assert result["verdict"] == "INFO"
        else:
            assert result["results"] == []
            assert result["match_count"] == 0
            assert result["verdict"] == "NOT_FOUND"
        symbol._cache.close()

    async def test_unsupported_safe_capture_stays_coordinate_only(
        self, tmp_path, monkeypatch
    ):
        from tree_sitter_analyzer import source_oracle
        from tree_sitter_analyzer.source_oracle import SourceOracleError

        _source, facade, symbol = await _published_search(tmp_path)

        def unsupported(*_args, **_kwargs):
            raise SourceOracleError("DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED")

        monkeypatch.setattr(source_oracle, "safe_index_source_path", unsupported)
        result = await facade.execute(
            {"action": "symbol", "query": "target", "output_format": "json"}
        )
        hit = result["results"][0]
        assert result["success"] is True
        assert "code" not in hit and "body" not in hit
        assert "no Read needed" not in result.get("next_step", "")
        symbol._cache.close()

    async def test_certified_search_does_not_rescan_repository_after_read(
        self, tmp_path, monkeypatch
    ):
        # PR #1491：导航正文按返回文件摘要认证，不再在请求前后扫描整个仓库。
        from tree_sitter_analyzer import index_snapshot

        _source, facade, symbol = await _published_search(tmp_path)
        monkeypatch.setattr(
            index_snapshot,
            "verify_snapshot_source_current",
            lambda *_args, **_kwargs: pytest.fail("认证搜索不得执行全仓库源码扫描"),
        )

        result = await facade.execute(
            {"action": "symbol", "query": "target", "output_format": "json"}
        )

        assert result["success"] is True
        target = next(row for row in result["results"] if row["name"] == "target")
        assert "code" in target and "body" in target
        assert "INDEXED_MARKER" in target["body"]["content"]
        assert "no Read needed" in result.get("next_step", "")
        symbol._cache.close()

    async def test_owner_exit_failure_removes_all_unbound_enrichment(
        self, tmp_path, monkeypatch
    ):
        # PR #1491：owner 在响应提交前失败时，已拼装的正文必须退回纯坐标结果。
        from contextlib import contextmanager

        from tree_sitter_analyzer import index_snapshot

        _source, facade, symbol = await _published_search(tmp_path)
        original = index_snapshot.certified_index_read

        @contextmanager
        def fail_on_exit(project_root):
            with original(project_root) as certified:
                yield certified
            raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")

        monkeypatch.setattr(index_snapshot, "certified_index_read", fail_on_exit)
        result = await facade.execute(
            {"action": "symbol", "query": "target", "output_format": "json"}
        )

        assert result["success"] is True
        assert all("code" not in row and "body" not in row for row in result["results"])
        assert result["next_step"] == "Use the returned coordinates to read the source."
        symbol._cache.close()

    async def test_snapshot_acquisition_failure_preserves_coordinate_success(
        self, indexed_project, monkeypatch
    ):
        from contextlib import contextmanager

        from tree_sitter_analyzer import index_snapshot

        @contextmanager
        def unavailable(_root):
            raise OSError("snapshot unavailable")
            yield

        monkeypatch.setattr(index_snapshot, "certified_index_read", unavailable)
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "get_user", "output_format": "json"})
        assert result["success"] is True
        assert result["results"]
        assert all("code" not in row and "body" not in row for row in result["results"])
        tool._cache.close()

    async def test_data_source_field(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "UserService", "output_format": "json"})
        assert "data_source" in result
        assert result["data_source"] in ("fts5", "linear_scan")

    async def test_relevance_score_on_fts5_results(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "format_user", "output_format": "json"})
        assert result["success"] is True
        assert result["match_count"] == 1, (
            "fixture must have exactly one format_user symbol"
        )
        assert result["data_source"] == "fts5", (
            f"expected fts5 data source, got {result['data_source']}"
        )
        for hit in result["results"]:
            assert "relevance_score" in hit, (
                "FTS5 results must carry relevance_score (README 'ahead' claim)"
            )
            score = hit["relevance_score"]
            assert 0.0 <= score <= 1.0, f"score out of range: {score}"

    async def test_fuzzy_suffix_finds_camelcase_class(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "~Service", "output_format": "json"})
        assert result["success"] is True
        names = [r["name"] for r in result["results"]]
        assert "UserService" in names, (
            f"~Service must find UserService via linear infix supplement; got {names}"
        )

    async def test_fuzzy_prefix_finds_camelcase_class(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "~User", "output_format": "json"})
        assert result["success"] is True
        names = [r["name"] for r in result["results"]]
        assert "UserService" in names, (
            f"~User must find UserService via prefix match; got {names}"
        )

    async def test_fuzzy_special_chars_do_not_crash(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        for bad_query in ["~foo-bar", "~foo.bar", "~foo:bar"]:
            result = await tool.execute({"query": bad_query, "output_format": "json"})
            assert result["success"] is True, (
                f"Query {bad_query!r} must not crash; got {result}"
            )

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
        """#443：定义排首位，重复 import 折叠且保留文件总数。"""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            (project / "core.py").write_text(
                "def apply_toon_format(data):\n    return data\n"
            )

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

                assert len(results) == 2, (
                    f"Expected 2 results (1 def + 1 folded import), "
                    f"got {len(results)}: {[r['name'] for r in results]}"
                )

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
        # 2026-09-09：没有索引时，不能断言项目里没有匹配符号。
        assert (result["success"], result["error_code"]) == (False, "INDEX_NOT_READY")
        assert result["match_count"] == 0
        tool._cache.close()


class TestCodeGraphSymbolSearchSourceContext:
    def test_exact_search_uses_linear_fallback_without_fts5(self):
        class LinearOnlyCache:
            fts5_available = False

            def _search_symbols_linear(self, query, language=None):
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

    def test_fuzzy_merge_supplements_fts_with_linear_suffix_hits(self):
        """#922：FTS 命中不能阻止线性扫描补回后缀匹配。"""
        tool = CodeGraphSymbolSearchTool()
        results = tool._fuzzy_search(
            FTSAndLinearCache(), "Service", language=None, kind="any", limit=10
        )
        names = [r["name"] for r in results]
        assert "Service" in names, f"FTS5 hit Service must appear; got {names}"
        assert "UserService" in names, (
            f"Linear supplement must add UserService; got {names}"
        )
        assert results[0]["name"] == "Service"
        service_hit = next(r for r in results if r["name"] == "Service")
        assert "relevance_score" in service_hit, "FTS hit must carry relevance_score"

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
    @pytest.mark.parametrize(
        ("group", "action", "expected"),
        [
            ("search", "symbol", "CodeGraphSymbolSearchTool"),
            ("nav", "callers", None),
            ("nav", "callees", None),
        ],
    )
    def test_registered_in_server(self, group, action, expected):
        from tree_sitter_analyzer.mcp.server import _create_tool_registry

        _, tools = _create_tool_registry(None)
        mapping = (
            tools[group].action_map if group == "search" else tools[group].bespoke_map
        )
        assert action in mapping
        if expected:
            assert type(mapping[action]).__name__ == expected


class TestSymbolSearchLimitValidation:
    """#540：limit 必须是正整数。"""

    @pytest.mark.parametrize(("limit", "valid"), [(-5, False), (0, False), (1, True)])
    def test_limit_validation(self, limit, valid):
        arguments = {"query": "foo", "limit": limit}
        if valid:
            assert CodeGraphSymbolSearchTool().validate_arguments(arguments)
        else:
            with pytest.raises(ValueError, match="limit"):
                CodeGraphSymbolSearchTool().validate_arguments(arguments)


class TestSymbolSearchTruncation:
    """#736：达到结果上限时必须公开 truncated。"""

    @pytest.mark.asyncio
    async def test_not_truncated_when_below_limit(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "UserService", "output_format": "json"})
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_truncated_when_at_limit(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "*", "limit": 1, "output_format": "json"})
        if result["match_count"] == 1:
            assert result["truncated"] is True
            assert "limit" in result["next_step"].lower()

    @pytest.mark.asyncio
    async def test_truncated_field_always_present(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute(
            {"query": "nonexistent_xyz", "output_format": "json"}
        )
        assert "truncated" in result


@pytest.mark.asyncio
@pytest.mark.parametrize("indexed", [False, True])
async def test_empty_index_does_not_claim_symbol_absence(tmp_path, indexed):
    # 2026-09-09：冷索引曾将真实存在的函数报告为 NOT_FOUND。
    source = tmp_path / "auth.py"
    source.write_text(
        "def authenticate_user(token): return bool(token)\n", encoding="utf-8"
    )
    cache = ASTCache(str(tmp_path))
    tool = CodeGraphSymbolSearchTool(str(tmp_path))
    try:
        if indexed:
            cache.index_file(str(source))
        result = await tool.execute(
            {"query": "authenticate_user", "output_format": "json"}
        )
        assert (result["success"], result["verdict"]) == (
            (True, "INFO") if indexed else (False, "ERROR")
        )
        if not indexed:
            assert result["error_code"] == "INDEX_NOT_READY"
            assert result["error_type"] == "validation"
            assert result["recovery_hint"] == result["next_step"]
            assert result["agent_summary"]["next_step"] == result["next_step"]
            assert result["results"] == []
            assert "--ast-cache-mode index" in result["next_step"]
    finally:
        cache.close()
        if tool._cache is not None:
            tool._cache.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("empty_project", [False, True])
async def test_indexed_zero_symbols_can_report_not_found(tmp_path, empty_project):
    # 2026-09-09：零符号文件和已完成的空项目不能被误判为尚未建索引。
    if not empty_project:
        (tmp_path / "empty.py").write_text("# 空模块\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    tool = CodeGraphSymbolSearchTool(str(tmp_path))
    try:
        cache.index_project(max_files=20)
        result = await tool.execute(
            {"query": "authenticate_user", "output_format": "json"}
        )
        assert (result["success"], result["verdict"], result["results"]) == (
            True,
            "NOT_FOUND",
            [],
        )
    finally:
        cache.close()
        if tool._cache is not None:
            tool._cache.close()
