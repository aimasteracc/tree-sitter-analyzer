"""RFC-0022 P0.4 zero-write Git runner.

The P0.4 invocation set must need no pathname-backed index, object
directory, shadow worktree, lock, config, attributes, or order file and
must make no write attempt (RFC-0022 P0.4). The frozen runner
(``git_subprocess``) materializes a temporary ``diff.orderFile`` override
per invocation; this module runs git with bounded pipes, ``GIT_OPTIONAL_LOCKS
=0`` (no optional lock/refresh), and no order file at all — git's default
deterministic ordering applies, and a repository-level ``diff.orderFile``
config fails the route closed before any diff command runs.

The pinned strace authority (``scripts/rfc0022_strace_*.py``) certifies
that no write attempt occurs.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404
import threading
from typing import Any

from .git_subprocess import _group_options
from .source_oracle import SourceOracleError, _remaining


def run_git_readonly(
    root: str,
    args: list[str],
    *,
    deadline: float,
    limit: int,
    env: dict[str, str] | None = None,
    input_: bytes | None = None,
) -> bytes:
    """Run Git with bounded pipes and ZERO filesystem writes.

    No temporary order file is materialized (``diff.orderFile`` is not
    overridden; repository-level ordering configs fail closed in the
    caller before any diff command runs). Every snapshot invariant is kept:
    ``GIT_OPTIONAL_LOCKS=0``, ``GIT_ATTR_NOSYSTEM=1``,
    ``GIT_NO_REPLACE_OBJECTS=1``, ``GIT_NO_LAZY_FETCH=1``, fsmonitor off.
    """
    if limit < 0:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    child_env = (
        {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith("GIT_")
        }
        if env is None
        else dict(env)
    )
    child_env["GIT_OPTIONAL_LOCKS"] = "0"
    child_env["GIT_ATTR_NOSYSTEM"] = "1"
    child_env["GIT_NO_REPLACE_OBJECTS"] = "1"
    child_env["GIT_NO_LAZY_FETCH"] = "1"
    process_options = _group_options()
    command = ["git", "-c", "core.fsmonitor=false", *args]
    try:
        proc = subprocess.Popen(  # type: ignore[call-overload]  # nosec B603
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

    def drain(stream: Any, target: bytearray, cap: int, code: str) -> None:
        try:
            if stream is None:
                failures.append("DIFF_SNAPSHOT_GIT_ERROR")
                return
            while chunk := stream.read(64 * 1024):
                if len(target) + len(chunk) > cap:
                    failures.append(code)
                    proc.kill()
                    return
                target.extend(chunk)
        except OSError:
            failures.append("DIFF_SNAPSHOT_GIT_ERROR")
            proc.kill()

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
            if any(
                thread.is_alive() for thread in threads
            ):  # pragma: no cover - defensive liveness net; join expiry raises first
                raise subprocess.TimeoutExpired("git", 0)
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - defensive net
            raise SourceOracleError("DIFF_SNAPSHOT_TIMEOUT") from exc
        if failures:
            raise SourceOracleError(failures[0])
        if proc.returncode != 0:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        succeeded = True
        return bytes(output)
    finally:
        if not succeeded:
            try:
                proc.kill()
            except OSError:  # pragma: no cover - fake/failed procs may refuse
                pass
            try:
                proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
