"""#1376：test_ast_cache_call_graph 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import sqlite3

import pytest

import tests.unit._ast_cache_helpers as _fixtures
from tree_sitter_analyzer.ast_cache import (
    ASTCache,
    _has_fts5,
)

tmp_project = _fixtures.tmp_project
cache = _fixtures.cache
method_project = _fixtures.method_project


class TestSQLNativeCallGraph:
    """query_callers 和 query_callees 的 SQL 原生方法测试。"""

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
            "    pass\n",
            encoding="utf-8",
        )
        (src / "b.py").write_text("def bar():\n    pass\n", encoding="utf-8")
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

    def test_query_callees_finds_go_method_selector_calls(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "gin.go").write_text(
            "package gin\n\n"
            "type Engine struct{}\n\n"
            "func (engine *Engine) ServeHTTP() {\n"
            "    engine.handleHTTPRequest()\n"
            "}\n\n"
            "func (engine *Engine) handleHTTPRequest() {}\n",
            encoding="utf-8",
        )
        cache = ASTCache(str(tmp_path))
        try:
            cache.index_project()

            callees = cache.query_callees("ServeHTTP", caller_file="src/gin.go")
            assert [edge["callee_name"] for edge in callees] == ["handleHTTPRequest"]
            assert [edge["callee_full"] for edge in callees] == [
                "engine.handleHTTPRequest"
            ]

            callers = cache.query_callers("handleHTTPRequest", callee_file="src/gin.go")
            assert [edge["caller_name"] for edge in callers] == ["ServeHTTP"]

            full_callers = cache.query_callers(
                "engine.handleHTTPRequest", callee_file="src/gin.go"
            )
            assert [edge["caller_name"] for edge in full_callers] == ["ServeHTTP"]
        finally:
            cache.close()

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
        assert len(callees) == 2
        for e in callees:
            assert e["caller_file"] == "src/a.py"

    def test_query_callers_with_file_filter(self, call_cache):
        callers = call_cache.query_callers("bar", callee_file="src/a.py")
        assert len(callers) == 1

    def test_query_callers_transitive(self, call_cache):
        callers = call_cache.query_callers("bar", max_depth=3)
        assert len(callers) == 1

    def test_query_callees_transitive(self, call_cache):
        callees = call_cache.query_callees("foo", max_depth=3)
        assert len(callees) == 2

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
            assert e["depth"] == 1


class TestPostIndexEdgeRefreshSkip:
    """提交期间 insert 已写入边，FTS5 可用的常见路径不应重复执行索引后的 refresh；此前它为相同边集合消耗约 47% 的 Django 索引时间。"""

    def test_refresh_skipped_when_fts5_available(self, tmp_project, monkeypatch):
        from tree_sitter_analyzer.ast_cache import ASTCache

        c = ASTCache(str(tmp_project))
        if not c.fts5_available:
            c.close()
            pytest.skip("SQLite built without FTS5 — refresh-skip path needs FTS5")
        try:
            calls = {"n": 0}
            orig = c._refresh_graph_edges_from_cache

            def spy(*a, **k):
                calls["n"] += 1
                return orig(*a, **k)

            monkeypatch.setattr(c, "_refresh_graph_edges_from_cache", spy)
            c.index_project(force=True)

            # FTS5 路径中，insert 已经写入边，不应调用 refresh。
            assert c.fts5_available is True
            assert calls["n"] == 0
            # 无论哪条路径，边都必须存在。
            conn = c._get_conn()
            assert conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0] == 1
        finally:
            c.close()

    def test_refresh_skipped_when_fts5_unavailable(self, tmp_project, monkeypatch):
        from tree_sitter_analyzer.ast_cache import ASTCache

        c = ASTCache(str(tmp_project))
        try:
            # 图行写入现在独立于 FTS 是否可用。
            monkeypatch.setattr(type(c), "fts5_available", property(lambda self: False))
            calls = {"n": 0}
            orig = c._refresh_graph_edges_from_cache

            def spy(*a, **k):
                calls["n"] += 1
                return orig(*a, **k)

            monkeypatch.setattr(c, "_refresh_graph_edges_from_cache", spy)
            c.index_project(force=True)

            assert calls["n"] == 0
        finally:
            c.close()

    def test_force_rebuild_writes_non_fts_derived_rows(self, tmp_path):
        path = tmp_path / "app.py"
        path.write_text(
            "import os\n\ndef current():\n    return os.getcwd()\n", encoding="utf-8"
        )
        cache = ASTCache(str(tmp_path))
        cache._fts5_available = False

        try:
            cache.index_project(force=True, workers=0)
            conn = cache.get_conn()
            counts = {
                "imports": conn.execute("SELECT COUNT(*) FROM ast_imports").fetchone()[
                    0
                ],
                "calls": conn.execute(
                    "SELECT COUNT(*) FROM edges WHERE kind = 'calls'"
                ).fetchone()[0],
            }
        finally:
            cache.close()

        assert counts == {"imports": 1, "calls": 1}


class TestMethodKindClassification:
    """验证类方法存储为 kind=method，而不是 kind=function。"""

    def test_method_stored_as_kind_method(self, method_project):
        """索引带类方法的文件后，ast_symbol_rows 必须至少包含一行 kind=method。"""
        from tree_sitter_analyzer.ast_cache import ASTCache

        c = ASTCache(str(method_project))
        try:
            c.index_project()
            conn = c._get_conn()
            method_count = conn.execute(
                "SELECT COUNT(*) FROM ast_symbol_rows WHERE kind='method'"
            ).fetchone()[0]
            assert method_count == 1, (
                "Expected exactly one kind='method' row but got "
                f"{method_count}. "
                "Class methods are being incorrectly stored as kind='function'."
            )
        finally:
            c.close()

    def test_method_kind_bark_found(self, method_project):
        """Dog 类中的 bark 方法必须以 kind=method 存储。"""
        from tree_sitter_analyzer.ast_cache import ASTCache

        c = ASTCache(str(method_project))
        try:
            c.index_project()
            conn = c._get_conn()
            row = conn.execute(
                "SELECT kind FROM ast_symbol_rows WHERE name='bark'"
            ).fetchone()
            assert row is not None, "Symbol 'bark' not found in ast_symbol_rows"
            assert row[0] == "method", (
                f"Expected kind='method' for 'bark' but got kind='{row[0]}'"
            )
        finally:
            c.close()

    def test_top_level_function_stays_kind_function(self, method_project):
        """没有父类的顶层函数必须保留 kind=function。"""
        from tree_sitter_analyzer.ast_cache import ASTCache

        c = ASTCache(str(method_project))
        try:
            c.index_project()
            conn = c._get_conn()
            row = conn.execute(
                "SELECT kind FROM ast_symbol_rows WHERE name='standalone'"
            ).fetchone()
            assert row is not None, "Symbol 'standalone' not found"
            assert row[0] == "function", (
                f"Expected kind='function' for 'standalone' but got kind='{row[0]}'"
            )
        finally:
            c.close()

    @pytest.mark.skipif(
        not _has_fts5(sqlite3.connect(":memory:")), reason="FTS5 not available"
    )
    def test_fts_search_finds_method_by_kind(self, method_project):
        """bark 的 fts_search 结果必须包含 kind=method 的 FTS 条目。"""
        from tree_sitter_analyzer.ast_cache import ASTCache

        c = ASTCache(str(method_project))
        try:
            c.index_project()
            conn = c._get_conn()
            rows = conn.execute(
                "SELECT name, kind FROM ast_symbol_rows WHERE name='bark'"
            ).fetchall()
            assert any(r[1] == "method" for r in rows), (
                "FTS5 / ast_symbol_rows has no kind='method' row for 'bark'"
            )
        finally:
            c.close()

    def test_serial_and_parallel_agree_on_method_kind(self, method_project):
        """串行 workers=0 和并行 workers=2 索引路径必须生成相同的 kind=method 行，用于防止 worker 元组序列化路径回归。"""
        from tree_sitter_analyzer.ast_cache import ASTCache

        db_serial = method_project / "ser.db"
        db_parallel = method_project / "par.db"

        serial_cache = ASTCache(str(method_project), db_path=str(db_serial))
        serial_cache.index_project(workers=0)

        parallel_cache = ASTCache(str(method_project), db_path=str(db_parallel))
        parallel_cache.index_project(workers=2)

        try:
            symbol_sql = (
                "SELECT name, kind FROM ast_symbol_rows "
                "WHERE name IN ('bark', 'standalone') "
                "ORDER BY name"
            )
            s_rows = [
                tuple(r)
                for r in serial_cache._get_conn().execute(symbol_sql).fetchall()
            ]
            p_rows = [
                tuple(r)
                for r in parallel_cache._get_conn().execute(symbol_sql).fetchall()
            ]
            assert s_rows == p_rows, (
                f"Serial and parallel paths disagree on method kind:\n"
                f"  serial={s_rows}\n  parallel={p_rows}"
            )
            assert ("bark", "method") in s_rows, (
                f"'bark' not classified as method in serial path: {s_rows}"
            )
        finally:
            serial_cache.close()
            parallel_cache.close()
