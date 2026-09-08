"""#1376：test_ast_cache_symbols 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import sqlite3

import pytest

import tests.unit._ast_cache_helpers as _fixtures
from tests.unit._ast_cache_helpers import _query_plan
from tree_sitter_analyzer.ast_cache import (
    ASTCache,
    _has_fts5,
)

tmp_project = _fixtures.tmp_project
cache = _fixtures.cache
method_project = _fixtures.method_project


class TestSearchSymbols:
    def test_search_by_name(self, cache, tmp_project):
        cache.index_project()
        results = cache.search_symbols("hello")
        assert len(results) == 1
        assert any(r["name"] == "hello" for r in results)

    def test_search_by_language(self, cache, tmp_project):
        cache.index_project()
        results = cache.search_symbols("add", language="javascript")
        assert len(results) == 1

    def test_search_no_results(self, cache, tmp_project):
        cache.index_project()
        results = cache.search_symbols("zzz_nonexistent_xyz")
        assert len(results) == 0

    def test_search_symbols_uses_linear_when_fts_disabled(self, cache, tmp_project):
        """_fts5_available 为 False 时，search_symbols() 回退到线性扫描。"""
        cache.index_project()
        cache._fts5_available = False
        results = cache.search_symbols("hello")
        assert len(results) == 1
        assert any(r["name"] == "hello" for r in results)


class TestLargeRepoHotPathIndexes:
    def test_large_repo_hot_path_indexes_exist(self, cache):
        if not cache.fts5_available:
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
        # B1.3：CALLS 热路径索引位于统一的 edges 表。
        assert "idx_edges_callee_name" in index_names
        assert "idx_edges_caller_name" in index_names
        assert "idx_edges_file_path" in index_names

    def test_symbol_resolver_hot_queries_use_composite_indexes(self, cache):
        if not cache.fts5_available:
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
        # B1.3：CALLS 行及其名称、文件和解析字段都位于
        # 统一的 edges 表，由 EdgeStore 的名称和文件索引提供查询。
        conn = cache._get_conn()

        callers_plan = _query_plan(
            conn,
            """SELECT caller_name, file_path, caller_line, callee_name,
                      callee_line, callee_resolved_file
               FROM edges
               WHERE kind = 'calls' AND callee_name = ?""",
            ("render",),
        )
        callees_plan = _query_plan(
            conn,
            """SELECT caller_name, file_path, caller_line, callee_name,
                      callee_full, callee_line, callee_resolved_file
               FROM edges
               WHERE kind = 'calls' AND caller_name = ?""",
            ("handle",),
        )
        file_scope_plan = _query_plan(
            conn,
            "SELECT id FROM edges WHERE kind = 'calls' AND file_path = ?",
            ("src/handler.py",),
        )

        assert "idx_edges_callee_name" in callers_plan
        assert "idx_edges_caller_name" in callees_plan
        assert "idx_edges_file_path" in file_scope_plan

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
        # B1.3：ast_call_edges 热路径索引已移除；helper 现在
        # 仅创建 ast_symbol_rows 复合索引，并容忍不完整的
        # 旧版表时也不能报错。
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE ast_symbol_rows (name TEXT)")

        ASTCache._ensure_large_repo_indexes(conn)

        index_names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        assert "idx_ce_callee_name_resolved_file" not in index_names
        conn.close()


@pytest.mark.skipif(
    not _has_fts5(sqlite3.connect(":memory:")), reason="FTS5 not available"
)
class TestFtsSearch:
    def test_fts_search_basic(self, cache, tmp_project):
        cache.index_project()
        results = cache.fts_search("hello")
        assert len(results) == 1
        assert any(r["name"] == "hello" for r in results)

    def test_fts_search_by_language(self, cache, tmp_project):
        cache.index_project()
        results = cache.fts_search("add", language="javascript")
        assert len(results) == 1
        assert all(r["language"] == "javascript" for r in results)

    def test_fts_search_no_results(self, cache, tmp_project):
        cache.index_project()
        results = cache.fts_search("zzz_nonexistent_xyz")
        assert len(results) == 0

    def test_fts_search_multi_term(self, cache, tmp_project):
        cache.index_project()
        results = cache.fts_search("hello foo")
        assert len(results) == 2

    def test_fts_search_with_limit(self, cache, tmp_project):
        cache.index_project()
        results = cache.fts_search("hello", limit=1)
        assert len(results) <= 1

    def test_fts_search_returns_ranked(self, cache, tmp_project):
        cache.index_project()
        results = cache.fts_search("hello")
        assert len(results) == 1
        for r in results:
            assert "file" in r
            assert "name" in r
            assert "kind" in r
            assert "line" in r

    def test_search_symbols_uses_fts5_when_available(self, cache, tmp_project):
        cache.index_project()
        results = cache.search_symbols("hello")
        assert len(results) == 1
        if cache.fts5_available:
            assert any(r["name"] == "hello" for r in results)

    def test_fts_indexed_symbols_in_stats(self, cache, tmp_project):
        cache.index_project()
        stats = cache.get_stats()
        if cache.fts5_available:
            assert stats["fts5_available"] is True
            assert "fts_indexed_symbols" in stats
            assert stats["fts_indexed_symbols"] == 3

    def test_invalidate_removes_fts_rows(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        cache.index_file(f)
        if cache.fts5_available:
            results_before = cache.fts_search("hello")
            assert len(results_before) == 1
            cache.invalidate(f)
            results_after = cache.fts_search("hello")
            assert len(results_after) == 0

    def test_fts_search_after_reindex(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        cache.index_file(f)
        if cache.fts5_available:
            cache.invalidate(f)
            cache.index_file(f)
            results = cache.fts_search("hello")
            assert len(results) == 1

    def test_fts_search_falls_back_to_linear_when_fts_disabled(
        self, cache, tmp_project
    ):
        """_fts5_available 为 False 时，fts_search() 回退到线性扫描。"""
        cache.index_project()
        cache._fts5_available = False
        results = cache.fts_search("hello")
        assert len(results) == 1
        assert any(r["name"] == "hello" for r in results)

    def test_get_functions_by_file_returns_functions_for_indexed_file(
        self, cache, tmp_project
    ):
        """get_functions_by_file() 返回已索引文件的函数条目。"""
        f = str(tmp_project / "src" / "main.py")
        cache.index_file(f)
        funcs = cache.get_functions_by_file("src/main.py")
        assert len(funcs) == 1
        for fn in funcs:
            assert "name" in fn
            assert "file" in fn
            assert "line" in fn


def test_no_fts_index_file_populates_ordinary_symbol_rows(tmp_path):
    # PR #1253: ast_symbol_rows 是统一普通存储，不是 FTS 实现细节。
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "sample.py"
    source.write_text("def answer():\n    return 42\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache._fts5_available = False
    try:
        cache.index_file(str(source))
        rows = (
            cache.get_conn()
            .execute("SELECT name, kind, file_path FROM ast_symbol_rows")
            .fetchall()
        )
    finally:
        cache.close()

    assert [tuple(row) for row in rows] == [("answer", "function", "sample.py")]


def test_no_fts_miswire_definition_reader_uses_ordinary_rows(tmp_path):
    # PR #1253: 无 FTS 的定义消费者必须能看到新索引的符号。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.miswire_audit import _iter_symbol_defs

    source = tmp_path / "sample.py"
    source.write_text("def answer():\n    return 42\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache._fts5_available = False
    try:
        cache.index_file(str(source))
        definitions = _iter_symbol_defs(cache.get_conn())
    finally:
        cache.close()

    assert definitions == [("answer", "sample.py", "python")]


def test_no_fts_symbol_search_reads_ordinary_rows(tmp_path):
    # PR #1253: 没有虚拟 FTS 表时，线性符号搜索仍必须可用。
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "sample.py"
    source.write_text("def answer():\n    return 42\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache._fts5_available = False
    try:
        cache.index_file(str(source))
        results = cache.search_symbols("answer")
    finally:
        cache.close()

    assert [(row["name"], row["file"], row["kind"]) for row in results] == [
        ("answer", "sample.py", "function")
    ]
