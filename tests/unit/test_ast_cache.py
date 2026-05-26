"""Tests for the pre-indexed AST cache (ast_cache module)."""

import sqlite3
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.ast_cache import (
    _EXT_TO_LANG,
    ASTCache,
    _content_hash,
    _extract_symbols,
    _has_fts5,
)


@pytest.fixture
def tmp_project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text(
        "def hello():\n    print('hello')\n\nclass Foo:\n    pass\n"
    )
    (src / "util.js").write_text("function add(a, b) { return a + b; }\n")
    (src / "readme.md").write_text("# Readme\n")
    return tmp_path


@pytest.fixture
def cache(tmp_project):
    c = ASTCache(str(tmp_project))
    yield c
    c.close()


def _query_plan(conn: sqlite3.Connection, sql: str, params: tuple[str, ...]) -> str:
    rows = conn.execute(f"EXPLAIN QUERY PLAN {sql}", params).fetchall()
    return " ".join(str(row[3]) for row in rows)


class TestContentHash:
    def test_deterministic(self):
        assert _content_hash("hello") == _content_hash("hello")

    def test_different_content(self):
        assert _content_hash("hello") != _content_hash("world")

    def test_bytes_input(self):
        assert _content_hash(b"hello") == _content_hash("hello")


class TestIndexFile:
    def test_index_python_file(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        result = cache.index_file(f)
        assert result["status"] == "indexed"
        assert result["symbols"] > 0

    def test_index_unsupported_language(self, cache, tmp_project):
        f = str(tmp_project / "readme.md")
        result = cache.index_file(f)
        assert result["status"] == "skipped"

    def test_index_nonexistent_file(self, cache, tmp_project):
        f = str(tmp_project / "nonexistent.py")
        result = cache.index_file(f)
        assert result["status"] == "error"

    def test_cached_on_second_index(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        cache.index_file(f)
        result = cache.index_file(f)
        assert result["status"] == "cached"

    def test_index_with_explicit_language(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        result = cache.index_file(f, language="python")
        assert result["status"] == "indexed"


class TestIndexProject:
    def test_index_project(self, cache):
        result = cache.index_project()
        assert result["total_files"] >= 2
        assert result["indexed"] >= 2

    def test_index_project_cached(self, cache):
        cache.index_project()
        result = cache.index_project()
        assert result["cached"] >= 2

    def test_index_project_force(self, cache):
        cache.index_project()
        result = cache.index_project(force=True)
        assert result["indexed"] >= 2

    def test_index_project_max_files(self, cache):
        result = cache.index_project(max_files=1)
        assert result["total_files"] <= 1

    def test_index_project_workers_field_in_stats(self, cache):
        """PERF-4: stats include the resolved worker count."""
        result = cache.index_project(workers=0)
        assert "workers" in result
        assert result["workers"] == 0

    def test_index_project_serial_and_parallel_agree(self, tmp_project):
        """PERF-4 correctness: parallel and serial paths must produce
        identical indexed counts and SQLite contents."""
        from tree_sitter_analyzer.ast_cache import ASTCache

        db_serial = tmp_project / "ser.db"
        db_parallel = tmp_project / "par.db"
        for db in (db_serial, db_parallel):
            if db.exists():
                db.unlink()

        serial_cache = ASTCache(str(tmp_project), db_path=str(db_serial))
        serial_result = serial_cache.index_project(workers=0)

        parallel_cache = ASTCache(str(tmp_project), db_path=str(db_parallel))
        # 2 workers is enough to exercise the spawn + IPC path.
        parallel_result = parallel_cache.index_project(workers=2)

        assert serial_result["indexed"] == parallel_result["indexed"]
        assert serial_result["errors"] == parallel_result["errors"]

        # Compare actual row sets — same files, same content_hash, same
        # symbols payload. Done in-process to avoid worker spawn here.
        serial_conn = serial_cache._get_conn()
        parallel_conn = parallel_cache._get_conn()
        s_rows = sorted(
            tuple(r)
            for r in serial_conn.execute(
                "SELECT file_path, content_hash, language FROM ast_index"
            ).fetchall()
        )
        p_rows = sorted(
            tuple(r)
            for r in parallel_conn.execute(
                "SELECT file_path, content_hash, language FROM ast_index"
            ).fetchall()
        )
        assert s_rows == p_rows

    def test_index_project_env_workers_override(self, cache, monkeypatch):
        """PERF-4: TSA_INDEX_WORKERS env var overrides the workers kwarg."""
        monkeypatch.setenv("TSA_INDEX_WORKERS", "0")
        # Pass workers=4 explicitly; env should win and force serial.
        result = cache.index_project(workers=4)
        assert result["workers"] == 0

    def test_index_project_skips_activation_by_default(self, cache, monkeypatch):
        """Large-repo warm-cache builds must not run per-file git history by default."""
        monkeypatch.delenv("TSA_INDEX_ACTIVATION", raising=False)
        with patch(
            "tree_sitter_analyzer.git_activation.compute_symbol_activation"
        ) as compute:
            result = cache.index_project(workers=0)

        assert result["activation_enabled"] is False
        compute.assert_not_called()
        conn = cache._get_conn()
        activation_rows = conn.execute(
            "SELECT COUNT(*) FROM ast_symbol_activation"
        ).fetchone()[0]
        assert activation_rows == 0

    def test_index_project_activation_opt_in_via_argument(self, cache, monkeypatch):
        monkeypatch.delenv("TSA_INDEX_ACTIVATION", raising=False)
        with patch(
            "tree_sitter_analyzer.git_activation.compute_symbol_activation",
            return_value=[],
        ) as compute:
            result = cache.index_project(workers=0, include_activation=True)

        assert result["activation_enabled"] is True
        assert compute.called

    def test_index_project_activation_opt_in_via_env(self, cache, monkeypatch):
        monkeypatch.setenv("TSA_INDEX_ACTIVATION", "1")
        with patch(
            "tree_sitter_analyzer.git_activation.compute_symbol_activation",
            return_value=[],
        ) as compute:
            result = cache.index_project(workers=0)

        assert result["activation_enabled"] is True
        assert compute.called


class TestLookup:
    def test_lookup_indexed_file(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        cache.index_file(f)
        result = cache.lookup(f)
        assert result is not None
        assert result["language"] == "python"
        assert "symbols" in result
        assert "structure" in result

    def test_lookup_missing_file(self, cache):
        result = cache.lookup("/nonexistent/file.py")
        assert result is None


class TestSearchSymbols:
    def test_search_by_name(self, cache, tmp_project):
        cache.index_project()
        results = cache.search_symbols("hello")
        assert len(results) >= 1
        assert any(r["name"] == "hello" for r in results)

    def test_search_by_language(self, cache, tmp_project):
        cache.index_project()
        results = cache.search_symbols("add", language="javascript")
        assert len(results) >= 1

    def test_search_no_results(self, cache, tmp_project):
        cache.index_project()
        results = cache.search_symbols("zzz_nonexistent_xyz")
        assert len(results) == 0


class TestStats:
    def test_stats_empty(self, cache):
        stats = cache.get_stats()
        assert stats["total_files"] == 0
        assert stats["total_symbols"] == 0

    def test_stats_after_index(self, cache):
        cache.index_project()
        stats = cache.get_stats()
        assert stats["total_files"] >= 2
        assert stats["total_symbols"] > 0
        assert "python" in stats["by_language"]

    def test_stats_uses_symbol_rows_when_fts_available(self, cache):
        cache.index_project()
        if not cache._fts5_available:
            pytest.skip("FTS5 not available")

        with patch(
            "tree_sitter_analyzer.ast_cache.json.loads",
            side_effect=AssertionError("get_stats should not scan symbols_json"),
        ):
            stats = cache.get_stats()

        assert stats["total_symbols"] == stats["fts_indexed_symbols"]
        assert stats["total_symbols"] > 0

    def test_stats_falls_back_to_symbols_json_without_fts(self, cache):
        cache.index_project()
        cache._fts5_available = False

        stats = cache.get_stats()

        assert stats["total_symbols"] > 0
        assert stats["fts5_available"] is False

    def test_stats_falls_back_when_symbol_rows_table_missing(self, cache):
        cache.index_project()
        if not cache._fts5_available:
            pytest.skip("FTS5 not available")

        conn = cache._get_conn()
        conn.execute("DROP TABLE ast_symbol_rows")

        stats = cache.get_stats()

        assert stats["total_symbols"] > 0

    def test_clear_activation_for_file_ignores_missing_table(self, cache):
        conn = sqlite3.connect(":memory:")

        ASTCache._clear_activation_for_file(conn, "src/main.py")

        conn.close()


class TestLargeRepoHotPathIndexes:
    def test_large_repo_hot_path_indexes_exist(self, cache):
        if not cache._fts5_available:
            pytest.skip("tracked: large-repo-hotpath-indexes require FTS5")
        conn = cache._get_conn()
        index_names = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }

        assert "idx_sym_rows_name_kind_path_line" in index_names
        assert "idx_sym_rows_file_name_kind_line" in index_names
        assert "idx_ce_callee_name_resolved_file" in index_names
        assert "idx_ce_callee_name_file_path" in index_names
        assert "idx_ce_caller_name_file" in index_names

    def test_symbol_resolver_hot_queries_use_composite_indexes(self, cache):
        if not cache._fts5_available:
            pytest.skip("tracked: large-repo-hotpath-indexes require FTS5")
        conn = cache._get_conn()

        symbol_plan = _query_plan(
            conn,
            """SELECT name, kind, file_path, language, line, end_line
               FROM ast_symbol_rows
               WHERE name = ? AND kind IN ('function', 'class', 'method', 'variable')
               ORDER BY file_path, line""",
            ("target",),
        )
        scoped_symbol_plan = _query_plan(
            conn,
            """SELECT name, kind, file_path, language, line, end_line
               FROM ast_symbol_rows
               WHERE file_path = ? AND name = ? AND kind IN ('function', 'class', 'method')
               ORDER BY line""",
            ("src/main.py", "target"),
        )

        assert "idx_sym_rows_name_kind_path_line" in symbol_plan
        assert "idx_sym_rows_file_name_kind_line" in scoped_symbol_plan

    def test_call_graph_hot_queries_use_composite_indexes(self, cache):
        conn = cache._get_conn()

        callers_plan = _query_plan(
            conn,
            """SELECT caller_name, caller_file, caller_line,
                      callee_name, file_path, callee_line, callee_resolved_file
               FROM ast_call_edges
               WHERE callee_name = ? AND callee_resolved_file = ?""",
            ("render", "src/view.py"),
        )
        callers_fallback_plan = _query_plan(
            conn,
            """SELECT caller_name, caller_file, caller_line,
                      callee_name, file_path, callee_line, callee_resolved_file
               FROM ast_call_edges
               WHERE callee_name = ? AND file_path = ?""",
            ("render", "src/view.py"),
        )
        callees_plan = _query_plan(
            conn,
            """SELECT caller_name, caller_file, caller_line,
                      callee_name, callee_full, file_path, callee_line, callee_resolved_file
               FROM ast_call_edges
               WHERE caller_name = ? AND caller_file = ?""",
            ("handle", "src/handler.py"),
        )

        assert "idx_ce_callee_name_resolved_file" in callers_plan
        assert "idx_ce_callee_name_file_path" in callers_fallback_plan
        assert "idx_ce_caller_name_file" in callees_plan

    def test_large_repo_index_helper_skips_missing_tables(self):
        conn = sqlite3.connect(":memory:")

        ASTCache._ensure_large_repo_indexes(conn)

        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
            == []
        )
        conn.close()

    def test_large_repo_index_helper_tolerates_legacy_partial_tables(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE ast_call_edges (callee_name TEXT)")

        ASTCache._ensure_large_repo_indexes(conn)

        index_names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        assert "idx_ce_callee_name_resolved_file" not in index_names
        conn.close()


class TestInvalidate:
    def test_invalidate_existing(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        cache.index_file(f)
        assert cache.invalidate(f) is True
        assert cache.lookup(f) is None

    def test_invalidate_nonexistent(self, cache):
        assert cache.invalidate("/nonexistent.py") is False


class TestExtractSymbols:
    def test_extract_from_none_tree(self):
        result = _extract_symbols(None, "x = 1", "python")
        assert result["symbols"] == []
        assert result["node_count"] == 0


class TestExtToLang:
    def test_common_extensions(self):
        assert _EXT_TO_LANG[".py"] == "python"
        assert _EXT_TO_LANG[".js"] == "javascript"
        assert _EXT_TO_LANG[".ts"] == "typescript"
        assert _EXT_TO_LANG[".java"] == "java"
        assert _EXT_TO_LANG[".go"] == "go"
        assert _EXT_TO_LANG[".c"] == "c"
        assert _EXT_TO_LANG[".cpp"] == "cpp"


class TestDbPersistence:
    def test_cache_persists_across_instances(self, tmp_project):
        c1 = ASTCache(str(tmp_project))
        f = str(tmp_project / "src" / "main.py")
        c1.index_file(f)
        stats1 = c1.get_stats()
        c1.close()

        c2 = ASTCache(str(tmp_project), db_path=c1.db_path)
        stats2 = c2.get_stats()
        assert stats2["total_files"] == stats1["total_files"]
        c2.close()


class TestHasFts5:
    def test_detects_fts5(self):
        conn = sqlite3.connect(":memory:")
        result = _has_fts5(conn)
        conn.close()
        assert isinstance(result, bool)


@pytest.mark.skipif(
    not _has_fts5(sqlite3.connect(":memory:")), reason="FTS5 not available"
)
class TestFtsSearch:
    def test_fts_search_basic(self, cache, tmp_project):
        cache.index_project()
        results = cache.fts_search("hello")
        assert len(results) >= 1
        assert any(r["name"] == "hello" for r in results)

    def test_fts_search_by_language(self, cache, tmp_project):
        cache.index_project()
        results = cache.fts_search("add", language="javascript")
        assert len(results) >= 1
        assert all(r["language"] == "javascript" for r in results)

    def test_fts_search_no_results(self, cache, tmp_project):
        cache.index_project()
        results = cache.fts_search("zzz_nonexistent_xyz")
        assert len(results) == 0

    def test_fts_search_multi_term(self, cache, tmp_project):
        cache.index_project()
        results = cache.fts_search("hello foo")
        assert len(results) >= 1

    def test_fts_search_with_limit(self, cache, tmp_project):
        cache.index_project()
        results = cache.fts_search("hello", limit=1)
        assert len(results) <= 1

    def test_fts_search_returns_ranked(self, cache, tmp_project):
        cache.index_project()
        results = cache.fts_search("hello")
        assert len(results) >= 1
        for r in results:
            assert "file" in r
            assert "name" in r
            assert "kind" in r
            assert "line" in r

    def test_search_symbols_uses_fts5_when_available(self, cache, tmp_project):
        cache.index_project()
        results = cache.search_symbols("hello")
        assert len(results) >= 1
        if cache._fts5_available:
            assert any(r["name"] == "hello" for r in results)

    def test_fts_indexed_symbols_in_stats(self, cache, tmp_project):
        cache.index_project()
        stats = cache.get_stats()
        if cache._fts5_available:
            assert stats["fts5_available"] is True
            assert "fts_indexed_symbols" in stats
            assert stats["fts_indexed_symbols"] > 0

    def test_invalidate_removes_fts_rows(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        cache.index_file(f)
        if cache._fts5_available:
            results_before = cache.fts_search("hello")
            assert len(results_before) >= 1
            cache.invalidate(f)
            results_after = cache.fts_search("hello")
            assert len(results_after) == 0

    def test_fts_search_after_reindex(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        cache.index_file(f)
        if cache._fts5_available:
            cache.invalidate(f)
            cache.index_file(f)
            results = cache.fts_search("hello")
            assert len(results) >= 1


class TestSQLNativeCallGraph:
    """Tests for query_callers / query_callees SQL-native methods."""

    @pytest.fixture
    def call_project(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text(
            "from src.b import bar\n\n"
            "def foo():\n"
            "    bar()\n"
            "    baz()\n\n"
            "def baz():\n"
            "    pass\n"
        )
        (src / "b.py").write_text("def bar():\n    pass\n")
        return tmp_path

    @pytest.fixture
    def call_cache(self, call_project):
        c = ASTCache(str(call_project))
        c.index_project()
        yield c
        c.close()

    def test_query_callees_finds_direct_calls(self, call_cache):
        callees = call_cache.query_callees("foo")
        callee_names = [e["callee_name"] for e in callees]
        assert "bar" in callee_names

    def test_query_callers_finds_caller(self, call_cache):
        callers = call_cache.query_callers("bar")
        caller_names = [e["caller_name"] for e in callers]
        assert "foo" in caller_names

    def test_query_callers_empty_for_unknown(self, call_cache):
        callers = call_cache.query_callers("nonexistent_func_xyz")
        assert callers == []

    def test_query_callees_empty_for_leaf(self, call_cache):
        callees = call_cache.query_callees("baz")
        assert callees == []

    def test_query_callees_with_file_filter(self, call_cache):
        callees = call_cache.query_callees("foo", caller_file="src/a.py")
        assert len(callees) > 0
        for e in callees:
            assert e["caller_file"] == "src/a.py"

    def test_query_callers_with_file_filter(self, call_cache):
        callers = call_cache.query_callers("bar", callee_file="src/a.py")
        assert len(callers) > 0

    def test_query_callers_transitive(self, call_cache):
        callers = call_cache.query_callers("bar", max_depth=3)
        assert len(callers) >= 1

    def test_query_callees_transitive(self, call_cache):
        callees = call_cache.query_callees("foo", max_depth=3)
        assert len(callees) >= 1

    def test_has_call_edges(self, call_cache):
        assert call_cache.has_call_edges() is True

    def test_has_call_edges_empty_cache(self, tmp_path):
        c = ASTCache(str(tmp_path))
        assert c.has_call_edges() is False
        c.close()

    def test_query_results_have_required_keys(self, call_cache):
        callees = call_cache.query_callees("foo")
        if callees:
            e = callees[0]
            assert "caller_name" in e
            assert "caller_file" in e
            assert "caller_line" in e
            assert "callee_name" in e
            assert "callee_file" in e
            assert "callee_line" in e
            assert "depth" in e

    def test_depth_1_is_default(self, call_cache):
        callees = call_cache.query_callees("foo", max_depth=1)
        for e in callees:
            assert e["depth"] == 1

    def test_query_callers_returns_depth(self, call_cache):
        callers = call_cache.query_callers("bar")
        for e in callers:
            assert e["depth"] >= 1
