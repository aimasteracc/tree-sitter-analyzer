"""Windows 活动选择器发布与读者并发契约。

回归来源：rfcs/evidence/0032-feasibility E4 (2026-10-13)。读者持有 ``active.json`` 时
``os.replace`` 报 ``PermissionError [WinError 5]``（2000 次发布中 1001 次失败，读者另有
4557 次 ``PermissionError``）。
"""

import ctypes
import stat
import sys
import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from tree_sitter_analyzer.cache import _win_fileops, generation_routing
from tree_sitter_analyzer.cache import generation_store as owner
from tree_sitter_analyzer.cache.generation_store import GenerationStore, IndexWriterBusy

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="E4 共享冲突只存在于 Windows 原生句柄语义"
)


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "a.py").write_text("def original(): return 0\n", encoding="utf-8")
    return GenerationStore(str(root), str(tmp_path / "storage"))


@contextmanager
def reader_holding_selector(store, monkeypatch):
    """让真实 read_selector 在已打开选择器、尚未读取时停住，模拟持有句柄的读者。"""
    opened, release = threading.Event(), threading.Event()
    result = {}

    def hold(mode):
        if threading.current_thread() is reader:
            opened.set()
            release.wait(10)
        return stat.S_ISREG(mode)

    monkeypatch.setattr(
        generation_routing, "stat", SimpleNamespace(S_ISDIR=stat.S_ISDIR, S_ISREG=hold)
    )

    def run():
        try:
            result["selector"] = store.active_selector()
        except BaseException as exc:
            result["error"] = exc

    reader = threading.Thread(target=run)
    reader.start()
    try:
        if not opened.wait(10):
            pytest.fail("读者未能打开活动选择器")
        yield result
    finally:
        release.set()
        reader.join(10)


def next_generation(store):
    (store.root / "a.py").write_text("def changed(): return 1\n", encoding="utf-8")
    return store.prepare(store.capture())


@windows_only
def test_publish_succeeds_while_reader_holds_selector(store, monkeypatch):
    # rfcs/evidence/0032-feasibility E4 (2026-10-13)：持有句柄的读者曾使发布失败。
    store.sync()
    prepared = next_generation(store)
    with reader_holding_selector(store, monkeypatch):
        published = store.publish(prepared)
    assert published == prepared.selector


@windows_only
def test_held_reader_keeps_old_selector_bytes(store, monkeypatch):
    # rfcs/evidence/0032-feasibility E4 (2026-10-13)：旧句柄读到完整旧字节，不撕裂。
    first = store.sync()
    prepared = next_generation(store)
    with reader_holding_selector(store, monkeypatch) as held:
        store.publish(prepared)
    assert held == {"selector": first}


@windows_only
def test_reader_opening_after_publish_sees_new_selector(store, monkeypatch):
    # rfcs/evidence/0032-feasibility E4 (2026-10-13)：旧句柄存续时新打开者见新版本。
    store.sync()
    prepared = next_generation(store)
    with reader_holding_selector(store, monkeypatch):
        store.publish(prepared)
        assert store.active_selector() == prepared.selector


@windows_only
def test_bounded_contention_has_no_publish_or_read_errors(store):
    # rfcs/evidence/0032-feasibility E4.2 (2026-10-13)：并发读写循环曾 1001/2000 发布失败。
    first = store.sync()
    second = store.publish(next_generation(store))
    payloads = (first.encode(), second.encode())
    stop, outcomes = threading.Event(), {"errors": [], "torn": 0}

    def read_loop():
        while not stop.is_set():
            try:
                if store.active_selector() not in (first, second):
                    outcomes["torn"] += 1
            except Exception as exc:
                outcomes["errors"].append(repr(exc))

    reader = threading.Thread(target=read_loop)
    reader.start()
    failures = []
    try:
        for index in range(200):
            try:
                owner._write_atomic(store.selector_path, payloads[index % 2])
            except Exception as exc:
                failures.append(repr(exc))
    finally:
        stop.set()
        reader.join(10)
    assert (failures, outcomes) == ([], {"errors": [], "torn": 0})


@windows_only
@pytest.mark.parametrize("code", [1, 32, 50, 87])
def test_unsupported_rename_fails_closed_with_writer_busy(store, monkeypatch, code):
    # rfcs/evidence/0032-feasibility E4 (2026-10-13)：不支持 POSIX 语义改名时不得退回
    # 有竞态的 os.replace，必须以类型化忙错误失败且活动选择器不变。
    first = store.sync()
    prepared = next_generation(store)

    def unsupported(handle, info_class, buffer, size):
        ctypes.set_last_error(code)
        return False

    monkeypatch.setattr(_win_fileops, "_set_file_information", unsupported)
    with pytest.raises(IndexWriterBusy, match="^INDEX_WRITER_BUSY$"):
        store.publish(prepared)
    assert store.active_selector() == first


@pytest.mark.parametrize("code", [1, 5, 32, 33, 50, 87])
def test_busy_or_unsupported_codes_map_to_writer_busy(tmp_path, code):
    # rfcs/evidence/0032-feasibility E4 (2026-10-13)：不支持或被旧读者占用即失败关闭。
    failure = _win_fileops.native_failure(code, tmp_path / "active.json")
    assert (type(failure), str(failure), failure.winerror, failure.retryable) == (
        IndexWriterBusy,
        "INDEX_WRITER_BUSY",
        code,
        True,
    )


def test_other_native_codes_keep_os_error(tmp_path):
    target = tmp_path / "active.json"
    failure = _win_fileops.native_failure(2, target)
    assert (isinstance(failure, OSError), failure.filename) == (True, str(target))
