"""Bounded, process-tree-safe Git subprocess execution."""

from __future__ import annotations

import os
import signal
import subprocess  # nosec B404
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from typing import BinaryIO

from .secure_temp import create_private_temp
from .source_oracle import SourceOracleError, _remaining
from .temp_cleanup import cleanup_path

PopenFactory = Callable[..., subprocess.Popen[bytes]]
_IS_WINDOWS = os.name == "nt"
_TASKKILL = subprocess.run
_REAP_TIMEOUT_SECONDS = 5.0


def _windows_creation_flags() -> int:
    """Return the explicit process-group flag without importing Windows-only APIs."""
    return getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)


def _exec_guard_path() -> str:
    """Return the module-local file-size guard command path."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "git_exec_guard.py"))


def _os_kill_process_group(pid: int, sig: int) -> None:
    """Call ``killpg`` only on platforms that provide it."""
    killpg = getattr(os, "killpg", None)
    if killpg is None:
        raise OSError("process-group termination is unavailable")
    killpg(pid, sig)


_KILL_PROCESS_GROUP = _os_kill_process_group


def _group_options() -> dict[str, object]:
    if _IS_WINDOWS:
        return {"creationflags": _windows_creation_flags()}
    return {"start_new_session": True}


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    """Best-effort hard termination of Git and all hook/helper descendants."""
    try:
        if _IS_WINDOWS and getattr(proc, "pid", None) is not None:
            completed = _TASKKILL(  # nosec B603 B607
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=_REAP_TIMEOUT_SECONDS,
            )
            if getattr(completed, "returncode", 0) != 0:
                proc.kill()
        elif getattr(proc, "pid", None) is not None:
            _KILL_PROCESS_GROUP(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except Exception:  # noqa: BLE001 - process cleanup must be best effort
        try:
            proc.kill()
        except Exception:  # noqa: BLE001 - preserve the original Git failure
            pass


def _kill_and_reap(proc: subprocess.Popen[bytes]) -> None:
    """Terminate a spawned process tree and make only bounded reap attempts."""
    _kill_group(proc)
    try:
        proc.wait(timeout=_REAP_TIMEOUT_SECONDS)
        return
    except Exception:  # noqa: BLE001 - retry cleanup after any wait failure
        _kill_group(proc)
    try:
        proc.wait(timeout=_REAP_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 - reap remains best effort and bounded
        pass


def _join_threads_bounded(threads: list[threading.Thread]) -> None:
    cleanup_deadline = time.monotonic() + _REAP_TIMEOUT_SECONDS
    for thread in threads:
        try:
            thread.join(timeout=max(0.0, cleanup_deadline - time.monotonic()))
        except Exception:  # noqa: BLE001 - cleanup must not mask Git failure
            # A prior ``Thread.start`` failure can leave later threads unstarted.
            continue


def _run_git_bounded_with_order_file(
    root: str,
    args: list[str],
    *,
    deadline: float,
    limit: int,
    env: dict[str, str] | None = None,
    input_: bytes | None = None,
    popen: PopenFactory = subprocess.Popen,
    file_size_limit: int | None = None,
    order_file: str,
) -> bytes:
    """Run Git with bounded pipes, disabled fsmonitor, and mandatory reaping."""
    if limit < 0:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    if env is None:
        child_env = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith("GIT_")
        }
        child_env["GIT_OPTIONAL_LOCKS"] = "0"
    else:
        child_env = dict(env)
    # Snapshot-owned Git must never inherit machine-wide attributes.  Keep this
    # invariant here so oracle, frozen-index, hash, diff, and temp commands agree.
    child_env["GIT_ATTR_NOSYSTEM"] = "1"
    # Replacement refs are mutable name-resolution policy, not object data.
    # All snapshot Git commands resolve the original object graph consistently.
    child_env["GIT_NO_REPLACE_OBJECTS"] = "1"
    process_options = _group_options()
    command = [
        "git",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "diff.orderFile=" + order_file,
        *args,
    ]
    if file_size_limit is not None:
        if file_size_limit < 0:
            raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
        if not _IS_WINDOWS:
            guard = _exec_guard_path()
            command = [
                sys.executable,
                guard,
                "--fsize",
                str(file_size_limit),
                "--",
                *command,
            ]
    try:
        proc = popen(  # nosec B603
            command,
            cwd=root,
            stdin=subprocess.PIPE if input_ is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=child_env,
            **process_options,
        )
    except OSError as exc:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc

    output = bytearray()
    errors = bytearray()
    failures: list[str] = []

    def drain(stream: BinaryIO | None, target: bytearray, cap: int, code: str) -> None:
        try:
            if stream is None:
                failures.append("DIFF_SNAPSHOT_GIT_ERROR")
                return
            while chunk := stream.read(64 * 1024):
                if len(target) + len(chunk) > cap:
                    failures.append(code)
                    _kill_group(proc)
                    return
                target.extend(chunk)
        except OSError:
            failures.append("DIFF_SNAPSHOT_GIT_ERROR")
            _kill_group(proc)

    def feed() -> None:
        if proc.stdin is None or input_ is None:
            return
        try:
            proc.stdin.write(input_)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    threads = [
        threading.Thread(
            target=drain,
            args=(proc.stdout, output, limit, "DIFF_SNAPSHOT_CAPACITY"),
            daemon=True,
        ),
        threading.Thread(
            target=drain,
            args=(proc.stderr, errors, 64 * 1024, "DIFF_SNAPSHOT_GIT_ERROR"),
            daemon=True,
        ),
    ]
    if input_ is not None:
        threads.append(threading.Thread(target=feed, daemon=True))
    succeeded = False
    try:
        for thread in threads:
            thread.start()
        try:
            proc.wait(timeout=_remaining(deadline))
            for thread in threads:
                thread.join(timeout=_remaining(deadline))
            if any(thread.is_alive() for thread in threads):
                raise subprocess.TimeoutExpired("git", 0)
        except subprocess.TimeoutExpired as exc:
            raise SourceOracleError("DIFF_SNAPSHOT_TIMEOUT") from exc
        if failures:
            raise SourceOracleError(failures[0])
        if proc.returncode != 0:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        succeeded = True
        return bytes(output)
    finally:
        if not succeeded:
            _kill_and_reap(proc)
            _join_threads_bounded(threads)


def _order_file_candidates() -> list[str]:
    """Return host-appropriate external temporary parent candidates."""
    candidates = [tempfile.gettempdir()]
    if not _IS_WINDOWS:
        candidates.extend(("/var/tmp", "/tmp"))  # nosec B108
    return candidates


def _empty_order_file(root: str) -> tuple[int, str]:
    """Create a validated portable empty order file outside the project."""
    real_root = os.path.realpath(root)
    for candidate in _order_file_candidates():
        real_parent = os.path.realpath(candidate)
        try:
            inside = os.path.commonpath((real_root, real_parent)) == real_root
        except ValueError:
            inside = False
        if inside or not os.path.isabs(real_parent) or not os.path.isdir(real_parent):
            continue
        if not os.access(real_parent, os.W_OK | os.X_OK):
            continue
        try:
            return create_private_temp(
                prefix="tsa-empty-order-",
                directory=real_parent,
                mkstemp=tempfile.mkstemp,
                unlink=os.unlink,
            )
        except Exception:
            continue
    raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_TEMP")


def run_git_bounded(
    root: str,
    args: list[str],
    *,
    deadline: float,
    limit: int,
    env: dict[str, str] | None = None,
    input_: bytes | None = None,
    popen: PopenFactory = subprocess.Popen,
    file_size_limit: int | None = None,
) -> bytes:
    """Run Git with external diff ordering neutralized by an empty private file."""
    descriptor, order_file = _empty_order_file(root)
    try:
        try:
            os.close(descriptor)
        except Exception as exc:
            raise SourceOracleError("DIFF_SNAPSHOT_CAPTURE_ERROR") from exc
        return _run_git_bounded_with_order_file(
            root,
            args,
            deadline=deadline,
            limit=limit,
            env=env,
            input_=input_,
            popen=popen,
            file_size_limit=file_size_limit,
            order_file=order_file,
        )
    finally:
        cleanup_path(order_file)
