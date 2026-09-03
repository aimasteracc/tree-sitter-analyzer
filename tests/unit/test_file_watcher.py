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

    def test_trigger_sync_populates_cache(self, watcher, cache):
        watcher.trigger_sync()
        stats = cache.get_stats()
        assert stats["total_files"] == 2

    def test_trigger_sync_idempotent(self, watcher):
        watcher.trigger_sync()
        result = watcher.trigger_sync()
        assert result["new_files"] == 0
        assert result["unchanged_files"] == 2


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
        (nm / "some_lib.py").write_text("# node_modules file\n")

        watcher = FileWatcherDaemon(cache, poll_interval=1.0, debounce=0.3)
        watcher._take_snapshot()
        with watcher._snapshot_lock:
            snapshot_keys = set(watcher._snapshot.keys())

        assert not any("node_modules" in k for k in snapshot_keys), (
            "node_modules 内のファイルが snapshot に含まれている"
        )
        watcher.stop()

    def test_detect_changes_excludes_skip_dirs(self, cache, project):
        """_LAG_SKIP_DIRS の全ディレクトリが _detect_changes から除外される。"""
        from tree_sitter_analyzer.index_lag import _LAG_SKIP_DIRS

        skip_dir_names = list(_LAG_SKIP_DIRS)[:3]  # サンプルで3つ確認

        for skip_dir in skip_dir_names:
            d = project / skip_dir
            d.mkdir(exist_ok=True)
            (d / "hidden.py").write_text("# should be excluded\n")

        watcher = FileWatcherDaemon(cache, poll_interval=1.0, debounce=0.3)
        # 初期スナップショットを空にしておく
        with watcher._snapshot_lock:
            watcher._snapshot = {}

        changed = watcher._detect_changes()
        watcher.stop()

        for skip_dir in skip_dir_names:
            assert not any(skip_dir in p for p in changed), (
                f"{skip_dir!r} 内のファイルが detect_changes に含まれている"
            )
