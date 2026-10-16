"""索引指纹内容寻址备忘录的行为测试（Issue #1561）。"""

from __future__ import annotations

import hashlib

import pytest

from tree_sitter_analyzer import index_fingerprint_memo as memo


@pytest.fixture(autouse=True)
def _isolated_memo():
    memo.clear_index_fingerprint_memo()
    yield
    memo.clear_index_fingerprint_memo()


async def _certified_project(root):
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (root / "leaf.py").write_text("def leaf():\n    return 1\n", encoding="utf-8")
    result = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert result["scope_complete"] is True
    memo.clear_index_fingerprint_memo()


def _count_fingerprints(monkeypatch) -> list[str]:
    from tree_sitter_analyzer import index_snapshot

    calls: list[str] = []
    original = index_snapshot.index_fingerprint

    def counting(connection, root, **kwargs):
        calls.append(root)
        return original(connection, root, **kwargs)

    monkeypatch.setattr(index_snapshot, "index_fingerprint", counting)
    return calls


async def test_unchanged_index_bytes_fingerprint_once_across_captures(
    tmp_path, monkeypatch
):
    # Issue #1561：每次捕获都全表排序哈希（2.4k 文件实测 18 秒）使认证必然超时。
    from tree_sitter_analyzer import index_snapshot

    await _certified_project(tmp_path)
    calls = _count_fingerprints(monkeypatch)

    first = index_snapshot.read_existing_snapshot(str(tmp_path))
    second = index_snapshot.read_existing_snapshot(str(tmp_path))

    assert (first.completeness, second.completeness) == ("complete", "complete")
    assert second.index_fingerprint == first.index_fingerprint
    assert len(calls) == 1


async def test_changed_index_bytes_recompute_fingerprint(tmp_path, monkeypatch):
    # Issue #1561：备忘录按字节内容寻址；任何索引写入都必须换键重新计算。
    from tree_sitter_analyzer import index_snapshot
    from tree_sitter_analyzer.ast_cache import ASTCache

    await _certified_project(tmp_path)
    calls = _count_fingerprints(monkeypatch)
    first = index_snapshot.read_existing_snapshot(str(tmp_path))
    cache = ASTCache(str(tmp_path))
    try:
        cache.invalidate(str(tmp_path / "leaf.py"))
    finally:
        cache.close()

    second = index_snapshot.read_existing_snapshot(str(tmp_path))

    assert (first.completeness, second.completeness) == ("complete", "partial")
    assert (second.reason, len(calls)) == ("CALL_GRAPH_INCOMPLETE", 2)


def _slower_than_capture(monkeypatch, name: str) -> list[float]:
    """把 ``name`` 换成需要比一次捕获期限多 1 秒预算的计算；期限不足即超时。"""
    import time

    from tree_sitter_analyzer import index_snapshot

    cost = index_snapshot._CAPTURE_DEADLINE_SECONDS + 1.0
    original = getattr(index_snapshot, name)
    calls: list[float] = []

    def slow(*args, **kwargs):
        calls.append(kwargs["deadline"])
        if kwargs["deadline"] - time.monotonic() < cost:
            raise RuntimeError("INDEX_FINGERPRINT_DEADLINE")
        return original(*args, **kwargs)

    monkeypatch.setattr(index_snapshot, name, slow)
    return calls


async def test_fingerprint_slower_than_capture_deadline_is_computed_once(
    tmp_path, monkeypatch
):
    # Issue #1634：指纹成本贴近 10 秒捕获期限时每次都超时、从不入表，
    # nav callers 每次固定付出约 10 秒；入表计算须按整段预算完成。
    from tree_sitter_analyzer import index_snapshot

    await _certified_project(tmp_path)
    calls = _slower_than_capture(monkeypatch, "index_fingerprint")

    index_snapshot.read_existing_snapshot(str(tmp_path))
    second = index_snapshot.read_existing_snapshot(str(tmp_path))

    assert (len(calls), second.completeness) == (1, "complete")


async def test_projection_check_slower_than_capture_deadline_is_computed_once(
    tmp_path, monkeypatch
):
    # Issue #1634：符号投影判定同为入表计算，同样不得在捕获期限处反复重算。
    from tree_sitter_analyzer import index_snapshot

    await _certified_project(tmp_path)
    calls = _slower_than_capture(monkeypatch, "symbol_projection_is_exact")

    index_snapshot.read_existing_snapshot(str(tmp_path))
    second = index_snapshot.read_existing_snapshot(str(tmp_path))

    assert (len(calls), second.completeness) == (1, "complete")


def test_missing_content_key_keeps_capture_deadline():
    # Issue #1634：无内容键的结果不会复用，延长期限只会拖慢本次调用。
    assert memo.memo_compute_deadline(None, 5.0, 1.0, 120.0) == 5.0


def test_content_key_extends_deadline_to_compute_budget():
    # Issue #1634：有内容键时期限取「现在 + 整段预算」。
    assert memo.memo_compute_deadline(("key",), 5.0, 1.0, 120.0) == 121.0


def test_missing_content_key_always_recomputes():
    calls: list[int] = []

    def compute() -> str:
        calls.append(1)
        return "sha256:" + "a" * 64

    memo.memoized_index_fingerprint(None, compute)
    memo.memoized_index_fingerprint(None, compute)

    assert len(calls) == 2


def test_memo_evicts_least_recently_used_key():
    computed: list[str] = []

    def compute_for(label: str):
        def compute() -> str:
            computed.append(label)
            return label

        return compute

    for index in range(memo._MEMO_CAPACITY):
        memo.memoized_index_fingerprint((str(index),), compute_for(str(index)))
    memo.memoized_index_fingerprint(("0",), compute_for("0"))
    memo.memoized_index_fingerprint(("new",), compute_for("new"))
    memo.memoized_index_fingerprint(("0",), compute_for("0"))
    memo.memoized_index_fingerprint(("1",), compute_for("1"))

    assert computed == [str(i) for i in range(memo._MEMO_CAPACITY)] + ["new", "1"]


def test_failed_compute_is_not_memoized():
    def failing() -> str:
        raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")

    with pytest.raises(RuntimeError, match="INDEX_SNAPSHOT_DEADLINE"):
        memo.memoized_index_fingerprint(("key",), failing)

    assert memo.memoized_index_fingerprint(("key",), lambda: "computed") == "computed"


def _open_bytes(tmp_path, payload: bytes) -> int:
    import os

    path = tmp_path / "index.db"
    path.write_bytes(payload)
    return os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))


def test_pinned_fd_content_key_hashes_exact_bytes_and_rewinds(tmp_path):
    import os

    fd = _open_bytes(tmp_path, b"bytes")
    try:
        key = memo.pinned_fd_content_key(fd, 5, lambda: None)
        offset = os.lseek(fd, 0, os.SEEK_CUR)
    finally:
        os.close(fd)

    assert (key, offset) == ((f"index.db:{hashlib.sha256(b'bytes').hexdigest()}",), 0)


@pytest.mark.parametrize("declared", [4, 6])
def test_pinned_fd_content_key_rejects_size_drift(tmp_path, declared):
    import os

    fd = _open_bytes(tmp_path, b"bytes")
    try:
        with pytest.raises(ValueError, match="CONCURRENT_WRITER"):
            memo.pinned_fd_content_key(fd, declared, lambda: None)
    finally:
        os.close(fd)
