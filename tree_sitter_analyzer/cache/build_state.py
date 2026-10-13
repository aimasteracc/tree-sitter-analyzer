"""Persisted "full rebuild in progress" marker for the AST cache (#578).

A ``--full-index --full-index-mode full`` rebuild does ``DELETE FROM ast_index``
+ ``commit`` up front, then re-populates in bounded 500-file batches (the "A4"
RSS guard in :func:`_ast_cache_helpers._commit_index_results`). Those batched
re-inserts commit incrementally over the ~70 s rebuild, so a reader on another
connection — or another process — sees the committed-but-empty / half-filled
table and returns ``success: true`` with phantom-empty data.

A single big transaction wrapping the whole rebuild would remove the window but
revive the exact OOM that A4's bounded-batch commit exists to prevent, so it is
not an option. Instead the rebuild stamps a single sqlite meta row before the
DELETE and clears it after re-population; readers consult it and warn rather
than trusting a half-built table.

The marker is persisted (visible to every connection, including other
processes) and self-expiring: a rebuild that crashes without clearing the row
leaves a marker that goes *stale* after ``ttl_seconds`` so readers are never
wedged into permanent "rebuilding" warnings.

This mirrors the ``ast_resolve_state`` single-row idiom in
:mod:`tree_sitter_analyzer._ast_cache_unresolved`.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sqlite3
import time
from types import SimpleNamespace
from typing import Any, cast

from ._win_fileops import IS_WINDOWS

logger = logging.getLogger(__name__)

# Liveness is decided primarily by the recorded rebuilder pid (below); this TTL
# is only a backstop for the cases pid-liveness can't cover — pid reuse, or a
# (non-default) cache shared across machines. Set well above any plausible
# single rebuild so it never expires a genuinely-running one: a 20k-file repo on
# a slow/contended host can take many minutes (the ~70 s in #578 was a small
# repo). Kept finite so a wedged marker still self-heals eventually.
_DEFAULT_TTL_SECONDS = 3600.0

# Tolerance for a marker timestamp that sits slightly in the future (minor clock
# skew). Beyond this the clock stepped backward (NTP) and the marker is bogus.
_CLOCK_SKEW_GRACE_SECONDS = 60.0

_CREATE_DDL = (
    "CREATE TABLE IF NOT EXISTS ast_build_state ("
    "id INTEGER PRIMARY KEY, "
    "building INTEGER NOT NULL, "
    "started_at REAL NOT NULL, "
    "pid INTEGER NOT NULL)"
)


_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
_ERROR_ACCESS_DENIED = 5
_ERROR_INVALID_PARAMETER = 87


def _bind_native() -> Any:  # pragma: no cover - 仅 Windows 加载 Kernel32
    """导入时绑定真实原生接口；之后替换 ``ctypes`` 全局的测试替身不影响存活探测。"""
    from ctypes import wintypes

    native = cast(Any, ctypes)
    dll = native.WinDLL("kernel32", use_last_error=True)
    dll.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    dll.OpenProcess.restype = wintypes.HANDLE
    dll.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    dll.GetExitCodeProcess.restype = wintypes.BOOL
    dll.CloseHandle.argtypes = [wintypes.HANDLE]
    dll.CloseHandle.restype = wintypes.BOOL
    return SimpleNamespace(
        kernel32=dll,
        get_last_error=native.get_last_error,
        dword=wintypes.DWORD,
        byref=ctypes.byref,
    )


_NATIVE: Any = None
if IS_WINDOWS:  # pragma: no cover - 仅 Windows 绑定原生接口
    _NATIVE = _bind_native()


def _query_process(pid: int) -> tuple[int, int]:  # pragma: no cover - 原生 seam
    """返回 ``(OpenProcess 错误码, 退出码)``；打开成功时错误码为 0。

    退出码读取失败时按存活处理（句柄已打开，进程对象确实存在）。
    """
    kernel32 = _NATIVE.kernel32
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return int(_NATIVE.get_last_error()), 0
    try:
        code = _NATIVE.dword()
        if not kernel32.GetExitCodeProcess(handle, _NATIVE.byref(code)):
            return 0, _STILL_ACTIVE
        return 0, int(code.value)
    finally:
        kernel32.CloseHandle(handle)


def _win_pid_alive(pid: int) -> bool:
    """Windows 存活探测：不发信号，只查询进程对象。

    拒绝访问说明进程存在但属于其他用户 → 存活；无效参数说明无此 pid → 未存活；
    其他打开错误保守视为存活（与 POSIX 分支的 OSError 处理一致）。
    """
    error, exit_code = _query_process(pid)
    if error == _ERROR_ACCESS_DENIED:
        return True
    if error == _ERROR_INVALID_PARAMETER:
        return False
    if error:
        return True
    return exit_code == _STILL_ACTIVE


def _pid_alive(pid: int) -> bool:
    """Best-effort: is a process with this pid running on THIS machine?

    The ``.ast-cache`` db is local to the checkout, so the rebuilder and any
    concurrent reader share a machine — a dead pid means the rebuild crashed,
    and the marker is stale *immediately* (no waiting for the TTL backstop).
    POSIX: signal 0 probes existence without delivering anything.

    Windows 上绝不能用 ``os.kill(pid, 0)``：0 即 ``signal.CTRL_C_EVENT``，CPython 会调用
    ``GenerateConsoleCtrlEvent`` 向共享控制台的进程组投递 Ctrl+C（T-5，2026-10-14：
    pytest 收到 KeyboardInterrupt、PowerShell 宿主被杀）。因此改走原生进程查询。
    """
    if pid <= 0:
        return False
    if IS_WINDOWS:
        return _win_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just owned by another user
    except OSError:  # pragma: no cover — be conservative, assume alive
        return True
    return True


def mark_build_in_progress(conn: sqlite3.Connection) -> None:
    """Stamp the single-row marker that a full rebuild has started.

    Best-effort: on write failure (lock contention, transient I/O) this logs and
    returns rather than raising — the marker must never become a *new* failure
    source. The caller then proceeds without a marker, degrading to the pre-#578
    behaviour (readers may see the transient empty window) rather than aborting
    the rebuild outright, which would be a worse "can't rebuild under
    contention" failure mode.
    """
    try:
        conn.execute(_CREATE_DDL)
        conn.execute(
            "INSERT INTO ast_build_state (id, building, started_at, pid) "
            "VALUES (1, 1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "building = excluded.building, "
            "started_at = excluded.started_at, "
            "pid = excluded.pid",
            (time.time(), os.getpid()),
        )
        conn.commit()
    except sqlite3.OperationalError:
        logger.debug("could not mark build-in-progress", exc_info=True)


def clear_build_in_progress(conn: sqlite3.Connection) -> None:
    """Clear the marker after a rebuild finishes (or aborts cleanly)."""
    try:
        conn.execute("UPDATE ast_build_state SET building = 0 WHERE id = 1")
        conn.commit()
    except sqlite3.OperationalError:
        logger.debug("could not clear build-in-progress", exc_info=True)


def build_in_progress(
    conn: sqlite3.Connection, *, ttl_seconds: float = _DEFAULT_TTL_SECONDS
) -> bool:
    """True iff a full rebuild is actively in progress.

    Returns ``False`` when the marker table/row is absent, when the flag is off,
    or when the marker is *stale*. Staleness is decided by, in order:

    * **clock skew** — a ``started_at`` more than ``_CLOCK_SKEW_GRACE_SECONDS``
      in the future means the wall clock stepped backward (NTP); the marker is
      bogus, not fresh-forever.
    * **TTL backstop** — older than ``ttl_seconds`` (covers pid reuse and the
      non-default cross-machine cache case).
    * **pid liveness** — the recorded rebuilder pid is no longer running, so the
      rebuild crashed; stale immediately rather than after the full TTL.

    Never raises.
    """
    valid = (
        "typeof(id) = 'integer' AND id = 1 "
        "AND typeof(building) = 'integer' AND building IN (0, 1) "
        "AND typeof(pid) = 'integer' "
        "AND typeof(started_at) IN ('integer', 'real') "
        "AND started_at BETWEEN -1.7976931348623157e308 "
        "AND 1.7976931348623157e308"
    )
    try:
        cursor = conn.execute(
            "SELECT "
            f"CASE WHEN {valid} THEN building ELSE -1 END, "
            f"CASE WHEN {valid} THEN pid ELSE 0 END, "
            f"CASE WHEN {valid} THEN started_at ELSE 0 END "
            "FROM ast_build_state LIMIT 2"
        )
        row = cursor.fetchone()
        extra_row = cursor.fetchone()
    except sqlite3.OperationalError as exc:
        return False if "no such table" in str(exc).lower() else True
    except sqlite3.DatabaseError:
        return True
    if row is None:
        return False
    if extra_row is not None:
        return True
    try:
        building, pid, started_at = row[0], row[1], row[2]
        if (
            type(building) is not int
            or type(pid) is not int
            or type(started_at) not in (int, float)
            or building not in (-1, 0, 1)
        ):
            return True
        if building == -1:
            return True
        if building == 0:
            return False
        now = time.time()
        if started_at > now + _CLOCK_SKEW_GRACE_SECONDS:
            return False  # clock stepped backward — bogus future timestamp
        if (now - started_at) >= ttl_seconds:
            return False  # TTL backstop for a wedged/crashed marker
        if not _pid_alive(pid):
            return False  # rebuilder process gone — crashed, stale now
    except (ArithmeticError, TypeError, ValueError):
        return True
    return True
