"""Pulse Python 反向导入派生表缓存的行为测试（审计 P2-2）。

从 test_pulse.py 拆出以遵守 800 行治理阈值；断言原样迁移。
"""

from __future__ import annotations

from tree_sitter_analyzer.api.pulse import query_pulse


class _BindingFetchCounter:
    """代理连接：统计 ast_imports 全量扫描次数（缓存命中验证，审计 P2-2）。"""

    def __init__(self, conn):
        self._conn = conn
        self.full_fetches = 0

    def execute(self, sql, *args):
        if "FROM ast_imports" in sql and "COUNT" not in sql:
            self.full_fetches += 1
        return self._conn.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _indexed_two_file_project(tmp_path):
    from tree_sitter_analyzer.ast_cache import ASTCache

    (tmp_path / "mod.py").write_text("def run():\n    pass\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text(
        "from mod import run\nrun()\n", encoding="utf-8"
    )
    cache = ASTCache(str(tmp_path))
    for name in ("mod.py", "consumer.py"):
        cache.index_file(str(tmp_path / name))
    return cache


def test_python_importers_cache_hits_on_second_query(tmp_path):
    """审计 P2-2：文件库上重复查询只做一次 ast_imports 全量扫描。"""
    cache = _indexed_two_file_project(tmp_path)
    try:
        counter = _BindingFetchCounter(cache.get_conn())
        first = query_pulse(counter, "mod.py", "run")
        second = query_pulse(counter, "mod.py", "run")
        assert first is not None and second is not None
        assert second.imported_by == ("consumer.py",)
        assert counter.full_fetches == 1
    finally:
        cache.close()


def test_python_importers_cache_invalidates_on_binding_change(tmp_path):
    """审计 P2-2：绑定表内容变化（计数戳变化）后缓存失效，新导入者可见。"""
    cache = _indexed_two_file_project(tmp_path)
    try:
        conn = cache.get_conn()
        first = query_pulse(conn, "mod.py", "run")
        assert first is not None
        assert "late.py" not in first.imported_by
        conn.execute(
            "INSERT INTO ast_imports(file_path,language,module_path,is_relative,"
            "local_name,alias_of,line) VALUES ('late.py','python','mod',0,'run','',1)"
        )
        conn.commit()
        second = query_pulse(conn, "mod.py", "run")
        assert second is not None
        assert "late.py" in second.imported_by
    finally:
        cache.close()
