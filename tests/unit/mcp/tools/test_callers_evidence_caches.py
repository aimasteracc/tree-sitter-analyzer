"""dogfood 第 7 轮：``nav callers`` 的证据缓存只能改变耗时，不能改变答案。

每个缓存都以能证明“输入未变”的证据为键（RFC-0030：绝不以“仅路径”判定为未变）：

* ``evidence_file_cache``：文件字节按 ``(size, mtime_ns, ctime_ns, ino, dev)``；
* ``project_walk_cache``：目录遍历按每个被列出目录与规则文件的 ``lstat``；
* ``relation_freshness.index_identity``：按库文件 / WAL 的 stat；
* ``query_cost._index_holds_rows``：按活动索引的行数与调用图状态；
* 认证快照：调用图标记不精确时注定无法认证，跳过捕获。

这里先证明每个缓存在输入变化时失效，再在真实索引上证明：命中缓存的答案与
清空缓存后重新计算的答案逐字段相同，编辑 / 新增文件后答案的变化也相同。
"""

from __future__ import annotations

import os
import sqlite3
import stat
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools import evidence_file_cache, project_walk_cache
from tree_sitter_analyzer.mcp.tools.evidence_file_cache import EvidenceFileCache
from tree_sitter_analyzer.mcp.tools.project_walk_cache import ProjectWalkCache

#: 回拨到一小时前：离开时间戳竞争窗口，缓存才会真正生效。
_AN_HOUR_NS = 3600 * 1_000_000_000


def _backdate(path: Path, offset_ns: int = _AN_HOUR_NS) -> None:
    stamp = time.time_ns() - offset_ns
    os.utime(path, ns=(stamp, stamp))


def _backdate_tree(root: Path) -> None:
    """回拨 ``root`` 下除索引目录外的全部文件与目录（自底向上）。"""
    for current, dirs, files in os.walk(root, topdown=False):
        if ".ast-cache" in Path(current).parts:
            continue
        for name in files:
            _backdate(Path(current) / name)
        for name in dirs:
            if name != ".ast-cache":
                _backdate(Path(current) / name)
    _backdate(root)


# --------------------------------------------------------------------------- #
# EvidenceFileCache
# --------------------------------------------------------------------------- #


def test_file_cache_reuses_bytes_while_stat_evidence_holds(tmp_path) -> None:
    target = tmp_path / "a.py"
    target.write_bytes(b"alpha\n")
    _backdate(target)
    cache = EvidenceFileCache()

    assert cache.read_bytes(str(target)) == b"alpha\n"
    assert len(cache) == 1
    assert cache.read_bytes(str(target)) == b"alpha\n"
    assert cache.total_bytes == len(b"alpha\n")


def test_file_cache_rereads_same_size_edit_with_new_mtime(tmp_path) -> None:
    target = tmp_path / "a.py"
    target.write_bytes(b"alpha\n")
    _backdate(target, 2 * _AN_HOUR_NS)
    cache = EvidenceFileCache()
    assert cache.read_bytes(str(target)) == b"alpha\n"

    # 大小不变、内容改变：只有 mtime（与 ctime）能证明它变了。
    target.write_bytes(b"omega\n")
    _backdate(target)

    assert cache.read_bytes(str(target)) == b"omega\n"


def test_file_cache_rereads_when_size_changes(tmp_path) -> None:
    target = tmp_path / "a.py"
    target.write_bytes(b"alpha\n")
    _backdate(target)
    cache = EvidenceFileCache()
    assert cache.read_bytes(str(target)) == b"alpha\n"

    target.write_bytes(b"alpha\nbeta\n")
    _backdate(target)

    assert cache.read_bytes(str(target)) == b"alpha\nbeta\n"


def test_file_cache_reports_a_vanished_file_as_unreadable(tmp_path) -> None:
    target = tmp_path / "a.py"
    target.write_bytes(b"alpha\n")
    _backdate(target)
    cache = EvidenceFileCache()
    assert cache.read_bytes(str(target)) == b"alpha\n"

    target.unlink()

    assert cache.read_bytes(str(target)) is None


def test_file_cache_never_caches_a_racy_file(tmp_path) -> None:
    # 刚写入的文件：同一时间戳刻度内的第二次写入不会改变元数据，必须每次重读。
    target = tmp_path / "a.py"
    target.write_bytes(b"alpha\n")
    cache = EvidenceFileCache()

    assert cache.read_bytes(str(target)) == b"alpha\n"
    assert len(cache) == 0


def test_file_cache_text_matches_text_mode_open(tmp_path) -> None:
    target = tmp_path / "a.py"
    target.write_bytes("x = 1\r\ny = 'é'\rz = 3\n\xff".encode("latin-1"))
    _backdate(target)
    cache = EvidenceFileCache()

    with open(target, encoding="utf-8", errors="replace") as handle:
        expected = handle.read()

    assert cache.read_text(str(target)) == expected
    assert cache.read_text(str(target)) == expected


def test_file_cache_is_bounded(tmp_path) -> None:
    cache = EvidenceFileCache(max_total_bytes=10, max_file_bytes=8)
    paths = []
    for index in range(3):
        target = tmp_path / f"f{index}.py"
        target.write_bytes(b"12345")
        _backdate(target)
        paths.append(str(target))
    big = tmp_path / "big.py"
    big.write_bytes(b"123456789")
    _backdate(big)

    for path in paths:
        assert cache.read_bytes(path) == b"12345"
    assert cache.read_bytes(str(big)) == b"123456789"

    assert cache.total_bytes <= 10
    assert len(cache) == 2


# --------------------------------------------------------------------------- #
# ProjectWalkCache
# --------------------------------------------------------------------------- #


def _counting_walker(root: Path, calls: list[int]):
    """遍历 ``root``（跳过点目录），记录被列出的目录，并统计调用次数。"""

    def walker(visited: list[str]) -> list[str]:
        calls.append(1)
        found: list[str] = []
        for current, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            relative = os.path.relpath(current, root)
            visited.append("" if relative == "." else relative)
            found.extend(os.path.join(current, name) for name in sorted(files))
        return found

    return walker


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "a.py").write_text("a\n")
    (root / "pkg" / "b.py").write_text("b\n")
    (root / ".gitignore").write_text("*.log\n")
    _backdate_tree(root)
    return root


def test_walk_cache_reuses_the_walk_while_directories_are_unchanged(tmp_path) -> None:
    root = _tree(tmp_path)
    calls: list[int] = []
    cache = ProjectWalkCache()
    walker = _counting_walker(root, calls)

    first = cache.walk(str(root), ("k",), "", walker)
    second = cache.walk(str(root), ("k",), "", walker)

    assert first == second
    assert len(calls) == 1


def test_walk_cache_rewalks_after_a_new_file_in_a_nested_directory(tmp_path) -> None:
    root = _tree(tmp_path)
    calls: list[int] = []
    cache = ProjectWalkCache()
    walker = _counting_walker(root, calls)
    cache.walk(str(root), ("k",), "", walker)

    (root / "pkg" / "c.py").write_text("c\n")
    result = cache.walk(str(root), ("k",), "", walker)

    assert str(root / "pkg" / "c.py") in result
    assert len(calls) == 2


def test_walk_cache_rewalks_after_a_removed_file(tmp_path) -> None:
    root = _tree(tmp_path)
    calls: list[int] = []
    cache = ProjectWalkCache()
    walker = _counting_walker(root, calls)
    cache.walk(str(root), ("k",), "", walker)

    (root / "a.py").unlink()
    result = cache.walk(str(root), ("k",), "", walker)

    assert str(root / "a.py") not in result
    assert len(calls) == 2


def test_walk_cache_rewalks_after_an_ignore_rule_edit(tmp_path) -> None:
    # 改写已存在的 .gitignore 不改变目录 mtime：规则文件自身的 lstat 必须是证据。
    root = _tree(tmp_path)
    calls: list[int] = []
    cache = ProjectWalkCache()
    walker = _counting_walker(root, calls)
    cache.walk(str(root), ("k",), "", walker)
    directory_before = os.lstat(root).st_mtime_ns

    (root / ".gitignore").write_text("*.log\n*.tmp\n")

    assert os.lstat(root).st_mtime_ns == directory_before
    cache.walk(str(root), ("k",), "", walker)
    assert len(calls) == 2


def test_walk_cache_keys_on_the_walk_parameters(tmp_path) -> None:
    root = _tree(tmp_path)
    calls: list[int] = []
    cache = ProjectWalkCache()
    walker = _counting_walker(root, calls)

    cache.walk(str(root), ("budget", 1), "", walker)
    cache.walk(str(root), ("budget", 2), "", walker)

    assert len(calls) == 2


def test_walk_cache_never_memoizes_racy_directories(tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("a\n")
    calls: list[int] = []
    cache = ProjectWalkCache()
    walker = _counting_walker(root, calls)

    cache.walk(str(root), ("k",), "", walker)
    cache.walk(str(root), ("k",), "", walker)

    assert len(calls) == 2
    assert len(cache) == 0


def test_walk_cache_propagates_and_never_memoizes_failures(tmp_path) -> None:
    root = _tree(tmp_path)
    cache = ProjectWalkCache()

    def failing(visited: list[str]) -> list[str]:
        visited.append("")
        raise OSError("listing failed")

    with pytest.raises(OSError, match="listing failed"):
        cache.walk(str(root), ("k",), "", failing)
    assert len(cache) == 0


def test_candidate_walker_reports_exactly_the_directories_it_listed(tmp_path) -> None:
    from tree_sitter_analyzer.index_candidate_walker import walk_candidate_entries

    (tmp_path / "pkg" / "deep").mkdir(parents=True)
    (tmp_path / "skipped").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".gitignore").write_text("skipped/\n")
    (tmp_path / "pkg" / "deep" / "a.py").write_text("a\n")
    visited: list[str] = []

    found = list(
        walk_candidate_entries(
            str(tmp_path),
            excluded_dir_names=frozenset(),
            entry_budget=1000,
            path_byte_budget=1 << 20,
            discovery_seconds=None,
            budget_error="X",
            visited_dirs=visited,
        )
    )

    assert sorted(visited) == ["", "pkg", os.path.join("pkg", "deep")]
    assert str(tmp_path / "pkg" / "deep" / "a.py") in found


# --------------------------------------------------------------------------- #
# index_identity / query_cost / live probe
# --------------------------------------------------------------------------- #


def _index_database(root: str) -> Path:
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_path

    return Path(resolve_index_path(root))


def _write_index(root: str, statement: str) -> None:
    """在已发布（封存为只读）的索引上执行一条写语句。"""
    database = _index_database(root)
    os.chmod(database, stat.S_IREAD | stat.S_IWRITE)
    conn = sqlite3.connect(database)
    try:
        conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


async def _full_index(root: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True


_WIDGET = (
    "class Widget:\n"
    "    def unused(self):\n"
    "        return 0\n\n"
    "    def used(self):\n"
    "        return 1\n\n\n"
    "def run(w):\n"
    "    return w.used()\n"
)


@pytest.fixture
async def indexed_root(tmp_path):
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "widget.py").write_text(_WIDGET, encoding="utf-8")
    (root / "pkg" / "helper.py").write_text("def helper():\n    return 3\n")
    await _full_index(root)
    evidence_file_cache.FILE_CACHE.clear()
    project_walk_cache.WALK_CACHE.clear()
    _backdate_tree(root)
    yield root
    evidence_file_cache.FILE_CACHE.clear()
    project_walk_cache.WALK_CACHE.clear()


@pytest.mark.asyncio
async def test_index_identity_changes_when_the_index_is_written(indexed_root) -> None:
    from tree_sitter_analyzer.mcp.tools import relation_freshness

    database = _index_database(str(indexed_root))
    _backdate(database)
    first = relation_freshness.index_identity(str(indexed_root))
    assert relation_freshness.index_identity(str(indexed_root)) == first

    _write_index(
        str(indexed_root), "UPDATE ast_index SET indexed_at = 'z' WHERE rowid = 1"
    )
    # 回拨到另一个过去时刻：stat 证据离开竞争窗口，但与记忆时不同。
    _backdate(database, 2 * _AN_HOUR_NS)

    assert relation_freshness.index_identity(str(indexed_root)) != first
    assert relation_freshness.index_identity(
        str(indexed_root)
    ) == relation_freshness._read_index_identity(database, first[1])


@pytest.mark.asyncio
async def test_index_holds_rows_follows_the_index_contents(indexed_root) -> None:
    from tree_sitter_analyzer.cache import query_cost

    root = str(indexed_root)
    assert query_cost._index_holds_rows(root) is True
    assert query_cost._index_holds_rows(root) is True

    _write_index(root, "DELETE FROM ast_index")

    assert query_cost._index_holds_rows(root) is False
    assert query_cost._compute_index_holds_rows(root) is False


@pytest.mark.asyncio
async def test_live_probe_reads_the_call_graph_marker(indexed_root) -> None:
    from tree_sitter_analyzer.cache.live_index_probe import probe_live_index

    root = str(indexed_root)
    probe = probe_live_index(root)
    assert probe is not None and probe.call_graph_exact is True

    _write_index(root, "UPDATE ast_call_graph_state SET built = 0")

    changed = probe_live_index(root)
    assert changed is not None and changed.call_graph_exact is False
    assert changed.identity != probe.identity


def test_live_probe_is_none_without_an_index(tmp_path) -> None:
    from tree_sitter_analyzer.cache.live_index_probe import probe_live_index

    assert probe_live_index(str(tmp_path)) is None


# --------------------------------------------------------------------------- #
# 端到端：命中缓存的答案 == 清空缓存后重算的答案
# --------------------------------------------------------------------------- #


def _without_timing(response: dict) -> dict:
    return {key: value for key, value in response.items() if "elapsed" not in key}


async def _callers(root: Path, name: str) -> dict:
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    return await CodeGraphCallersTool(str(root)).execute(
        {"function_name": name, "include_bodies": False}
    )


async def _cold_callers(root: Path, name: str) -> dict:
    """同一问题在全部证据缓存清空后的答案（即未加缓存时的计算）。"""
    from tree_sitter_analyzer.cache import query_cost
    from tree_sitter_analyzer.mcp.tools import relation_freshness, unindexed_sources

    evidence_file_cache.FILE_CACHE.clear()
    project_walk_cache.WALK_CACHE.clear()
    relation_freshness._IDENTITY_MEMO.clear()
    query_cost._HOLDS_ROWS_MEMO.clear()
    unindexed_sources._CLASSIFIED_MEMO.clear()
    return await _callers(root, name)


async def _warm(root: Path, name: str) -> dict:
    """调用两次让缓存生效，并确认它们确实被填充。"""
    await _callers(root, name)
    result = await _callers(root, name)
    # 一个遍历起点（项目根）；两个已索引 Python 文件的字节。
    assert len(project_walk_cache.WALK_CACHE) == 1
    assert len(evidence_file_cache.FILE_CACHE) == 2
    return result


@pytest.mark.asyncio
async def test_warm_answer_equals_cold_answer(indexed_root) -> None:
    for name in ("Widget.unused", "Widget.used", "helper", "missing_name"):
        await _callers(indexed_root, name)
        warm = await _callers(indexed_root, name)
        cold = await _cold_callers(indexed_root, name)
        assert _without_timing(warm) == _without_timing(cold), name


@pytest.mark.asyncio
async def test_new_unindexed_file_invalidates_the_cached_walk(indexed_root) -> None:
    warm = await _warm(indexed_root, "Widget.unused")
    assert (warm["completeness"], warm["completeness_reason"]) == ("complete", None)

    (indexed_root / "pkg" / "caller.py").write_text("def go(w):\n    w.unused()\n")
    result = await _callers(indexed_root, "Widget.unused")

    assert result["completeness_reason"] == "UNINDEXED_SOURCE_FILES"
    assert result["unindexed_source_files"] == ["pkg/caller.py"]
    assert _without_timing(result) == _without_timing(
        await _cold_callers(indexed_root, "Widget.unused")
    )


@pytest.mark.asyncio
async def test_unignored_file_invalidates_the_cached_walk(indexed_root) -> None:
    (indexed_root / ".gitignore").write_text("ignored_*.py\n")
    (indexed_root / "ignored_caller.py").write_text("def go(w):\n    w.unused()\n")
    _backdate_tree(indexed_root)
    warm = await _warm(indexed_root, "Widget.unused")
    assert warm["completeness_reason"] is None

    # 只改写规则文件内容：目录 mtime 不变，规则文件的 stat 变化必须使遍历失效。
    (indexed_root / ".gitignore").write_text("nothing_matches_*.py\n")
    result = await _callers(indexed_root, "Widget.unused")

    assert result["completeness_reason"] == "UNINDEXED_SOURCE_FILES"
    assert result["unindexed_source_files"] == ["ignored_caller.py"]


@pytest.mark.asyncio
async def test_edited_and_reindexed_file_invalidates_cached_bytes(indexed_root) -> None:
    warm = await _warm(indexed_root, "Widget.unused")
    assert warm["non_call_references"] == 0

    helper = indexed_root / "pkg" / "helper.py"
    helper.write_text("def helper(w):\n    return w.unused\n")
    stale = await _callers(indexed_root, "Widget.unused")
    # 编辑后、刷新前：新鲜度门先报告索引已过期，与未加缓存时相同。
    assert stale["completeness_reason"] == "SOURCE_INDEX_MISMATCH"
    assert _without_timing(stale) == _without_timing(
        await _cold_callers(indexed_root, "Widget.unused")
    )

    await _full_index(indexed_root)
    _backdate_tree(indexed_root)
    await _callers(indexed_root, "Widget.unused")
    result = await _callers(indexed_root, "Widget.unused")

    assert result["completeness_reason"] == "NON_CALL_REFERENCES"
    assert result["non_call_reference_sites"] == [{"file": "pkg/helper.py", "line": 2}]
    assert _without_timing(result) == _without_timing(
        await _cold_callers(indexed_root, "Widget.unused")
    )


@pytest.mark.asyncio
async def test_uncertifiable_index_answers_as_the_capture_would(
    indexed_root, monkeypatch
) -> None:
    from tree_sitter_analyzer.mcp.tools import callers_tool

    _write_index(str(indexed_root), "UPDATE ast_call_graph_state SET built = 0")
    assert callers_tool._certification_ruled_out(str(indexed_root)) is True

    skipped = await _callers(indexed_root, "Widget.used")
    monkeypatch.setattr(callers_tool, "_certification_ruled_out", lambda _root: False)
    captured = await _callers(indexed_root, "Widget.used")

    assert _without_timing(skipped) == _without_timing(captured)


@pytest.mark.asyncio
async def test_certifiable_index_still_takes_the_certified_read(
    indexed_root, monkeypatch
) -> None:
    from tree_sitter_analyzer import index_snapshot
    from tree_sitter_analyzer.mcp.tools import callers_tool

    assert callers_tool._certification_ruled_out(str(indexed_root)) is False
    entered: list[str] = []
    original = index_snapshot.certified_index_read

    def spy(root: str):
        entered.append(root)
        return original(root)

    monkeypatch.setattr(index_snapshot, "certified_index_read", spy)
    await _callers(indexed_root, "Widget.used")

    assert entered == [str(indexed_root)]
