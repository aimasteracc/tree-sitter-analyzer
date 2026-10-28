"""#1717：认证捕获的私有暂存目录——必清理，清理失败给出类型化原因，残留可回收。

Windows（以及带 WAL 的 POSIX 索引）上，每次认证捕获都把整份索引（本仓库约 340 MB）
复制到 ``%TEMP%`` 下的私有目录，供私有 SQLite 恢复 WAL。原实现用
``tempfile.TemporaryDirectory``：

* 进程在捕获中途被杀（MCP 客户端重启、超时终止）时目录永远留下；
* 仍有句柄占用（实时扫描、尚未关闭的连接）时清理抛出 ``PermissionError``，
  捕获以一段不可分类的错误文本失败，目录同样留下。

实测一台机器上积累了 14 份、共 4.7 GB。这里改为：

* 目录名带创建进程的 PID：``tsa-wal-index-<pid>-<随机>``。
* 创建前回收残留：PID 已不存在的目录、本进程以前清理失败的目录立即删除；
  旧格式（无 PID）或归属无法确认的目录超过 :data:`STALE_SECONDS` 才删除（捕获远短于
  此，不会删到正在使用的目录）。仍被占用而删不掉的跳过，下次再试。
* 退出时先由调用方关闭全部句柄（私有 SQLite 连接在本上下文之前退出），再删除；
  Windows 上对短暂占用重试几次。仍删不掉时记下目录供下次回收，并在没有其他异常
  传播时抛出 ``RuntimeError("INDEX_TEMP_CLEANUP_FAILED")``——捕获以类型化原因失败，
  从不静默。
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

from .cache.build_state import _win_pid_alive as _bound_windows_pid_alive

#: 暂存目录名前缀（旧版本为 ``tsa-wal-index-<随机>``，不含 PID）。
PREFIX = "tsa-wal-index-"
#: 无法确认归属的残留目录，超过此年龄才回收（秒）。
STALE_SECONDS = 3600.0
#: 清理失败的原因码。
CLEANUP_FAILED = "INDEX_TEMP_CLEANUP_FAILED"
#: Windows 上删除被短暂占用目录的重试次数与间隔。
_REMOVE_ATTEMPTS = 3
_REMOVE_PAUSE_SECONDS = 0.2
_PID_NAME = re.compile(re.escape(PREFIX) + r"(\d+)-")

_LOCK = threading.Lock()
#: 本进程正在使用的暂存目录（不得被回收）。
_ACTIVE: set[str] = set()
#: 本进程清理失败、已不再使用的暂存目录（下次回收时不论年龄重试）。
_LEFTOVERS: set[str] = set()


def _now() -> float:
    return time.time()


def pid_alive(pid: int) -> bool:
    """``pid`` 对应的进程是否仍在运行；无法判断时按“仍在运行”（不删除）。"""
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _windows_pid_alive(pid: int) -> bool:  # pragma: no cover - 仅 Windows
    """Windows 存活探测，复用 ``cache.build_state`` 导入时绑定的 Kernel32。

    原实现每次调用都 ``ctypes.WinDLL("kernel32")`` 延迟查找全局：进程内任何替换
    ``ctypes.WinDLL`` 的代码（测试的 Kernel32 替身）都会让回收别的进程残留目录时
    拿到替身（CI run 40095395832：``'_Kernel' object has no attribute
    'OpenProcess'``）。语义不变：87（无此进程）为未存活，其他打开错误按存活。
    """
    return _bound_windows_pid_alive(pid)


def _owner_pid(name: str) -> int | None:
    match = _PID_NAME.match(name)
    return int(match.group(1)) if match else None


def _remove(path: str) -> bool:
    """删除目录；成功或已不存在为 True。"""
    for attempt in range(_REMOVE_ATTEMPTS):
        try:
            shutil.rmtree(path)
        except FileNotFoundError:
            return True
        except OSError:
            if attempt + 1 < _REMOVE_ATTEMPTS:
                time.sleep(_REMOVE_PAUSE_SECONDS)
            continue
        return True
    return not os.path.lexists(path)


def sweep_stale(temp_parent: str) -> list[str]:
    """回收 ``temp_parent`` 下的残留暂存目录，返回已删除的目录名。"""
    removed: list[str] = []
    try:
        entries = list(os.scandir(temp_parent))
    except OSError:
        return removed
    now = _now()
    for entry in entries:
        if not entry.name.startswith(PREFIX):
            continue
        path = os.path.realpath(entry.path)
        with _LOCK:
            if path in _ACTIVE:
                continue
        try:
            if not entry.is_dir(follow_symlinks=False):
                continue
            age = now - entry.stat(follow_symlinks=False).st_mtime
        except OSError:
            continue
        owner = _owner_pid(entry.name)
        with _LOCK:
            leftover = path in _LEFTOVERS
        if leftover:
            stale = True  # 本进程以前清理失败、已不再使用
        elif owner is not None and owner != os.getpid() and not pid_alive(owner):
            stale = True  # 创建者已退出：残留无疑
        else:
            stale = age > STALE_SECONDS  # 旧格式或本进程的遗留：只按年龄
        if stale and _remove(path):
            removed.append(entry.name)
            with _LOCK:
                _LEFTOVERS.discard(path)
    return removed


@contextmanager
def private_stage_dir(temp_parent: str) -> Iterator[str]:
    """创建本进程的暂存目录；退出时删除，失败时以类型化原因报告。"""
    sweep_stale(temp_parent)
    path = os.path.realpath(
        tempfile.mkdtemp(prefix=f"{PREFIX}{os.getpid()}-", dir=temp_parent)
    )
    with _LOCK:
        _ACTIVE.add(path)
    failed = False
    try:
        yield path
    except BaseException:
        failed = True
        raise
    finally:
        with _LOCK:
            _ACTIVE.discard(path)
        cleaned = _remove(path)
        if not cleaned:
            with _LOCK:
                _LEFTOVERS.add(path)
            if not failed:
                raise RuntimeError(CLEANUP_FAILED)
