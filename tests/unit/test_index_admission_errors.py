"""RFC-0032 slice 4 (#1554)：写入准入失败在 Python、MCP、CLI 与 watcher 上类型一致。

每个用例都以确定性的交错制造准入失败（持有发布租约、在捕获与准入之间插入一次
更新的发布、损坏选择器），不依赖 sleep 竞速。
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import tree_sitter_analyzer.cache.generation_store as store_owner
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.admission import (
    ADMISSION_CODES,
    INDEX_CANDIDATE_SUPERSEDED,
    INDEX_RECOVERY_REQUIRED,
    INDEX_WRITER_BUSY,
    IndexWriteAdmissionError,
    admission_failure_of,
)
from tree_sitter_analyzer.cache.generation_indexing import project_store
from tree_sitter_analyzer.cache.generation_routing import generation_storage_path
from tree_sitter_analyzer.cache.generation_selector import InvalidGenerationSelector
from tree_sitter_analyzer.cache.generation_store import (
    GenerationStore,
    IndexWriterBusy,
    Superseded,
)
from tree_sitter_analyzer.cache.source_recheck import (
    SOURCE_CHANGED,
    SOURCE_RECHECK_INCOMPLETE,
    SourceChanged,
)
from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor
from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool
from tree_sitter_analyzer.mcp.tools.incremental_sync_tool import (
    CodeGraphIncrementalSyncTool,
)

_BUSY = {
    "success": False,
    "verdict": "ERROR",
    "error_code": INDEX_WRITER_BUSY,
    "retryable": True,
    "retry_after_ms": 5000,
    "next_action": "recapture",
}
_SUPERSEDED = {**_BUSY, "error_code": INDEX_CANDIDATE_SUPERSEDED}
_RECOVERY = {
    **_BUSY,
    "error_code": INDEX_RECOVERY_REQUIRED,
    "retryable": False,
    "retry_after_ms": 0,
    "next_action": "recover_index",
}


def _core(payload: dict) -> dict:
    return {key: payload.get(key) for key in _BUSY}


def _published(root: Path) -> None:
    (root / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    cache = ASTCache(str(root))
    try:
        cache.index_project()
    finally:
        cache.close()
    assert (generation_storage_path(str(root)) / "active.json").is_file()


@contextmanager
def _held_lease(root: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """另一连接持有发布租约，模拟正在发布的另一写入者。"""
    monkeypatch.setattr(store_owner, "LEASE_TIMEOUT_S", 0.05)
    holder = sqlite3.connect(generation_storage_path(str(root)) / "publication.lock.db")
    try:
        holder.execute("BEGIN IMMEDIATE")
        yield
    finally:
        holder.close()


def _corrupt_selector(root: Path) -> None:
    (generation_storage_path(str(root)) / "active.json").write_bytes(b"{not json")


def _run_cli(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict]:
    from tree_sitter_analyzer.cli_main import main

    with patch.object(sys, "argv", ["tree_sitter_analyzer", *argv]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    out = capsys.readouterr().out
    return int(exc_info.value.code or 0), json.loads(out[out.index("{") :])


# --- 准入码表与归类 -------------------------------------------------------------


def test_admission_code_table_matches_rfc():
    # RFC-0032 "Typed admission failures and retry contract" 表。
    assert {
        code: (c.retryable, c.retry_after_ms, c.next_action)
        for code, c in ADMISSION_CODES.items()
    } == {
        INDEX_CANDIDATE_SUPERSEDED: (True, 5000, "recapture"),
        INDEX_WRITER_BUSY: (True, 5000, "recapture"),
        INDEX_RECOVERY_REQUIRED: (False, 0, "recover_index"),
    }
    assert all(contract.next_step for contract in ADMISSION_CODES.values())


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (Superseded("INDEX_GENERATION_SUPERSEDED"), INDEX_CANDIDATE_SUPERSEDED),
        (Superseded("INDEX_GENERATION_DIRECTORY_CHANGED"), INDEX_CANDIDATE_SUPERSEDED),
        (Superseded("INDEX_GENERATION_LOCK_UNSAFE"), INDEX_RECOVERY_REQUIRED),
        (SourceChanged(SOURCE_CHANGED, ["modified: a.py"]), INDEX_CANDIDATE_SUPERSEDED),
        (IndexWriterBusy(32), INDEX_WRITER_BUSY),
        (
            InvalidGenerationSelector("INDEX_GENERATION_SELECTOR_INVALID"),
            INDEX_RECOVERY_REQUIRED,
        ),
        (
            InvalidGenerationSelector("INDEX_GENERATION_SELECTOR_MISSING"),
            INDEX_RECOVERY_REQUIRED,
        ),
        (ValueError("INDEX_GENERATION_PATH_UNSAFE"), INDEX_RECOVERY_REQUIRED),
    ],
)
def test_generation_failures_map_to_admission_codes(exc, expected):
    failure = admission_failure_of(exc)
    assert failure is not None
    assert (failure.code, failure.cause_code) == (expected, str(exc))


@pytest.mark.parametrize(
    "exc",
    [
        SourceChanged(SOURCE_RECHECK_INCOMPLETE, ["discovery: X"]),
        RuntimeError("INDEX_GENERATION_INCOMPLETE"),
        RuntimeError("boom"),
        OSError("INDEX_GENERATION_SUPERSEDED"),
    ],
)
def test_other_failures_are_not_admission_failures(exc):
    assert admission_failure_of(exc) is None


def test_python_entrypoint_exceptions_are_typed_and_keep_their_message():
    # 现有 ``pytest.raises(Superseded, match=...)`` 与 ``except RuntimeError`` 不变。
    superseded = Superseded("INDEX_GENERATION_SUPERSEDED")
    busy = IndexWriterBusy(32)
    assert isinstance(superseded, IndexWriteAdmissionError)
    assert isinstance(busy, IndexWriteAdmissionError)
    assert (str(superseded), superseded.code, superseded.retryable) == (
        "INDEX_GENERATION_SUPERSEDED",
        INDEX_CANDIDATE_SUPERSEDED,
        True,
    )
    assert (str(busy), busy.code, busy.retry_after_ms, busy.next_action) == (
        "INDEX_WRITER_BUSY",
        INDEX_WRITER_BUSY,
        5000,
        "recapture",
    )


# --- 发布租约超时 → INDEX_WRITER_BUSY --------------------------------------------


def test_lease_timeout_raises_typed_writer_busy(tmp_path, monkeypatch):
    # E3/E5 (2026-10-13)：租约被占时竞争者报裸 ``OperationalError: database is locked``。
    _published(tmp_path)
    store = GenerationStore(
        str(tmp_path),
        str(generation_storage_path(str(tmp_path))),
        logical_path=str(tmp_path / ".ast-cache" / "index.db"),
    )
    with _held_lease(tmp_path, monkeypatch):
        with pytest.raises(IndexWriterBusy, match="^INDEX_WRITER_BUSY$") as raised:
            store.capture()
    assert isinstance(raised.value.__cause__, sqlite3.OperationalError)


def test_mcp_incremental_sync_reports_busy_writer(tmp_path, monkeypatch):
    _published(tmp_path)
    with _held_lease(tmp_path, monkeypatch):
        result = asyncio.run(
            CodeGraphIncrementalSyncTool(str(tmp_path)).execute({"mode": "sync"})
        )
    assert _core(result) == _BUSY
    assert result["error"] == "Sync failed: IndexWriterBusy: INDEX_WRITER_BUSY"
    assert result["cause_code"] == "INDEX_WRITER_BUSY"
    assert result["agent_summary"]["next_step"] == result["next_step"]


def test_cli_incremental_sync_busy_payload_matches_mcp_and_exits_1(
    tmp_path, monkeypatch, capsys
):
    _published(tmp_path)
    with _held_lease(tmp_path, monkeypatch):
        mcp = asyncio.run(
            CodeGraphIncrementalSyncTool(str(tmp_path)).execute({"mode": "sync"})
        )
        code, cli = _run_cli(
            ["--project-root", str(tmp_path), "--incremental-sync"], capsys
        )
    assert code == 1
    assert _core(cli) == _core(mcp) == _BUSY
    assert cli["next_step"] == mcp["next_step"]


def test_mcp_ast_cache_index_reports_busy_writer(tmp_path, monkeypatch):
    _published(tmp_path)
    with _held_lease(tmp_path, monkeypatch):
        result = asyncio.run(ASTCacheTool(str(tmp_path)).execute({"mode": "index"}))
    assert _core(result) == _BUSY


# --- 捕获与准入之间插入更新的发布 → INDEX_CANDIDATE_SUPERSEDED ---------------------


def test_mcp_ast_cache_index_reports_superseded_candidate(tmp_path, monkeypatch):
    # 注入交错：本次写入捕获父版本后、准入前，另一写入者发布了更新的版本。
    _published(tmp_path)
    selector = generation_storage_path(str(tmp_path)) / "active.json"
    original_begin = GenerationStore.begin
    interleaved: list[bytes] = []

    def newer_publication_then_begin(self, candidate):
        if not interleaved:
            (tmp_path / "b.py").write_text("def beta():\n    return 2\n", "utf-8")
            interleaved.append(b"")
            # 直接经存储发布（不取同进程写锁，外层写入正持有它）。
            project_store(str(tmp_path), make_source_scope_descriptor()).sync()
            interleaved[0] = selector.read_bytes()
        return original_begin(self, candidate)

    monkeypatch.setattr(GenerationStore, "begin", newer_publication_then_begin)
    result = asyncio.run(ASTCacheTool(str(tmp_path)).execute({"mode": "index"}))
    monkeypatch.setattr(GenerationStore, "begin", original_begin)
    assert _core(result) == _SUPERSEDED
    assert result["cause_code"] == "INDEX_GENERATION_SUPERSEDED"
    # 被拒绝的写入没有发布：活动版本仍是插入的那次更新发布。
    assert selector.read_bytes() == interleaved[0]
    cache = ASTCache(str(tmp_path))
    try:
        assert cache.get_stats()["total_files"] == 2
    finally:
        cache.close()


def test_source_change_during_build_is_a_superseded_candidate(tmp_path, monkeypatch):
    # RFC-0032 Revision 1：INDEX_GENERATION_SOURCE_CHANGED → INDEX_CANDIDATE_SUPERSEDED；
    # ``error`` 文本与差异清单保持不变。
    import tree_sitter_analyzer.cache.indexer as indexer

    source = tmp_path / "a.py"
    source.write_text("def f():\n    return 1\n", encoding="utf-8")
    original = indexer.run_index_project

    def edit_then_index(*args, **kwargs):
        source.write_text("def f():\n    return 12345\n", encoding="utf-8")
        return original(*args, **kwargs)

    monkeypatch.setattr(indexer, "run_index_project", edit_then_index)
    result = asyncio.run(ASTCacheTool(str(tmp_path)).execute({"mode": "index"}))
    assert _core(result) == _SUPERSEDED
    assert (result["error"], result["cause_code"], result["changes"]) == (
        SOURCE_CHANGED,
        SOURCE_CHANGED,
        ["modified: a.py"],
    )


def test_full_index_publication_error_is_typed():
    from tree_sitter_analyzer.cache.generation_indexing import _publication_error

    failure = _publication_error(
        Superseded("INDEX_GENERATION_SUPERSEDED"), "/repo", "generation_publication"
    )
    assert _core(failure) == _SUPERSEDED
    assert failure["published"] is False


# --- 损坏选择器 → INDEX_RECOVERY_REQUIRED（不重试） ---------------------------------


def test_mcp_write_routes_report_recovery_required(tmp_path):
    _published(tmp_path)
    _corrupt_selector(tmp_path)
    for tool, arguments in (
        (ASTCacheTool(str(tmp_path)), {"mode": "index"}),
        (ASTCacheTool(str(tmp_path)), {"mode": "sync"}),
        (CodeGraphIncrementalSyncTool(str(tmp_path)), {"mode": "sync"}),
    ):
        result = asyncio.run(tool.execute(arguments))
        assert _core(result) == _RECOVERY, arguments
        assert result["cause_code"] == "INDEX_GENERATION_SELECTOR_INVALID"


def test_cli_recovery_required_exits_1_with_typed_payload(tmp_path, capsys):
    _published(tmp_path)
    _corrupt_selector(tmp_path)
    code, payload = _run_cli(
        ["--project-root", str(tmp_path), "--incremental-sync"], capsys
    )
    assert code == 1
    assert _core(payload) == _RECOVERY


# --- watcher：同一答复、只重试可重试码、状态诊断 -----------------------------------


def _watcher(root: Path, on_sync=None):
    from tree_sitter_analyzer.file_watcher import FileWatcherDaemon

    cache = ASTCache(str(root))
    # poll_interval=1：准入重试的退避不随轮询间隔变化。
    return cache, FileWatcherDaemon(cache, poll_interval=1, debounce=0, on_sync=on_sync)


def test_watcher_returns_typed_busy_payload_and_backs_off(tmp_path, monkeypatch):
    _published(tmp_path)
    background: list[dict] = []
    cache, watcher = _watcher(tmp_path, on_sync=background.append)
    timers: list[tuple[float, object]] = []

    def timer(delay, callback):
        timers.append((delay, callback))
        return Mock(is_alive=lambda: False)

    monkeypatch.setattr("tree_sitter_analyzer.file_watcher.threading.Timer", timer)
    monkeypatch.setattr(watcher, "is_running", lambda: True)
    try:
        with _held_lease(tmp_path, monkeypatch):
            first = watcher.trigger_sync()
            for _ in range(5):
                timers[-1][1]()  # 计时器到期：重新捕获，再次遇到忙租约
        assert _core(first) == _BUSY
        assert first["error"] == "INDEX_WRITER_BUSY"
        assert [_core(result) for result in background] == [_BUSY] * 5
        # RFC-0032：5、10、20、40、60 秒，之后封顶 60 秒；与 poll_interval 无关。
        assert [delay for delay, _ in timers] == [5, 10, 20, 40, 60, 60]
        stats = watcher.get_stats()
        assert stats["errors"] == 6
        assert stats["last_admission_error"] == background[-1]
        # 成功的完整同步清除诊断。
        assert watcher.trigger_sync()["completeness"] == "complete"
        assert watcher.get_stats()["last_admission_error"] is None
    finally:
        watcher.stop()
        cache.close()


def test_watcher_does_not_retry_recovery_required(tmp_path, monkeypatch):
    _published(tmp_path)
    cache, watcher = _watcher(tmp_path)
    _corrupt_selector(tmp_path)
    try:
        with patch.object(watcher, "_request_sync") as request_sync:
            result = watcher.trigger_sync()
        request_sync.assert_not_called()
        assert _core(result) == _RECOVERY
        assert watcher.get_stats()["last_admission_error"] == result
    finally:
        watcher.stop()
        cache.close()


def test_watcher_status_starts_without_admission_error(tmp_path):
    cache, watcher = _watcher(tmp_path)
    try:
        assert watcher.get_stats()["last_admission_error"] is None
    finally:
        cache.close()
