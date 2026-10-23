"""#1749：修补出的解析上下文必须与同一索引上的全量构建逐项相同。

做法：在编辑前的已发布索引上全量构建上下文（并载入惰性的类方法表与注解索引），
记为"上一份"；编辑并真实刷新后，在新索引上走复用路径修补，再与同一新索引上的
全量构建逐字段比较。文件集合变化时必须回退全量（``reuse`` 返回 None）。
"""

from __future__ import annotations

import dataclasses
import os

import pytest

from tests.unit.test_refresh_equivalence_1671 import _index_project, _sync

_FILES = {
    "pkg/__init__.py": "",
    "pkg/base.py": (
        "class Helper:\n"
        "    def assist(self) -> int:\n"
        "        return 1\n\n\n"
        "class Base:\n"
        "    def run(self) -> Helper:\n"
        "        return Helper()\n\n\n"
        "def helper() -> int:\n"
        "    return 1\n"
    ),
    "pkg/util.py": "from .base import *\n\n\ndef util():\n    return helper()\n",
    "pkg/api.py": (
        "from pkg.base import Base as B\n"
        "import pkg.util as u\n\n"
        "shared: B = B()\n\n\n"
        "class Api(B):\n"
        "    def go(self):\n"
        "        return u.util() + self.run().assist()\n"
    ),
    "app.py": "from pkg.api import Api\n\n\ndef main():\n    return Api().go()\n",
}

_BASE = _FILES["pkg/base.py"]
#: 文件集合不变的编辑：(文件, 新内容)。
_EDITS = {
    "body_edit": ("pkg/base.py", _BASE.replace("return 1\n", "return 2\n")),
    "add_function": (
        "pkg/base.py",
        _BASE + "\n\ndef extra() -> Base:\n    return Base()\n",
    ),
    "remove_function": ("pkg/base.py", _BASE.split("\n\n\ndef helper")[0] + "\n"),
    "add_method": (
        "pkg/base.py",
        _BASE.replace(
            "        return Helper()\n",
            "        return Helper()\n\n    def stop(self) -> None:\n        return None\n",
        ),
    ),
    "rename_class": ("pkg/base.py", _BASE.replace("Helper", "Assistant")),
    "change_imports": (
        "pkg/api.py",
        _FILES["pkg/api.py"].replace(
            "import pkg.util as u", "from pkg import util as u"
        ),
    ),
    "edit_importer": (
        "app.py",
        _FILES["app.py"] + "\n\ndef other():\n    return main()\n",
    ),
    # 文件失去全部符号：``file_symbols`` 的键集合变化，须按路径重排（与全量相同）。
    "loses_all_symbols": ("app.py", "VALUE = 1\n"),
}


@pytest.fixture
def root(tmp_path):
    from tree_sitter_analyzer.mcp.utils import auto_index_guard
    from tree_sitter_analyzer.synapse_resolver import _context_reuse
    from tree_sitter_analyzer.synapse_resolver._context import (
        clear_resolver_context_cache,
    )

    project = tmp_path / "project"
    for name, text in _FILES.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    auto_index_guard.reset()
    clear_resolver_context_cache()
    _context_reuse.forget_all()
    yield str(project)
    clear_resolver_context_cache()
    _context_reuse.forget_all()
    auto_index_guard.reset()


def _write(root: str, name: str, text: str) -> None:
    path = os.path.join(root, name)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(text)
    info = os.stat(path)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))


def _loaded_context(cache):
    """全量构建并载入全部惰性部分（类方法表、方法索引、注解索引）。"""
    from tree_sitter_analyzer.synapse_resolver._annotated import annotation_index
    from tree_sitter_analyzer.synapse_resolver._context import (
        _build_resolver_context_uncached,
    )

    ctx = _build_resolver_context_uncached(cache)
    _ = ctx.file_class_methods, ctx.class_method_index
    annotation_index(ctx)
    return ctx


def _ordered(mapping: dict) -> list:
    return list(mapping.items())


def _fields(state, ctx) -> dict:
    """比较用的全部字段；键顺序有意义的映射按 items 列表比较。"""
    from tree_sitter_analyzer.synapse_resolver._annotated import annotation_index

    resolver = ctx.callee_resolver
    annotations = annotation_index(ctx)
    out = {
        f.name: getattr(state, f.name)
        for f in dataclasses.fields(state)
        if f.name != "evidence"
    }
    out |= {
        "file_symbols_order": _ordered(state.file_symbols),
        "imports_order": _ordered(state.imports_by_file),
        "file_languages_order": _ordered(state.file_languages),
        "file_class_methods": ctx.file_class_methods,
        "class_method_index": ctx.class_method_index,
        "unique_method_index": ctx.unique_method_index,
        "method_symbol_ids": ctx.method_symbol_ids,
        "project_class_names": ctx.project_class_names,
        "resolver_by_name": resolver._functions_by_name,
        "resolver_by_file": resolver._functions_by_file,
        "resolver_sources": resolver._name_to_source,
        "annotations": dataclasses.asdict(annotations),
    }
    return out


def _patched_and_full(root: str, edit, edited: str) -> tuple[dict, dict]:
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.synapse_resolver import _context_reuse
    from tree_sitter_analyzer.synapse_resolver._context import (
        ResolverContext,
        read_context_state,
    )

    _index_project(root)
    before = ASTCache(root)
    try:
        old_ctx = _loaded_context(before)
        old = _context_reuse._LAST[_context_reuse._project_key(before)]
        assert old[2] is old_ctx
    finally:
        before.close()

    edit(root)
    _sync(root)
    after = ASTCache(root)
    try:
        with _context_reuse._LOCK:
            _context_reuse._LAST[_context_reuse._project_key(after)] = old
        patched_ctx = _context_reuse.reuse(after)
        # 文件集合不变：必须走修补路径，得到新的上下文对象。
        assert isinstance(patched_ctx, ResolverContext)
        assert patched_ctx is not old[2]
        patched_state = _context_reuse._LAST[_context_reuse._project_key(after)][1]
        assert patched_state is not old[1]
        # 编辑过的文件证据确实变了：比较的是一次真正的修补，而不是原样复用。
        assert patched_state.evidence[edited] != old[0][edited]
        patched = _fields(patched_state, patched_ctx)
        full_ctx = _loaded_context(after)
        full = _fields(read_context_state(after.get_conn()), full_ctx)
    finally:
        after.close()
    return patched, full


# slow_ok：每个用例做两次真实刷新并构建三份上下文。
@pytest.mark.slow_ok
@pytest.mark.parametrize("kind", sorted(_EDITS))
def test_a_patched_context_equals_a_full_build(root, kind) -> None:
    name, text = _EDITS[kind]
    patched, full = _patched_and_full(root, lambda r: _write(r, name, text), name)

    differing = sorted(key for key in full if patched[key] != full[key])
    assert differing == []
    assert full["file_symbols"]  # 比较的不是空上下文


@pytest.mark.slow_ok
@pytest.mark.parametrize("change", ["add_file", "delete_file"])
def test_a_changed_file_set_rebuilds_in_full(root, change) -> None:
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.synapse_resolver import _context_reuse

    _index_project(root)
    before = ASTCache(root)
    try:
        _loaded_context(before)
        old = _context_reuse._LAST[_context_reuse._project_key(before)]
    finally:
        before.close()
    if change == "add_file":
        _write(root, "pkg/extra.py", "def more():\n    return 1\n")
    else:
        os.remove(os.path.join(root, "app.py"))
    _sync(root)
    after = ASTCache(root)
    try:
        with _context_reuse._LOCK:
            _context_reuse._LAST[_context_reuse._project_key(after)] = old
        assert _context_reuse.reuse(after) is None
    finally:
        after.close()


@pytest.mark.slow_ok
def test_reuse_can_be_switched_off(root, monkeypatch) -> None:
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.synapse_resolver import _context_reuse

    _index_project(root)
    cache = ASTCache(root)
    try:
        _loaded_context(cache)
        monkeypatch.setenv("TSA_RESOLVER_CONTEXT_REUSE", "0")
        assert _context_reuse.reuse(cache) is None
    finally:
        cache.close()


@pytest.mark.slow_ok
def test_unchanged_content_reuses_every_loaded_part(root) -> None:
    """证据完全相同（如另一个数据库连接读同一版本）：直接沿用，惰性部分照搬。"""
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.synapse_resolver import _context_reuse
    from tree_sitter_analyzer.synapse_resolver._context import read_context_state

    _index_project(root)
    cache = ASTCache(root)
    try:
        old_ctx = _loaded_context(cache)
        reused = _context_reuse.reuse(cache)
        assert reused is not None and reused is not old_ctx
        assert reused._file_class_methods_loaded
        state = _context_reuse._LAST[_context_reuse._project_key(cache)][1]
        full = _fields(read_context_state(cache.get_conn()), old_ctx)
        assert _fields(state, reused) == full
    finally:
        cache.close()


@pytest.mark.slow_ok
@pytest.mark.parametrize("failure", ["database_error", "patch_declined"])
def test_a_failed_patch_falls_back_to_a_full_build(root, monkeypatch, failure) -> None:
    import sqlite3

    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.synapse_resolver import _context, _context_reuse

    _index_project(root)
    before = ASTCache(root)
    try:
        _loaded_context(before)
        old = _context_reuse._LAST[_context_reuse._project_key(before)]
    finally:
        before.close()
    _write(root, "pkg/base.py", _BASE.replace("return 1\n", "return 3\n"))
    _sync(root)

    def declined(*_args, **_kwargs):
        if failure == "database_error":
            raise sqlite3.OperationalError("database is locked")
        return None

    monkeypatch.setattr(_context, "patch_context_state", declined)
    after = ASTCache(root)
    try:
        with _context_reuse._LOCK:
            _context_reuse._LAST[_context_reuse._project_key(after)] = old
        assert _context_reuse.reuse(after) is None
        # 记住的状态不被失败的修补替换。
        assert _context_reuse._LAST[_context_reuse._project_key(after)] is old
    finally:
        after.close()


def test_a_disabled_or_unreadable_reuse_stays_out_of_the_way(root, monkeypatch) -> None:
    import sqlite3

    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.synapse_resolver import _context_reuse

    _index_project(root)
    cache = ASTCache(root)
    try:
        monkeypatch.setenv("TSA_RESOLVER_CONTEXT_REUSE", "off")
        _context_reuse.forget_all()  # 索引时已记住的状态先清掉
        _loaded_context(cache)
        assert _context_reuse._LAST == {}  # 关闭时不记住
        monkeypatch.delenv("TSA_RESOLVER_CONTEXT_REUSE")
        _loaded_context(cache)
        assert len(_context_reuse._LAST) == 1

        def unreadable(_conn):
            raise sqlite3.OperationalError("no such column: extractor_version")

        monkeypatch.setattr(_context_reuse, "read_evidence", unreadable)
        assert _context_reuse.reuse(cache) is None
    finally:
        cache.close()


def _memory_state(conn):
    from tree_sitter_analyzer.synapse_resolver._context import read_context_state

    return read_context_state(conn)


def test_missing_tables_read_as_empty_and_never_reuse() -> None:
    import sqlite3

    conn = sqlite3.connect(":memory:")
    state = _memory_state(conn)
    assert (state.evidence, state.file_paths, state.file_symbols) == (None, [], {})
    # 旧表结构（无 extractor_version）：仍按 ast_index 读出文件，但证据不可用。
    conn.execute("CREATE TABLE ast_index (file_path TEXT, language TEXT)")
    conn.execute("INSERT INTO ast_index VALUES ('a.py', 'python')")
    state = _memory_state(conn)
    assert state.evidence is None
    assert state.file_languages == {"a.py": "python"}


def test_symbol_rows_without_an_index_row_still_enter_the_evidence() -> None:
    import sqlite3

    from tree_sitter_analyzer.synapse_resolver._context_inputs import read_evidence

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, language TEXT, "
        "content_hash TEXT, extractor_version INTEGER)"
    )
    conn.execute(
        "CREATE TABLE ast_symbol_rows (id INTEGER PRIMARY KEY, name TEXT, "
        "kind TEXT, file_path TEXT, line INTEGER)"
    )
    conn.execute("CREATE TABLE ast_imports (id INTEGER PRIMARY KEY, file_path TEXT)")
    conn.execute("INSERT INTO ast_index VALUES ('a.py', 'python', 'h', 1)")
    conn.execute("INSERT INTO ast_symbol_rows VALUES (7, 'f', 'function', 'b.py', 1)")
    evidence, ordered = read_evidence(conn)
    assert ordered == [("a.py", "python")]
    assert evidence["b.py"] == (None, None, None, None, (1, 7, 7), None)


def test_a_changed_module_map_declines_the_patch() -> None:
    import dataclasses
    import sqlite3

    from tree_sitter_analyzer.synapse_resolver._context_inputs import patch_state

    conn = sqlite3.connect(":memory:")
    old = dataclasses.replace(_memory_state(conn), module_to_file={"a": "a.py"})
    declined = patch_state(
        conn,
        old,
        {"a.py": ()},
        [("a.py", "python")],
        {"a.py"},
        module_map=lambda _paths: {"a": "a/__init__.py"},
        import_maps=lambda *_args: ({}, {}),
        star_target=lambda *_args: "",
    )
    assert declined is None


def test_an_unreadable_scoped_edge_read_falls_back_to_the_full_read() -> None:
    """#1749：范围内读边失败时返回 None，交叉文件阶段改为读取全部调用边（旧行为）。"""
    import sqlite3

    from tree_sitter_analyzer.cache.backfill_scope import BackfillScope
    from tree_sitter_analyzer.cache.query import _scoped_call_edges

    conn = sqlite3.connect(":memory:")  # 没有 edges 表
    scope = BackfillScope(frozenset({"a.py"}), frozenset({"f"}), frozenset())
    assert _scoped_call_edges(conn, scope) is None
