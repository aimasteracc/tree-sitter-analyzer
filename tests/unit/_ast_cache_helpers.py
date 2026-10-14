"""#1376：_ast_cache_helpers 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import os
import sqlite3
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.ast_cache import (
    ASTCache,
)
from tree_sitter_analyzer.indexing_snapshot import (
    IndexCandidateSnapshot,
    build_index_candidate_snapshot,
)

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")


_BACKFILL_ROUTES = (
    ("backfill_cross_file_edges", "cross_file_backfill"),
    ("_run_synapse_backfill", "synapse_backfill"),
    ("_run_unresolved_refs_backfill", "unresolved_refs_backfill"),
)


@pytest.fixture
def tmp_project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text(
        "def hello():\n    print('hello')\n\nclass Foo:\n    pass\n", encoding="utf-8"
    )
    (src / "util.js").write_text(
        "function add(a, b) { return a + b; }\n", encoding="utf-8"
    )
    (src / "readme.md").write_text("# Readme\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def cache(tmp_project):
    c = ASTCache(str(tmp_project))
    yield c
    c.close()


def engine_cache(root) -> ASTCache:
    """直接驱动原地写引擎：默认定位符已改经版本存储写入（#1554）。

    与版本路由的私有构建库一致：自定义库路径，并作为项目索引待发布。
    """
    built = ASTCache(
        str(root), db_path=os.path.join(str(root), ".ast-cache", "build", "index.db")
    )
    built._publishes_project_index = True
    return built


def legacy_cache(root, db_path=None) -> ASTCache:
    """原地写旧 ``.ast-cache/index.db`` 的缓存，供依赖旧库原地写入的测试构造状态。

    #1554 起生产默认路由不再原地写旧库；此处显式关闭版本路由，以便继续验证
    遗留旧库上的目录固定、镜像隔离、快照读取，以及直接读写旧库的测试夹具。
    其他自定义 ``db_path`` 原样交给 ``ASTCache``（自定义路径本就原地写）。
    """
    real_root = os.path.realpath(os.path.abspath(str(root)))
    legacy = os.path.join(real_root, ".ast-cache", "index.db")
    if (
        db_path is not None
        and os.path.realpath(os.path.abspath(str(db_path))) != legacy
    ):
        return ASTCache(str(root), db_path=str(db_path))
    os.makedirs(os.path.dirname(legacy), exist_ok=True)
    sqlite3.connect(legacy).close()
    built = ASTCache(str(root))
    built._generation_managed = False
    return built


def write_legacy_index(built: ASTCache) -> None:
    """把引擎库整库备份到旧 ``.ast-cache/index.db``，模拟首次发布前遗留的旧库。"""
    target = sqlite3.connect(os.path.join(built.project_root, ".ast-cache", "index.db"))
    try:
        built.get_conn().backup(target)
    finally:
        target.close()


@pytest.fixture
def engine(tmp_project):
    c = engine_cache(tmp_project)
    yield c
    c.close()


def _query_plan(conn: sqlite3.Connection, sql: str, params: tuple[str, ...]) -> str:
    rows = conn.execute(f"EXPLAIN QUERY PLAN {sql}", params).fetchall()
    return " ".join(str(row[3]) for row in rows)


def _python_language(path: str) -> str | None:
    return "python" if path.endswith(".py") else None


def _snapshot(tmp_path, path) -> IndexCandidateSnapshot:
    return build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(path),),
        language_fn=_python_language,
    )


def _run_backfill_with_route_result(cache, monkeypatch, route, result):
    from tree_sitter_analyzer.cache.indexer import post_index_backfill

    for method, _key in _BACKFILL_ROUTES:
        monkeypatch.setattr(cache, method, lambda: {"errors": 0})
    monkeypatch.setattr(cache, route, lambda: result)
    stats = {}
    with patch(
        "tree_sitter_analyzer.cache.unresolved.mark_resolution_converged"
    ) as converged:
        post_index_backfill(cache, stats)
    return stats, converged


# ---------------------------------------------------------------------------
# kind=method 分类；RED-first，参见 feature/kind-method-classification。
# ---------------------------------------------------------------------------


@pytest.fixture
def method_project(tmp_path):
    """包含一个类方法和一个顶层函数的最小 Python 项目。"""
    src = tmp_path / "src"
    src.mkdir()
    (src / "animals.py").write_text(
        "class Dog:\n"
        "    def bark(self):\n"
        "        return 'woof'\n"
        "\n"
        "def standalone():\n"
        "    pass\n",
        encoding="utf-8",
    )
    return tmp_path


def _cache_storage_bytes(project_root) -> dict[str, bytes]:
    cache_dir = project_root / ".ast-cache"
    return {
        path.name: path.read_bytes()
        for path in sorted(cache_dir.iterdir())
        if path.is_file()
    }


# 索引器所有权边界用例集中在既有 cache 测试体系中。
class _CacheRoot:
    def __init__(self, project_root: str) -> None:
        self.project_root = project_root


class _OsProxy:
    def __init__(self, **overrides) -> None:
        self._overrides = overrides

    def __getattr__(self, name):
        return self._overrides.get(name, getattr(os, name))
