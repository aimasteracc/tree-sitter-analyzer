"""#1735：有稳定失败（缺少可选语法）的检出上，范围回填（#1696）同样武装。

稳定失败的文件不写行，调用图标记按设计保持撤销（#1671），``writer_marker_is_current``
因而永远为假，``backfill_scope.begin`` 每次都撤销武装：每次刷新都全量回填。
本仓库在没有 swift / lua 语法的机器上（常见的用户环境）就是这样。

规则（与发布、监视器 #1733 相同的 ``stable_failures_only`` 判定）：上一轮是一次收敛
的完整刷新、唯一的失败是已记录的稳定失败（#1671 的收敛记录）时，照常武装；其余
任何“标记不是当前”的状态都不武装。等价门：刷新后的规范化转储等于全新重建。
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit._index_canonical_dump import canonical_dump, dump_differences
from tests.unit.test_scoped_backfill_1696 import _FILES, _edit

_REASON = 'Swift grammar not installed — pip install "tree-sitter-analyzer[swift]"'
_BROKEN = "def broken():\n    return 4\n"


@pytest.fixture
def root(tmp_path, monkeypatch):
    from tree_sitter_analyzer.core.parser import Parser
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    project = tmp_path / "project"
    for name, text in {**_FILES, "broken.py": _BROKEN}.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    original = Parser.parse_code

    def parse_code(self, source_code, language, filename=None, *args, **kwargs):
        if filename is not None and os.path.basename(filename) == "broken.py":
            return SimpleNamespace(success=False, error_message=_REASON)
        return original(self, source_code, language, filename, *args, **kwargs)

    monkeypatch.setattr(Parser, "parse_code", parse_code)
    auto_index_guard.reset()
    yield project
    auto_index_guard.reset()


def _sync(root):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.incremental_sync import IncrementalSync
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    scope = make_source_scope_descriptor()
    cache = ASTCache(str(root))
    try:
        result = IncrementalSync(cache).sync(
            max_files=scope.certification_max_files,
            exclude_patterns=scope.effective_excludes,
            source_scope=scope,
        )
    finally:
        cache.close()
    return result.backfill_scope


def _index_project(root):
    from tree_sitter_analyzer.ast_cache import ASTCache

    cache = ASTCache(str(root))
    try:
        result = cache.index_project(workers=0)
    finally:
        cache.close()
    return result.get("backfill_scope") or (result.get("stats") or {}).get(
        "backfill_scope"
    )


_ROUTES = {"sync": _sync, "index_project": _index_project}


def _dump(root):
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    location = resolve_index_location(str(root))
    assert location.published is True
    return canonical_dump(location.path)


def _wipe_index(root) -> None:
    cache = os.path.join(root, ".ast-cache")
    for directory, _dirs, files in os.walk(cache):
        for name in files:
            os.chmod(os.path.join(directory, name), stat.S_IWRITE | stat.S_IREAD)
    shutil.rmtree(cache)


# slow_ok：每个用例做三次真实刷新与一次全新重建，并转储两份完整索引。
@pytest.mark.slow_ok
@pytest.mark.parametrize("route", sorted(_ROUTES))
@pytest.mark.parametrize("edit", ["body_only", "signature", "import_alias"])
def test_stable_failures_do_not_disarm_the_scoped_backfill(
    root, route: str, edit: str
) -> None:
    refresh = _ROUTES[route]
    refresh(root)
    refresh(root)
    _edit(root, edit)

    decision = refresh(root)
    refreshed = _dump(root)
    _wipe_index(root)
    refresh(root)
    rebuilt = _dump(root)

    assert decision["mode"] == "scoped", decision
    assert dump_differences(refreshed, rebuilt) == {}


def _record_conn(record: dict | None, tmp_path) -> sqlite3.Connection:
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import stable_failures

    database = tmp_path / f"index-{len(list(tmp_path.iterdir()))}.db"
    cache = ASTCache(str(tmp_path), str(database))
    cache.get_conn()
    cache.close()
    conn = sqlite3.connect(database)
    if record is not None:
        conn.execute(
            "INSERT INTO ast_cache_metadata VALUES (?, ?)",
            (stable_failures.RECORD_KEY, json.dumps(record)),
        )
    return conn


def _record(**overrides) -> dict:
    from tree_sitter_analyzer.cache import stable_failures
    from tree_sitter_analyzer.cache.callgraph_state import CALL_GRAPH_PIPELINE_VERSION

    base = {
        "version": stable_failures.RECORD_VERSION,
        "root": "/repo",
        "scope": "scope",
        "extractor_version": stable_failures.current_extractor_version(),
        "pipeline_version": CALL_GRAPH_PIPELINE_VERSION,
        "failures": [["broken.py", "a" * 64, "x"]],
    }
    return {**base, **overrides}


def _armed(conn: sqlite3.Connection) -> bool:
    from tree_sitter_analyzer.cache import backfill_scope

    backfill_scope.begin(conn)
    return backfill_scope._armed(conn)


def test_only_a_converged_record_with_stable_failures_arms(tmp_path) -> None:
    from tree_sitter_analyzer.cache.callgraph_state import CALL_GRAPH_PIPELINE_VERSION

    assert _armed(_record_conn(_record(), tmp_path)) is True
    # 其余“标记不是当前”的状态都不武装：没有记录、记录没有失败（应有当前标记）、
    # 记录属于别的调用图流水线或提取器版本。
    assert _armed(_record_conn(None, tmp_path)) is False
    assert _armed(_record_conn(_record(failures=[]), tmp_path)) is False
    stale = _record(pipeline_version=CALL_GRAPH_PIPELINE_VERSION + 1)
    assert _armed(_record_conn(stale, tmp_path)) is False
    assert _armed(_record_conn(_record(extractor_version=1), tmp_path)) is False


def test_a_private_copy_arms_on_its_published_parent_record(tmp_path) -> None:
    from tree_sitter_analyzer.cache import backfill_scope, stable_failures

    parent = _record_conn(_record(), tmp_path)
    parent.commit()
    parent_path = Path(parent.execute("PRAGMA database_list").fetchone()[2])
    parent.close()
    copy = _record_conn(None, tmp_path)
    copy_path = Path(copy.execute("PRAGMA database_list").fetchone()[2])

    stable_failures.clear_record_at(copy_path)

    assert stable_failures.read_record(copy) is None  # 副本不继承记录
    backfill_scope.begin(copy, parent_path)
    assert backfill_scope._armed(copy) is True
    backfill_scope.begin(copy, None)
    assert backfill_scope._armed(copy) is False
    # 读不到父版本时不武装。
    backfill_scope.begin(copy, tmp_path / "missing.db")
    assert backfill_scope._armed(copy) is False


def test_published_parent_is_none_for_the_live_database(tmp_path) -> None:
    from tree_sitter_analyzer.cache.backfill_scope import published_parent

    class _Cache:
        project_root = str(tmp_path)
        db_path = str(tmp_path / "index.db")

    assert published_parent(_Cache()) is None  # 没有已发布版本
    assert published_parent(object()) is None
