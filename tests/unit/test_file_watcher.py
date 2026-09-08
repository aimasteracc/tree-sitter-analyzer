"""Tests for FileWatcherDaemon (file_watcher module)."""

import os
import time

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.file_watcher import FileWatcherDaemon


def _wait_until(predicate, timeout: float = 3.0, interval: float = 0.05) -> bool:
    """Poll predicate until true or timeout. Returns the final predicate value.

    Replaces fixed time.sleep() waits for watcher events: returns as soon as the
    condition holds (typically ~1 poll interval) instead of always blocking for
    the worst-case duration.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return bool(predicate())


@pytest.fixture
def project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("def hello():\n    pass\n")
    (src / "util.py").write_text("def add(a, b):\n    return a + b\n")
    return tmp_path


@pytest.fixture
def cache(project):
    c = ASTCache(str(project))
    yield c
    c.close()


@pytest.fixture
def watcher(cache):
    w = FileWatcherDaemon(cache, poll_interval=1.0, debounce=0.3)
    yield w
    w.stop()


class TestWatcherLifecycle:
    def test_start_stop(self, watcher):
        assert not watcher.is_running()
        watcher.start()
        assert watcher.is_running()
        watcher.stop()
        assert not watcher.is_running()

    def test_double_start_is_noop(self, watcher):
        watcher.start()
        watcher.start()
        assert watcher.is_running()
        watcher.stop()

    def test_stop_when_not_started(self, watcher):
        watcher.stop()


class TestManualTriggerSync:
    def test_trigger_sync_indexes_new_files(self, watcher, project):
        result = watcher.trigger_sync()
        assert result["new_files"] == 2
        assert result["scanned"] == 2
        assert result["completeness"] == "complete"

    def test_trigger_sync_populates_cache(self, watcher, cache):
        watcher.trigger_sync()
        stats = cache.get_stats()
        assert stats["total_files"] == 2

    def test_trigger_sync_idempotent(self, watcher):
        watcher.trigger_sync()
        result = watcher.trigger_sync()
        assert result["new_files"] == 0
        assert result["unchanged_files"] == 2

    def test_trigger_sync_uses_full_index_default_scope(self, watcher, cache, project):
        """自动同步遵守完整索引默认排除范围，并记录可重放的认证范围。"""
        from tree_sitter_analyzer.index_source_scope import (
            canonical_source_scope_descriptor,
            make_source_scope_descriptor,
        )

        excluded = project / "tests" / "golden" / "corpus_watch.py"
        excluded.parent.mkdir(parents=True)
        excluded.write_text("def excluded():\n    pass\n", encoding="utf-8")
        result = watcher.trigger_sync()
        assert result["scanned"] == 2
        assert result["completeness"] == "complete"
        rows = (
            cache.get_conn()
            .execute("SELECT source_scope_descriptor FROM ast_index_snapshot_manifest")
            .fetchall()
        )
        assert [row[0] for row in rows] == [
            canonical_source_scope_descriptor(make_source_scope_descriptor())
        ]


class TestWatcherStats:
    def test_initial_stats(self, watcher):
        stats = watcher.get_stats()
        assert stats["events_processed"] == 0
        assert stats["syncs_triggered"] == 0
        assert stats["errors"] == 0

    def test_stats_after_sync(self, watcher):
        watcher.trigger_sync()
        stats = watcher.get_stats()
        assert stats["syncs_triggered"] == 1

    def test_uptime_after_start(self, watcher):
        watcher.start()
        time.sleep(0.2)
        stats = watcher.get_stats()
        assert stats["uptime_seconds"] >= 0.1
        watcher.stop()


class TestPollingDetection:
    def test_failed_scan_preserves_snapshot_without_synthesizing_change(
        self, watcher, project, monkeypatch
    ):
        """#1405：扫描失败保留基线并由下一轮重试，不触发虚假同步。"""
        from types import SimpleNamespace

        import tree_sitter_analyzer.file_watcher as owner

        watcher._take_snapshot()
        before = dict(watcher._snapshot)
        with monkeypatch.context() as patcher:

            def failed(*_a, **_k):
                return SimpleNamespace(state="unknown", reason="SOURCE_SCAN_DEADLINE")

            patcher.setattr(owner, "capture_current_source_snapshot", failed)
            patcher.setattr(owner, "capture_portable_source_snapshot", failed)
            assert watcher._detect_changes() == []
            watcher._take_snapshot()
        assert watcher._snapshot == before
        assert watcher.get_stats()["errors"] == 2
        path = project / "src" / "main.py"
        path.write_text("def saved():\n    pass\n", encoding="utf-8")
        assert watcher._detect_changes() == [str(path)]

    def test_portable_polling_reads_actual_content(self, watcher, project, monkeypatch):
        """便携路由也读取真实内容，不退回仅比较时间戳。"""
        import ntpath
        from types import SimpleNamespace

        import tree_sitter_analyzer.file_watcher as owner

        monkeypatch.setattr(owner, "os", SimpleNamespace(name="nt", path=ntpath))
        monkeypatch.setattr(
            owner,
            "capture_current_source_snapshot",
            lambda *_a, **_k: pytest.fail("不应调用 POSIX 路由"),
        )
        watcher._take_snapshot()
        path = project / "src" / "main.py"
        before = path.stat()
        path.write_text("def saved():\n    pass\n", encoding="utf-8")
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        assert watcher._detect_changes() == [ntpath.normpath(str(path))]

    @pytest.mark.parametrize("atomic", [False, True])
    def test_detects_content_change_with_preserved_metadata(
        self, watcher, project, atomic
    ):
        """等长写入与原子替换均不能借相同 mtime 绕过轮询。"""
        # 2026-09-08 实测：保留 mtime 的保存曾被轮询遗漏。
        path = project / "src" / "main.py"
        watcher._take_snapshot()
        before = path.stat()
        target = path.with_suffix(".tmp") if atomic else path
        target.write_text("def saved():\n    pass\n", encoding="utf-8")
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        if atomic:
            os.replace(target, path)
        assert (path.stat().st_size, path.stat().st_mtime_ns) == (
            before.st_size,
            before.st_mtime_ns,
        )
        assert watcher._detect_changes() == [str(path)]
        assert watcher._detect_changes() == []

    def test_detects_non_utf8_byte_change_with_preserved_metadata(
        self, watcher, project
    ):
        """#1405：不同非法 UTF-8 字节不能因替换解码后的摘要相同而被遗漏。"""
        path = project / "src" / "main.py"
        path.write_bytes(b"# coding: cp1252\ndef caf\xe9(): pass\n")
        watcher._take_snapshot()
        before = path.stat()
        path.write_bytes(b"# coding: cp1252\ndef caf\xf6(): pass\n")
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        assert watcher._detect_changes() == [str(path)]

    def test_detects_new_file(self, watcher, project, cache):
        # The watcher snapshots the tree at start(), then detects later changes.
        # So: start FIRST, let the initial snapshot settle, THEN create the file,
        # and wait for the INCREMENT (>= 3). The previous version created the file
        # before start() (already in the snapshot) and asserted >= 2 (true after
        # trigger_sync regardless) — it never actually exercised detection.
        watcher.trigger_sync()
        assert cache.get_stats()["total_files"] == 2
        watcher.start()
        time.sleep(0.3)  # let the initial snapshot complete before mutating
        (project / "new_file.py").write_text("def world():\n    pass\n")
        detected = _wait_until(lambda: cache.get_stats()["total_files"] >= 3)
        watcher.stop()
        assert detected, "watcher did not detect the newly created file"
        assert cache.get_stats()["total_files"] >= 3  # ratchet: nondeterministic

    def test_detects_modified_file(self, watcher, project, cache):
        # Same ordering requirement: start (snapshot) -> modify -> wait for the
        # SECOND sync (>= 2) caused by the modification.
        watcher.trigger_sync()
        assert watcher.get_stats()["syncs_triggered"] == 1
        watcher.start()
        time.sleep(0.3)  # let the initial snapshot complete before mutating
        py_file = project / "src" / "main.py"
        py_file.write_text("def hello():\n    return 42\n")
        os.utime(str(py_file), (time.time() + 1, time.time() + 1))
        detected = _wait_until(lambda: watcher.get_stats()["syncs_triggered"] >= 2)
        watcher.stop()
        assert detected, "watcher did not detect the modified file"
        assert watcher.get_stats()["syncs_triggered"] >= 2  # ratchet: nondeterministic


class TestOnSyncCallback:
    def test_callback_receives_result(self, cache, project):
        results: list[dict] = []

        def on_sync(r):
            results.append(r)

        w = FileWatcherDaemon(cache, on_sync=on_sync, poll_interval=1.0)
        for i in range(3):
            w._enqueue(f"/fake/{i}.py")
        w._flush_pending()
        assert len(results) == 1
        assert results[0]["new_files"] == 2
        w.stop()


class TestDebounce:
    def test_rapid_events_batched(self, cache, watcher):
        for i in range(5):
            watcher._enqueue(f"/fake/path/file{i}.py")
        assert watcher._stats.events_processed == 5
        watcher._flush_pending()
        assert watcher._stats.syncs_triggered == 1


class TestNonSourceFiles:
    def test_ignores_non_source_files(self, watcher, project):
        (project / "readme.md").write_text("# Hello")
        (project / "data.json").write_text("{}")
        result = watcher.trigger_sync()
        assert result["scanned"] == 2


class TestSkipDirExclusion:
    """REQ-E-001 回帰テスト: _LAG_SKIP_DIRS に含まれるディレクトリが
    _take_snapshot / _detect_changes のスナップショットに含まれないことを確認する。"""

    def test_take_snapshot_excludes_node_modules(self, cache, project):
        """node_modules 内の .py ファイルが snapshot に含まれない (P4b 修正)。"""
        nm = project / "node_modules"
        nm.mkdir()
        (nm / "some_lib.py").write_text("# node_modules file\n", encoding="utf-8")

        watcher = FileWatcherDaemon(cache, poll_interval=1.0, debounce=0.3)
        watcher._take_snapshot()
        with watcher._snapshot_lock:
            snapshot_keys = set(watcher._snapshot.keys())

        assert not any("node_modules" in k for k in snapshot_keys), (
            "node_modules 内のファイルが snapshot に含まれている"
        )
        watcher.stop()

    def test_detect_changes_excludes_skip_dirs(self, cache, project):
        """PR #1350：全部排除目录都不进入变更集合，且不误判祖先路径。"""
        from tree_sitter_analyzer.index_lag import _LAG_SKIP_DIRS

        skip_dir_names = sorted(_LAG_SKIP_DIRS)

        for skip_dir in skip_dir_names:
            d = project / skip_dir
            d.mkdir(exist_ok=True)
            (d / "hidden.py").write_text("hidden = True\n", encoding="utf-8")

        watcher = FileWatcherDaemon(cache, poll_interval=1.0, debounce=0.3)
        # 空快照应只报告项目内两个真实源文件。
        with watcher._snapshot_lock:
            watcher._snapshot = {}

        changed = watcher._detect_changes()
        watcher.stop()

        assert {os.path.relpath(p, project) for p in changed} == {
            os.path.join("src", "main.py"),
            os.path.join("src", "util.py"),
        }


@pytest.mark.parametrize(
    "source,destination,expected",
    [
        ("save.tmp", "main.py", ["main.py"]),
        ("main.py", "renamed.py", ["main.py", "renamed.py"]),
        ("main.py", "archive.tmp", ["main.py"]),
        ("save.tmp", "archive.tmp", []),
        ("main.py", "main.py", ["main.py"]),
        ("main.py", "", ["main.py"]),
    ],
)
def test_watchdog_dispatches_supported_move_endpoints(source, destination, expected):
    # 2026-09-08：原子保存的源文件扩展名不受支持时，目标源码仍必须触发刷新。
    from types import SimpleNamespace

    from tree_sitter_analyzer.file_watcher import _WatchdogHandler

    paths = []
    _WatchdogHandler(paths.append).dispatch(
        SimpleNamespace(src_path=source, dest_path=destination, is_directory=False)
    )
    assert paths == expected


def test_watchdog_atomic_save_refreshes_index(watcher, cache, project):
    # 2026-09-08：验证真实替换、事件入队和增量索引，不以回调次数代替索引正确性。
    from types import SimpleNamespace

    from tree_sitter_analyzer.file_watcher import _WatchdogHandler

    watcher.trigger_sync()
    target = project / "src" / "main.py"
    temporary = target.with_suffix(".tmp")
    temporary.write_text("def saved():\n    pass\n", encoding="utf-8")
    os.replace(temporary, target)
    watcher._debounce = 60.0
    _WatchdogHandler(watcher._enqueue).dispatch(
        SimpleNamespace(
            src_path=str(temporary), dest_path=str(target), is_directory=False
        )
    )
    watcher._flush_pending()
    rows = (
        cache.get_conn()
        .execute(
            "SELECT name FROM ast_symbol_rows WHERE file_path='src/main.py' ORDER BY name"
        )
        .fetchall()
    )
    assert [row[0] for row in rows] == ["saved"]
    from tree_sitter_analyzer.index_snapshot_schema import index_fingerprint

    conn = cache.get_conn()
    manifest = conn.execute(
        "SELECT file_count, index_fingerprint FROM ast_index_snapshot_manifest"
    ).fetchall()
    assert [tuple(row) for row in manifest] == [
        (2, index_fingerprint(conn, str(project)))
    ]
