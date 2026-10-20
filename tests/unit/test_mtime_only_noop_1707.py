"""#1707：只有 mtime 变化（字节完全相同）的刷新不重新提取、不发布新版本。

dogfood 第 9 轮：把一个文件按原字节重写（``touch``、同内容的 ``git checkout``）后，
``index action=cache mode=index`` 重新提取该文件、跑全局回填并发布一份新版本
（35.5 s，16 个文件时 47.5 s）。内容摘要相同即内容未变（RFC-0030 的证据是当前
字节的摘要，不是 mtime）：只更新 stat 证据（``cache.stat_evidence``），不提取、
不复制父版本、不发布。真正的内容变化照常发布。
"""

from __future__ import annotations

import os
import sqlite3
import time
from types import SimpleNamespace

import pytest

_A = "from b import beta\n\n\ndef alpha():\n    return beta()\n"
_A_EDITED = "from b import beta\n\n\ndef alpha_edited():\n    return beta()\n"
_B = "def beta():\n    return 3\n"
_BROKEN = "def broken():\n    return 4\n"
_REASON = 'Swift grammar not installed — pip install "tree-sitter-analyzer[swift]"'
_MANY = [f"m{index:02d}.py" for index in range(16)]
#: 测试把戳记设到过去（竞争窗口之外），模拟“改写后过了一会儿才刷新”。
_PAST_NS = 3_600 * 1_000_000_000


@pytest.fixture
def root(tmp_path, monkeypatch):
    from tree_sitter_analyzer.core.parser import Parser
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    project = tmp_path / "project"
    project.mkdir()
    (project / "a.py").write_text(_A, encoding="utf-8")
    (project / "b.py").write_text(_B, encoding="utf-8")
    (project / "broken.py").write_text(_BROKEN, encoding="utf-8")
    for index, name in enumerate(_MANY):
        (project / name).write_text(
            f"from b import beta\n\n\ndef many_{index}():\n    return beta()\n",
            encoding="utf-8",
        )
    original = Parser.parse_code

    def parse_code(self, source_code, language, filename=None, *args, **kwargs):
        if filename is not None and os.path.basename(filename) == "broken.py":
            return SimpleNamespace(success=False, error_message=_REASON)
        return original(self, source_code, language, filename, *args, **kwargs)

    monkeypatch.setattr(Parser, "parse_code", parse_code)
    auto_index_guard.reset()
    yield str(project)
    auto_index_guard.reset()


@pytest.fixture
def copies(monkeypatch):
    """记录私有副本的创建次数（每次 ``begin`` 都复制整份父版本）。"""
    from tree_sitter_analyzer.cache.generation_store import GenerationStore

    calls: list[str] = []
    original = GenerationStore.begin

    def begin(self, candidate):
        calls.append(str(self.root))
        return original(self, candidate)

    monkeypatch.setattr(GenerationStore, "begin", begin)
    return calls


@pytest.fixture
def extractions(monkeypatch):
    """记录被重新提取（解析并写行）的文件。"""
    from tree_sitter_analyzer.cache import extraction

    seen: list[str] = []
    original = extraction._worker_index_file

    def counted(args):
        seen.append(os.path.basename(args[0]))
        return original(args)

    monkeypatch.setattr(extraction, "_worker_index_file", counted)
    return seen


def _index_project(root):
    from tree_sitter_analyzer.ast_cache import ASTCache

    cache = ASTCache(root)
    try:
        result = cache.index_project(workers=0)
    finally:
        cache.close()
    return {
        "published": result["published"],
        "reason": result.get("publication_reason"),
        "indexed": result["indexed"],
    }


def _sync(root):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.incremental_sync import IncrementalSync
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    scope = make_source_scope_descriptor()
    cache = ASTCache(root)
    try:
        result = IncrementalSync(cache).sync(
            max_files=scope.certification_max_files,
            exclude_patterns=scope.effective_excludes,
            source_scope=scope,
        )
    finally:
        cache.close()
    indexed = sum(1 for detail in result.details if detail.get("status") == "indexed")
    return {
        "published": result.published,
        "reason": result.publication_reason,
        "indexed": indexed,
    }


_ROUTES = {"index_project": _index_project, "sync": _sync}
_UNCHANGED = {"published": False, "reason": "INDEX_UNCHANGED", "indexed": 0}


def _active(root) -> str:
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    location = resolve_index_location(root)
    assert location.published is True
    return str(getattr(location.selector, "generation_id", ""))


def _rows(root) -> dict[str, tuple[int, int, str]]:
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    path = resolve_index_location(root).path
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        return {
            str(row[0]): (int(row[1]), int(row[2]), str(row[3]))
            for row in connection.execute(
                "SELECT file_path, mtime_ns, file_size, content_hash FROM ast_index"
            )
        }
    finally:
        connection.close()


def _rewrite_same_bytes(root, name, *, mtime_ns=None):
    """按原字节重写文件；``mtime_ns`` 缺省时设到竞争窗口之外的过去。"""
    path = os.path.join(root, name)
    with open(path, "rb") as stream:
        data = stream.read()
    before = os.stat(path)
    with open(path, "wb") as stream:
        stream.write(data)
    target = time.time_ns() - _PAST_NS if mtime_ns is None else mtime_ns
    os.utime(path, ns=(before.st_atime_ns, target))
    after = os.stat(path)
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, target)
    assert after.st_mtime_ns != before.st_mtime_ns


def _write(root, name, text):
    path = os.path.join(root, name)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(text)
    info = os.stat(path)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))


def _established(root, route):
    refresh = _ROUTES[route]
    assert refresh(root)["published"] is True
    # 第二次：父版本带收敛刷新记录（稳定失败），零变化判定可用。
    assert refresh(root) == _UNCHANGED
    return refresh


@pytest.mark.parametrize("route", sorted(_ROUTES))
@pytest.mark.parametrize("touched", [["a.py"], _MANY])
def test_identical_bytes_touch_does_not_publish(
    root, route, touched, copies, extractions
) -> None:
    refresh = _established(root, route)
    active = _active(root)
    copies.clear()
    extractions.clear()
    for name in touched:
        _rewrite_same_bytes(root, name)

    result = refresh(root)

    # 不发布、活动版本不变、没有复制父版本、没有重新提取任何文件。
    assert (result, _active(root), copies, extractions) == (
        _UNCHANGED,
        active,
        [],
        [],
    )


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_touch_records_stat_evidence_and_stays_unchanged(root, route) -> None:
    from tree_sitter_analyzer.cache import stat_evidence

    refresh = _established(root, route)
    rows = _rows(root)
    _rewrite_same_bytes(root, "b.py")
    live = os.stat(os.path.join(root, "b.py"))

    assert refresh(root) == _UNCHANGED
    # stat 证据更新为磁盘戳记，绑定该行的内容摘要。
    assert stat_evidence.load(root) == {
        "b.py": (live.st_mtime_ns, live.st_size, rows["b.py"][2])
    }
    # 下一次刷新仍是零变化（不会因为行戳记旧而在之后再提取一次）。
    assert refresh(root) == _UNCHANGED
    assert refresh(root) == _UNCHANGED


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_racy_touch_is_unchanged_but_not_recorded(root, route) -> None:
    # 竞争窗口内的戳记不能作为“未变”的证据记录：同一刻度内的第二次同大小写入不改
    # 戳记。判定仍以本次读取的当前字节为准，因此照样是零变化。
    from tree_sitter_analyzer.cache import stat_evidence

    refresh = _established(root, route)
    _rewrite_same_bytes(root, "b.py", mtime_ns=time.time_ns())

    assert refresh(root) == _UNCHANGED
    assert stat_evidence.load(root) == {}


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_edit_refresh_restore_refresh_then_refresh_is_a_noop(root, route) -> None:
    refresh = _established(root, route)
    original = _active(root)

    _write(root, "a.py", _A_EDITED)
    assert refresh(root)["published"] is True
    edited = _active(root)
    _write(root, "a.py", _A)
    assert refresh(root)["published"] is True
    restored = _active(root)

    assert refresh(root) == _UNCHANGED
    # dogfood 的后续：恢复后再按原字节重写一次（换入换出工具的 finally）。
    _rewrite_same_bytes(root, "a.py")
    assert refresh(root) == _UNCHANGED
    assert refresh(root) == _UNCHANGED
    assert len({original, edited, restored, _active(root)}) == 3


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_changed_bytes_with_the_same_size_and_new_mtime_publish(root, route) -> None:
    # 同样大小、mtime 变化、字节不同：只有内容摘要能看出变化。
    refresh = _established(root, route)
    path = os.path.join(root, "b.py")
    size = os.stat(path).st_size
    _write(root, "b.py", _B.replace("3", "7"))
    assert os.stat(path).st_size == size

    result = refresh(root)
    assert (result["published"], result["indexed"]) == (True, 1)


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_line_ending_change_with_a_new_mtime_publishes(root, route) -> None:
    # 归一化摘要相同但大小不同：行的大小必须更新，读者以大小不同判定为变更。
    refresh = _established(root, route)
    path = os.path.join(root, "b.py")
    with open(path, "rb") as stream:
        data = stream.read()
    with open(path, "wb") as stream:
        stream.write(data.replace(b"\n", b"\r\n"))
    info = os.stat(path)
    os.utime(path, ns=(info.st_atime_ns, time.time_ns() - _PAST_NS))

    result = refresh(root)
    assert (result["published"], result["indexed"]) == (True, 1)


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_next_real_change_folds_the_stamps_without_reextracting(
    root, route, extractions
) -> None:
    from tree_sitter_analyzer.cache import stat_evidence

    refresh = _established(root, route)
    _rewrite_same_bytes(root, "b.py")
    assert refresh(root) == _UNCHANGED
    extractions.clear()

    _write(root, "a.py", _A_EDITED)
    result = refresh(root)

    live = os.stat(os.path.join(root, "b.py"))
    # 只有 a.py 重新提取（b.py 只刷新戳记）。
    assert (result["published"], result["indexed"]) == (True, 1)
    assert "b.py" not in extractions
    # 新版本的行带磁盘戳记，旁路记录随发布删除。
    assert _rows(root)["b.py"][:2] == (live.st_mtime_ns, live.st_size)
    assert stat_evidence.load(root) == {}


def test_real_change_beside_a_touch_publishes_and_reextracts_only_it(
    root, extractions
) -> None:
    refresh = _established(root, "index_project")
    extractions.clear()
    _rewrite_same_bytes(root, "b.py")
    _write(root, "a.py", _A_EDITED)

    result = refresh(root)

    # broken.py 是稳定失败（没有行），每次建库都重新解析；b.py 只刷新戳记。
    assert (result["published"], result["indexed"], extractions) == (
        True,
        1,
        ["a.py", "broken.py"],
    )


def test_staleness_check_after_a_touch_is_content_based(root) -> None:
    # 读者：touch 之后（无论是否已刷新）内容相同即不过期；内容改变才过期。
    from tree_sitter_analyzer.cache.fingerprint import is_ast_index_stale

    # 未入索引的源码文件（稳定失败）本身就让检查报告过期，这里去掉它。
    os.remove(os.path.join(root, "broken.py"))
    _established(root, "index_project")
    assert is_ast_index_stale(root) is False
    _rewrite_same_bytes(root, "b.py", mtime_ns=time.time_ns() + 10_000_000_000)
    assert is_ast_index_stale(root) is False
    _write(root, "b.py", _B.replace("3", "7"))
    assert is_ast_index_stale(root) is True


def test_touch_unchanged_mcp_reply(root) -> None:
    import asyncio

    from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

    tool = ASTCacheTool(root)
    asyncio.run(tool.execute({"mode": "index"}))
    asyncio.run(tool.execute({"mode": "index"}))
    _rewrite_same_bytes(root, "a.py")
    reply = asyncio.run(tool.execute({"mode": "index"}))

    assert (
        reply["published"],
        reply["publication_reason"],
        reply["indexed"],
        reply["stat_refreshed"],
    ) == (False, "INDEX_UNCHANGED", 0, 1)


def test_extractor_version_bump_reextracts_touched_files(root, monkeypatch) -> None:
    # 提取器版本变了：同样的字节也要重新提取，不能只刷新戳记（项目索引路由；
    # 同步路由按内容判定变化，不因版本重新提取，与本修复无关）。
    from tree_sitter_analyzer.cache import indexer

    refresh = _established(root, "index_project")
    _rewrite_same_bytes(root, "b.py")
    monkeypatch.setattr(
        indexer,
        "_AST_CACHE_EXTRACTOR_VERSION",
        indexer._AST_CACHE_EXTRACTOR_VERSION + 1,
    )

    result = refresh(root)

    assert (result["published"], result["indexed"]) == (True, 2 + len(_MANY))
