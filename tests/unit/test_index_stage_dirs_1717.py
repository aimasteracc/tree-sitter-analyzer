"""#1717：认证捕获的私有暂存目录不再泄漏。

* 进程崩溃留下的目录（创建者 PID 已不存在）在下一次捕获前被回收；
* 旧格式或归属不明的目录只在超过年龄阈值后回收，活着的进程的目录保留；
* 句柄占用导致清理失败时，捕获以 ``INDEX_TEMP_CLEANUP_FAILED`` 失败而不是静默，
  目录在占用解除后的下一次捕获被回收。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer import index_stage_dirs as stage


def _dead_pid() -> int:
    """一个刚退出的子进程的 PID（短时间内不会被复用）。"""
    proc = subprocess.run(
        [sys.executable, "-c", "import os; print(os.getpid())"],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(proc.stdout.strip())


def _leftover(parent: Path, name: str, *, age_seconds: float = 0.0) -> Path:
    path = parent / name
    path.mkdir()
    (path / "index.db").write_bytes(b"x" * 1024)
    if age_seconds:
        stamp = time.time() - age_seconds
        os.utime(path, (stamp, stamp))
    return path


@pytest.fixture
def parent(tmp_path: Path) -> Path:
    directory = tmp_path / "temp"
    directory.mkdir()
    return directory


def test_a_crashed_process_leftover_is_swept(parent: Path) -> None:
    crashed = _leftover(parent, f"{stage.PREFIX}{_dead_pid()}-abc")

    with stage.private_stage_dir(str(parent)) as private:
        assert os.path.isdir(private)

    assert not crashed.exists()
    assert sorted(p.name for p in parent.iterdir()) == []


def test_a_live_process_directory_is_kept(parent: Path) -> None:
    live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        mine = _leftover(parent, f"{stage.PREFIX}{live.pid}-abc", age_seconds=10)

        stage.sweep_stale(str(parent))

        assert mine.exists()
    finally:
        live.kill()
        live.wait()


def test_legacy_directories_are_swept_only_when_old(parent: Path) -> None:
    young = _leftover(parent, f"{stage.PREFIX}k7fco6xz", age_seconds=60)
    old = _leftover(
        parent, f"{stage.PREFIX}_2hpwef7", age_seconds=stage.STALE_SECONDS + 60
    )
    unrelated = _leftover(parent, "tsa-other-dir", age_seconds=stage.STALE_SECONDS + 60)

    removed = stage.sweep_stale(str(parent))

    assert removed == [old.name]
    assert young.exists() and unrelated.exists() and not old.exists()


def test_the_stage_dir_is_removed_after_use(parent: Path) -> None:
    with stage.private_stage_dir(str(parent)) as private:
        Path(private, "index.db").write_bytes(b"data")
        assert Path(private).name.startswith(f"{stage.PREFIX}{os.getpid()}-")

    assert list(parent.iterdir()) == []


def test_the_stage_dir_is_removed_when_the_capture_fails(parent: Path) -> None:
    with pytest.raises(ValueError, match="CONCURRENT_WRITER"):
        with stage.private_stage_dir(str(parent)) as private:
            Path(private, "index.db").write_bytes(b"data")
            raise ValueError("CONCURRENT_WRITER")

    assert list(parent.iterdir()) == []


def test_an_active_stage_dir_is_never_swept(parent: Path, monkeypatch) -> None:
    monkeypatch.setattr(stage, "STALE_SECONDS", -1.0)
    with stage.private_stage_dir(str(parent)) as private:
        stage.sweep_stale(str(parent))
        assert os.path.isdir(private)


def test_a_cleanup_blocked_by_an_open_handle_fails_typed_then_recovers(
    parent: Path, monkeypatch
) -> None:
    import shutil

    real_rmtree = shutil.rmtree
    blocked = {"on": True}

    def rmtree(path, *args, **kwargs):
        if blocked["on"]:
            raise PermissionError(13, "The process cannot access the file", path)
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(stage.shutil, "rmtree", rmtree)
    monkeypatch.setattr(stage, "_REMOVE_PAUSE_SECONDS", 0.0)

    with pytest.raises(RuntimeError, match=stage.CLEANUP_FAILED):
        with stage.private_stage_dir(str(parent)) as private:
            Path(private, "index.db").write_bytes(b"data")
    assert os.path.isdir(private)

    blocked["on"] = False
    with stage.private_stage_dir(str(parent)):
        pass

    assert list(parent.iterdir()) == []


def test_a_capture_that_cannot_clean_up_reports_the_typed_reason(
    tmp_path: Path, monkeypatch
) -> None:
    """端到端：真实捕获在清理被阻塞时以类型化原因失败，下次捕获回收残留。"""
    if os.name != "nt":
        pytest.skip("POSIX captures of a WAL-free index pin it by descriptor, no copy")
    import asyncio
    import shutil

    from tree_sitter_analyzer import index_snapshot
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    project = tmp_path / "proj"
    project.mkdir()
    (project / "leaf.py").write_text("def leaf():\n    return 1\n", encoding="utf-8")
    asyncio.run(CodeGraphFullIndexTool(str(project)).execute({"mode": "full"}))
    temp = tmp_path / "temp"
    temp.mkdir()
    for name in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.setenv(name, str(temp))
    crashed = _leftover(temp, f"{stage.PREFIX}{_dead_pid()}-crash")

    real_rmtree = shutil.rmtree
    blocked = {"on": True}

    def rmtree(path, *args, **kwargs):
        if blocked["on"] and Path(path).name.startswith(
            f"{stage.PREFIX}{os.getpid()}-"
        ):
            raise PermissionError(13, "in use", path)
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(stage.shutil, "rmtree", rmtree)
    monkeypatch.setattr(stage, "_REMOVE_PAUSE_SECONDS", 0.0)
    first = index_snapshot._capture_existing_snapshot(
        str(project), deadline=index_snapshot._clock() + 120
    )
    assert (first.completeness, first.reason) == ("unknown", stage.CLEANUP_FAILED)
    assert not crashed.exists()
    assert len(list(temp.iterdir())) == 1  # 本次被阻塞的目录

    blocked["on"] = False
    second = index_snapshot._capture_existing_snapshot(
        str(project), deadline=index_snapshot._clock() + 120
    )

    assert second.reason != stage.CLEANUP_FAILED
    assert list(temp.iterdir()) == []


# --------------------------------------------------------------------------- #
# 边界与失败路径
# --------------------------------------------------------------------------- #


def test_sweeping_a_missing_parent_is_a_no_op(tmp_path: Path) -> None:
    assert stage.sweep_stale(str(tmp_path / "absent")) == []


def test_a_prefixed_file_is_not_a_stage_dir(parent: Path) -> None:
    stray = parent / f"{stage.PREFIX}{_dead_pid()}-file"
    stray.write_text("x")

    assert stage.sweep_stale(str(parent)) == []
    assert stray.exists()


def test_pid_liveness_edges(monkeypatch) -> None:
    assert stage.pid_alive(0) is False
    assert stage.pid_alive(os.getpid()) is True
    if sys.platform == "win32":
        assert stage.pid_alive(_dead_pid()) is False
        return

    def denied(_pid, _signal):
        raise PermissionError

    monkeypatch.setattr(stage.os, "kill", denied)
    assert stage.pid_alive(12345) is True

    def other(_pid, _signal):
        raise OSError("unknown")

    monkeypatch.setattr(stage.os, "kill", other)
    assert stage.pid_alive(12345) is True


@pytest.mark.skipif(sys.platform != "win32", reason="Kernel32 liveness probe")
def test_windows_sweep_ignores_replaced_ctypes_globals(
    parent: Path, monkeypatch
) -> None:
    # CI run 40095395832：快照测试把 ctypes.WinDLL 换成 Kernel32 替身时，回收别的
    # 进程残留目录的存活探测拿到替身而失败。探测必须使用导入时绑定的真实接口。
    import ctypes

    crashed = _leftover(parent, f"{stage.PREFIX}{_dead_pid()}-abc")

    def forbidden(*_args, **_kwargs):
        pytest.fail("存活探测不得使用被替换的 ctypes 全局")

    monkeypatch.setattr(ctypes, "WinDLL", forbidden)
    monkeypatch.setattr(ctypes, "get_last_error", forbidden)
    assert stage.sweep_stale(str(parent)) == [crashed.name]


def test_removing_a_vanished_dir_succeeds(tmp_path: Path) -> None:
    assert stage._remove(str(tmp_path / "gone")) is True


def test_a_failed_capture_with_a_blocked_cleanup_keeps_its_own_error(
    parent: Path, monkeypatch
) -> None:
    def blocked(path, *args, **kwargs):
        raise PermissionError(13, "in use", path)

    monkeypatch.setattr(stage.shutil, "rmtree", blocked)
    monkeypatch.setattr(stage, "_REMOVE_PAUSE_SECONDS", 0.0)

    with pytest.raises(ValueError, match="CONCURRENT_WRITER"):
        with stage.private_stage_dir(str(parent)) as private:
            raise ValueError("CONCURRENT_WRITER")

    assert os.path.realpath(private) in stage._LEFTOVERS
