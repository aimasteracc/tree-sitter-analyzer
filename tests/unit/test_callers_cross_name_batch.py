"""RFC-0041 跨名批量：查询作用域内为全部名字共享一次的工作，逐输入答复不变。

每项共享工作都对照它所替代的逐名计算：改名导入的分桶、ES 改名边的连接查询、
词表的拼接查找、stat 记忆、装饰器定义表、成本档位探测；最后在一个混合了这些
机制的真实索引上，批量答复与单次调用逐字节相同。
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer import query_scope as qs
from tree_sitter_analyzer.graph import alias_edges
from tree_sitter_analyzer.mcp.tools import callers_decorators
from tree_sitter_analyzer.mcp.tools.reference_vocab import (
    _JoinedVocab,
    searchable,
    vocabulary,
)

# --------------------------------------------------------------------------- #
# 改名导入与 ES 改名边
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _fresh_join_memo() -> None:
    # 连接顺序的进程内记忆按两张表的最大 rowid 记键；各测试的小库键相同。
    alias_edges._JOIN_MEMO.clear()


def _alias_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE ast_imports (file_path TEXT, local_name TEXT, language TEXT,"
        " alias_of TEXT, is_star INTEGER);"
        "CREATE TABLE edges (id INTEGER PRIMARY KEY, kind TEXT, callee_name TEXT,"
        " file_path TEXT, metadata TEXT, source_node_id TEXT DEFAULT '',"
        " target_node_id TEXT DEFAULT '', line INTEGER DEFAULT 0);"
    )
    imports = [
        ("a.py", "g", "python", "f", 0),
        ("b.py", "h", "python", "f", 0),
        ("c.py", "g", "python", "f", 0),  # 同一本地名的第二个文件
        ("d.py", "f", "python", "f", 0),  # 原样导入：不算改名
        ("e.py", "k", "python", "f", 1),  # 星号导入除外
        ("f.py", "m", "python", None, 0),
        ("g.ts", "makeSig", "typescript", None, 0),
        ("h.ts", "sign", "typescript", None, 0),
        ("i.ts", "signer", "typescript", None, 0),
    ]
    conn.executemany("INSERT INTO ast_imports VALUES (?, ?, ?, ?, ?)", imports)

    def alias(local: str, name: str) -> str:
        return json.dumps({"import_alias": {"local": local, "name": name}})

    # 行号刻意乱序插入：两条路径都须按 id 递增返回。
    edges = [
        (9, "calls", "sign", "h.ts", alias("sign", "signer")),
        (3, "calls", "makeSig", "g.ts", alias("makeSig", "signer")),
        (5, "calls", "makeSig", "g.ts", alias("makeSig", "other")),
        (7, "calls", "signer", "i.ts", alias("signer", "signer")),
        (4, "imports", "makeSig", "g.ts", alias("makeSig", "signer")),
    ]
    conn.executemany(
        "INSERT INTO edges (id, kind, callee_name, file_path, metadata) "
        "VALUES (?, ?, ?, ?, ?)",
        edges,
    )
    conn.commit()
    return conn


@pytest.mark.parametrize("name", ["f", "m", "nope", "signer"])
def test_scoped_alias_local_names_equal_the_per_name_query(
    tmp_path: Path, name: str
) -> None:
    conn = _alias_db(tmp_path / "index.db")
    live = alias_edges._alias_local_names(conn, name)
    with qs.query_scope():
        bucketed = alias_edges._alias_local_names(conn, name)
    assert bucketed == live
    assert alias_edges._alias_local_names(conn, "f") == ["g", "h"]


@pytest.mark.parametrize("name", ["signer", "other", "nope"])
def test_es_alias_rows_are_in_id_order_in_and_out_of_scope(
    tmp_path: Path, name: str
) -> None:
    conn = _alias_db(tmp_path / "index.db")
    live = [row["id"] for row in alias_edges._es_alias_rows(conn, name)]
    with qs.query_scope():
        bucketed = [row["id"] for row in alias_edges._es_alias_rows(conn, name)]
    assert bucketed == live
    if name == "signer":
        assert live == [3, 9]


def test_alias_buckets_are_read_once_per_scope(tmp_path: Path) -> None:
    conn = _alias_db(tmp_path / "index.db")
    statements: list[str] = []
    conn.set_trace_callback(statements.append)
    with qs.query_scope():
        for name in ("f", "m", "nope", "signer", "other"):
            alias_edges.alias_call_rows(conn, name)
    bucket_reads = [s for s in statements if "alias_of IS NOT NULL" in s]
    es_reads = [s for s in statements if "'\"import_alias\"') > 0" in s]
    join_choices = [s for s in statements if s.startswith("SELECT COUNT(*) FROM ast_")]
    assert (len(bucket_reads), len(es_reads), len(join_choices)) == (1, 1, 1)


@pytest.mark.parametrize("join", ["default", "cross"])
@pytest.mark.parametrize("name", ["signer", "other"])
def test_both_join_orders_return_the_same_rows_in_id_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, join: str, name: str
) -> None:
    conn = _alias_db(tmp_path / "index.db")
    expected = {"signer": [3, 9], "other": [5]}[name]
    monkeypatch.setattr(alias_edges, "_es_join", lambda _conn: join)
    live = [row["id"] for row in alias_edges._es_alias_rows(conn, name)]
    with qs.query_scope():
        bucketed = [row["id"] for row in alias_edges._es_alias_rows(conn, name)]
    assert (live, bucketed) == (expected, expected)


def test_join_order_follows_the_edges_each_plan_reads(tmp_path: Path) -> None:
    # 同名候选边（4）不少于调用边（4）：默认计划；再加一批无关调用边后改由导入行驱动。
    conn = _alias_db(tmp_path / "index.db")
    assert alias_edges._es_join(conn) == "default"
    conn.executemany(
        "INSERT INTO edges (id, kind, callee_name, file_path, metadata) "
        "VALUES (?, 'calls', 'unrelated', 'z.py', NULL)",
        [(100 + i,) for i in range(10)],
    )
    conn.commit()
    assert alias_edges._es_join(conn) == "cross"  # 最大 rowid 变了：重新计数


def test_join_choice_is_remembered_while_the_database_is_unchanged(
    tmp_path: Path,
) -> None:
    conn = _alias_db(tmp_path / "index.db")
    statements: list[str] = []
    conn.set_trace_callback(statements.append)
    choices = {alias_edges._es_join(conn) for _ in range(3)}
    counts = [s for s in statements if s.startswith("SELECT COUNT(*)")]
    assert (choices, len(counts)) == ({"default"}, 2)


# --------------------------------------------------------------------------- #
# 词表：拼接段查找 == 逐文件包含测试
# --------------------------------------------------------------------------- #

_WORDS = st.text(alphabet="ab_$1é", min_size=0, max_size=6)


@settings(
    # 单测每项 8 s 预算（tests/conftest.py）：长会话里 200 个样例曾超时，60 个约 1 s。
    max_examples=60,
    deadline=None,
    database=None,
    # 纯内存比较；CI / xdist 负载下样例生成可能变慢，那不是被测行为。
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    files=st.lists(st.lists(_WORDS, max_size=6), max_size=8),
    needle=st.text(alphabet="ab_$1é", min_size=1, max_size=4),
)
def test_joined_vocabulary_agrees_with_per_file_containment(
    files: list[list[str]], needle: str
) -> None:
    known = [
        (f"f{i}.py", vocabulary(" ".join(words).encode("utf-8")))
        for i, words in enumerate(files)
    ]
    raw = needle.encode("utf-8")
    assert searchable(raw)
    expected = {path for path, words in known if raw not in words}
    assert _JoinedVocab(known).lacking(raw) == expected


# --------------------------------------------------------------------------- #
# stat 记忆
# --------------------------------------------------------------------------- #


def _counting_stat(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    real = os.stat

    def counting(path, *args, **kwargs):
        calls.append(str(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(qs.os, "stat", counting)
    return calls


def test_scoped_stats_stat_each_path_once_per_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = []
    for i in range(qs._PARALLEL_STAT_MIN + 6):
        path = tmp_path / f"f{i}.py"
        path.write_text("x")
        paths.append(str(path))
    missing = str(tmp_path / "missing.py")
    calls = _counting_stat(monkeypatch)
    with qs.query_scope():
        first = qs.scoped_stats([*paths, missing])
        again = qs.scoped_stats([missing, paths[0]])
    assert len(calls) == len(paths) + 1
    assert (first[-1], again[0], again[1].st_size) == (None, None, 1)


def test_unscoped_stats_are_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "f.py"
    path.write_text("x")
    calls = _counting_stat(monkeypatch)
    qs.scoped_stats([str(path)])
    path.write_text("xyz")
    sizes = [info.st_size for info in qs.scoped_stats([str(path)])]
    assert (len(calls), sizes) == (2, [3])


# --------------------------------------------------------------------------- #
# 装饰器定义表
# --------------------------------------------------------------------------- #

_DECORATED = (
    "import functools\n"
    "from app import registry\n\n\n"
    "@registry.register\n"
    "@functools.lru_cache(maxsize=2)\n"
    "def handler():\n"
    "    return 1\n\n\n"
    "class Box:\n"
    "    @property\n"
    "    def size(self):\n"
    "        return 2\n\n"
    "    @staticmethod\n"
    "    def make():\n"
    "        @registry.inner\n"
    "        def nested():\n"
    "            return 3\n"
    "        return nested\n"
)


@pytest.mark.parametrize("line", [5, 6, 7, 8, 11, 12, 13, 15, 16, 17, 18, 99])
def test_scoped_decorator_lookup_equals_the_live_walk(line: int) -> None:
    live = callers_decorators._python_decorators(_DECORATED, line)
    with qs.query_scope():
        callers_decorators._python_decorators(_DECORATED, 1)  # 先建表
        scoped = callers_decorators._python_decorators(_DECORATED, line)
    assert scoped == live


def test_decorator_lookup_names_every_decorator_of_the_definition() -> None:
    found = callers_decorators._python_decorators(_DECORATED, 7)
    assert [d.text for d in found or []] == [
        "@registry.register",
        "@functools.lru_cache(maxsize=2)",
    ]


# --------------------------------------------------------------------------- #
# 成本档位：作用域内探测一次
# --------------------------------------------------------------------------- #


def test_index_holds_rows_is_probed_once_per_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tree_sitter_analyzer.cache import query_cost

    calls: list[str] = []

    def probe(root: str) -> bool:
        calls.append(root)
        return True

    monkeypatch.setattr(query_cost, "_live_index_holds_rows", probe)
    with qs.query_scope():
        inside = [query_cost._index_holds_rows("r") for _ in range(3)]
    outside = [query_cost._index_holds_rows("r") for _ in range(2)]
    assert (inside, outside, len(calls)) == ([True] * 3, [True] * 2, 3)


# --------------------------------------------------------------------------- #
# 端到端：混合机制的批量答复 == 单次调用
# --------------------------------------------------------------------------- #

_PROJECT = {
    "pkg/__init__.py": "",
    "pkg/core.py": (
        "import functools\n\n\n"
        "def target(x):\n"
        "    return x + 1\n\n\n"
        "@functools.lru_cache(maxsize=None)\n"
        "def cached(x):\n"
        "    return target(x)\n\n\n"
        "class Box:\n"
        "    @property\n"
        "    def size(self):\n"
        "        return target(2)\n\n"
        "    def grow(self):\n"
        "        return self.size + helper()\n\n\n"
        "def helper():\n"
        "    return 3\n\n\n"
        "def unused():\n"
        "    return 0\n"
    ),
    "pkg/use.py": (
        "from pkg.core import target as t, helper\n"
        "from pkg import core\n\n\n"
        "def use():\n"
        "    return t(1) + helper() + core.cached(2)\n\n\n"
        "HANDLERS = {'h': helper}\n"
    ),
    "web/sig.ts": ("export function signer(x: number): number {\n  return x;\n}\n"),
    "web/use.ts": (
        "import makeSig from './sig';\n"
        "import { signer as sign } from './sig';\n\n"
        "export function go(): number {\n  return makeSig(1) + sign(2);\n}\n"
    ),
    "tests/test_core.py": (
        "from pkg.core import cached, target\n\n\n"
        "def test_target():\n"
        "    assert target(1) == 2\n\n\n"
        "def test_cached():\n"
        "    assert cached(1) == 2\n"
    ),
}

_NAMES = (
    ("target", "pkg/core.py"),
    ("target", None),
    ("cached", "pkg/core.py"),
    ("Box.size", "pkg/core.py"),
    ("size", None),
    ("Box.grow", None),
    ("helper", "pkg/core.py"),
    ("unused", None),
    ("signer", "web/sig.ts"),
    ("go", None),
    ("use", None),
    ("missing_name", None),
)


def _without_timing(response: dict) -> dict:
    return {key: value for key, value in response.items() if "elapsed" not in key}


@pytest.fixture
async def mixed_root(tmp_path: Path) -> Path:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    root = tmp_path / "proj"
    for rel, body in _PROJECT.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True
    old = 1_600_000_000
    for path in root.rglob("*"):
        if path.is_file() and ".ast-cache" not in path.parts:
            os.utime(path, (old, old))
    return root


def _requests() -> list[dict]:
    requests = []
    for name, file in _NAMES:
        args = {"function_name": name, "include_bodies": False, "limit": 500}
        if file:
            args["file_path"] = file
        requests.append(args)
    return requests


@pytest.mark.asyncio
async def test_cross_name_batch_answers_equal_single_answers(mixed_root: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    tool = CodeGraphCallersTool(str(mixed_root))
    single = [await tool.execute(dict(args)) for args in _requests()]
    with qs.query_scope():
        batched = await tool.execute_batch(_requests())
    assert [_without_timing(r) for r in batched] == [_without_timing(r) for r in single]
    # 夹具确实覆盖了这些机制：改名导入的调用方被列出。
    target = single[0]
    assert "pkg/use.py" in {c["file"] for c in target["callers"]}
