#!/usr/bin/env python3
"""Atomic evidence publication for the RFC-0022 strace authority."""

from __future__ import annotations

import hashlib
import json
import os
import re
import select
import signal
import stat
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rfc0022_strace_model import AuthorityError

TRACE_NAME = re.compile(r"trace\.([1-9][0-9]*)")
TERMINAL = re.compile(r"\+\+\+ (?:exited with \d+|killed by .+) \+\+\+")
MAX_CLEANUP_IDENTITIES = 4096
LINUX_SIGKILL = 9


def raw_trace_metadata(
    trace_dir: Path, *, expected_uid: int = 0
) -> list[dict[str, Any]]:
    metadata: list[dict[str, Any]] = []
    if not trace_dir.is_dir():
        return metadata
    directory_stat = trace_dir.stat()
    if (
        directory_stat.st_uid != expected_uid
        or stat.S_IMODE(directory_stat.st_mode) != 0o700
    ):
        raise OSError("raw trace directory lost root-only ownership")
    for path in sorted(trace_dir.iterdir()):
        match = TRACE_NAME.fullmatch(path.name)
        if match is None or not path.is_file() or path.is_symlink():
            raise OSError(f"unexpected raw trace entry: {path.name}")
        path_stat = path.stat()
        if path_stat.st_uid != expected_uid or stat.S_IMODE(path_stat.st_mode) & 0o022:
            raise OSError(f"raw trace is not root-owned and protected: {path.name}")
        raw = path.read_bytes()
        try:
            lines = raw.decode("utf-8", "strict").splitlines()
        except UnicodeDecodeError as exc:
            raise OSError(f"raw trace is not UTF-8: {path.name}") from exc
        terminal = None
        if lines:
            body = lines[-1].partition(" ")[2]
            terminal = body if TERMINAL.fullmatch(body) else None
        metadata.append(
            {
                "pid": int(match.group(1)),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size": len(raw),
                "terminal": terminal,
            }
        )
    return metadata


def seal_trace_directory(trace_dir: Path) -> None:
    for path in trace_dir.iterdir():
        if not path.is_file() or path.is_symlink():
            raise OSError(f"cannot seal unexpected trace entry: {path.name}")
        path.chmod(0o444)
    trace_dir.chmod(0o555)


def record_error_trace_metadata(report: dict[str, Any], trace_dir: Path) -> None:
    try:
        report["raw_trace_files"] = raw_trace_metadata(trace_dir)
        seal_trace_directory(trace_dir)
    except OSError as exc:
        report["errors"].append(f"raw trace finalization failed: {exc}")


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_failure_report(
    path: Path,
    *,
    error: str,
    policy_path: Path,
    target: list[str],
    expected_returncode: int,
) -> None:
    write_report(
        path,
        {
            "schema_version": 1,
            "authority_id": "rfc0022-linux-strace-v1",
            "authority_status": "error",
            "outcome": "indeterminate",
            "errors": [error],
            "policy": {"path": os.fspath(policy_path.resolve())},
            "raw_trace_files": [],
            "target_identity": None,
            "trace_files": [],
            "violations": [],
            "target": {
                "argv": target,
                "expected_returncode": expected_returncode,
                "returncode": None,
            },
        },
    )


@dataclass(frozen=True)
class ProcessIdentity:
    """An owned pidfd binding cleanup to one Linux process lifetime."""

    pid: int
    pidfd: int


def _open_identity(pid: int) -> ProcessIdentity | None:
    opener = getattr(os, "pidfd_open", None)
    if not callable(opener):
        raise AuthorityError("pidfd cleanup support is unavailable")
    try:
        return ProcessIdentity(pid, opener(pid, 0))
    except ProcessLookupError:
        return None
    except (AttributeError, OSError) as exc:
        raise AuthorityError(f"unable to open cleanup pidfd for {pid}") from exc


def _identity_alive(identity: ProcessIdentity) -> bool:
    try:
        poller = select.poll()
        poller.register(identity.pidfd, select.POLLIN)
        return not poller.poll(0)
    except OSError as exc:
        raise AuthorityError(
            f"unable to poll cleanup pidfd for {identity.pid}"
        ) from exc


def close_process_identities(identities: list[ProcessIdentity]) -> None:
    for identity in identities:
        try:
            os.close(identity.pidfd)
        except OSError:
            pass


def require_pidfd_support() -> None:
    """Fail before target launch unless race-free Linux signaling is available."""
    sender = getattr(signal, "pidfd_send_signal", None)
    if not callable(getattr(os, "pidfd_open", None)) or not callable(sender):
        raise AuthorityError("pidfd cleanup support is unavailable")
    identity = _open_identity(os.getpid())
    if identity is None:
        raise AuthorityError("unable to bind authority pidfd")
    try:
        sender(identity.pidfd, 0, None, 0)
    except OSError as exc:
        raise AuthorityError("pidfd cleanup self-probe failed") from exc
    finally:
        close_process_identities([identity])


def trace_pids(trace_dir: Path) -> list[int]:
    if not trace_dir.is_dir():
        return []
    return sorted(
        int(match.group(1))
        for path in trace_dir.iterdir()
        if path.is_file() and (match := TRACE_NAME.fullmatch(path.name)) is not None
    )


_STATUS_TGID = re.compile(rb"^Tgid:[ \t]*([1-9][0-9]*)$", re.MULTILINE)
_STATUS_TRACER = re.compile(rb"^TracerPid:[ \t]*([0-9]+)$", re.MULTILINE)


def _status_membership(proc: Path, pid: int) -> tuple[int, int] | None:
    try:
        status = (proc / str(pid) / "status").read_bytes()
    except (FileNotFoundError, ProcessLookupError):
        return None
    except OSError as exc:
        raise AuthorityError(f"unable to read cleanup status for {pid}") from exc
    tgids = _STATUS_TGID.findall(status)
    tracers = _STATUS_TRACER.findall(status)
    if len(tgids) != 1 or len(tracers) != 1:
        raise AuthorityError(f"ambiguous cleanup status for {pid}")
    return int(tgids[0]), int(tracers[0])


def _proc_entries(proc_root: Path) -> list[Path]:
    try:
        return list(proc_root.iterdir())
    except OSError as exc:
        raise AuthorityError("unable to enumerate cleanup processes") from exc


def capture_cleanup_identities(
    token: str,
    trace_dir: Path | None = None,
    *,
    tracer_pid: int | None = None,
    proc_root: Path = Path("/proc"),
    exclude_pids: frozenset[int] = frozenset(),
) -> list[ProcessIdentity]:
    """Open pidfds, then validate token or live ptrace membership."""
    needle = f"RFC0022_AUTHORITY_TOKEN={token}".encode()
    identities: list[ProcessIdentity] = []
    try:
        if proc_root.is_dir():
            for entry in _proc_entries(proc_root):
                if not entry.name.isdigit():
                    continue
                pid = int(entry.name)
                if pid == os.getpid() or pid in exclude_pids:
                    continue
                identity = _open_identity(pid)
                if identity is None:
                    continue
                identities.append(identity)
                if len(identities) > MAX_CLEANUP_IDENTITIES:
                    raise AuthorityError("cleanup identity limit exceeded")
                try:
                    environment = (entry / "environ").read_bytes().split(b"\0")
                except (FileNotFoundError, PermissionError, ProcessLookupError):
                    environment = []
                if needle not in environment or not _identity_alive(identity):
                    identities.remove(identity)
                    close_process_identities([identity])
        if trace_dir is not None and tracer_pid is not None:
            for tid in trace_pids(trace_dir):
                first = _status_membership(proc_root, tid)
                if first is None or first[1] != tracer_pid:
                    continue
                tgid = first[0]
                if tgid == os.getpid() or tgid in exclude_pids:
                    continue
                existing = next((item for item in identities if item.pid == tgid), None)
                if existing is not None:
                    if _identity_alive(existing):
                        continue
                    identities.remove(existing)
                    close_process_identities([existing])
                identity = _open_identity(tgid)
                if identity is None:
                    continue
                identities.append(identity)
                if len(identities) > MAX_CLEANUP_IDENTITIES:
                    raise AuthorityError("cleanup identity limit exceeded")
                second = _status_membership(proc_root, tid)
                leader = _status_membership(proc_root, tgid)
                if (
                    second != first
                    or leader is None
                    or leader[0] != tgid
                    or second[1] != tracer_pid
                    or not _identity_alive(identity)
                ):
                    identities.remove(identity)
                    close_process_identities([identity])
        return identities
    except Exception as exc:
        close_process_identities(identities)
        if isinstance(exc, AuthorityError):
            raise
        raise AuthorityError("cleanup identity discovery failed") from exc


def signal_cleanup_identities(identities: list[ProcessIdentity]) -> None:
    """Signal each distinct stable handle without transferring ownership."""
    sender = getattr(signal, "pidfd_send_signal", None)
    if not callable(sender):
        raise AuthorityError("pidfd cleanup support is unavailable")
    errors: list[str] = []
    for identity in {item.pidfd: item for item in identities}.values():
        try:
            sender(identity.pidfd, LINUX_SIGKILL, None, 0)
        except ProcessLookupError:
            pass
        except OSError as exc:
            errors.append(f"pidfd signal failed for {identity.pid}: {exc}")
    if errors:
        raise AuthorityError("; ".join(errors))


def _kill_identities(
    identities: list[ProcessIdentity], *, timeout: float = 1.0
) -> tuple[list[int], list[int]]:
    unique = list({item.pidfd: item for item in identities}.values())
    deadline = time.monotonic() + max(timeout, 0.0)
    try:
        signal_cleanup_identities(unique)
        remaining = [item for item in unique if _identity_alive(item)]
        while remaining and time.monotonic() < deadline:
            time.sleep(min(0.05, max(deadline - time.monotonic(), 0.0)))
            remaining = [item for item in remaining if _identity_alive(item)]
        return sorted({item.pid for item in unique}), sorted(
            {item.pid for item in remaining}
        )
    finally:
        close_process_identities(unique)


def cleanup_candidates(
    token: str,
    captured: list[ProcessIdentity] | None = None,
    *,
    timeout: float = 1.0,
) -> tuple[list[int], list[int]]:
    """Kill stable identities and observe once more after the final signal."""
    deadline = time.monotonic() + max(timeout, 0.0)
    pending = list(captured or [])
    cleaned: set[int] = set()
    observed = 0
    while True:
        if not pending:
            pending = capture_cleanup_identities(token)
            if not pending:
                return sorted(cleaned), []
        observed += len(pending)
        if observed > MAX_CLEANUP_IDENTITIES:
            close_process_identities(pending)
            raise AuthorityError("cleanup identity limit exceeded")
        killed, remaining = _kill_identities(
            pending, timeout=max(deadline - time.monotonic(), 0.0)
        )
        cleaned.update(killed)
        post = capture_cleanup_identities(token)
        observed += len(post)
        if observed > MAX_CLEANUP_IDENTITIES:
            close_process_identities(post)
            raise AuthorityError("cleanup identity limit exceeded")
        if not remaining and not post:
            return sorted(cleaned), []
        if not remaining and time.monotonic() < deadline:
            pending = post
            continue
        if post:
            killed, post_remaining = _kill_identities(post, timeout=0.0)
            cleaned.update(killed)
            remaining = sorted((set(remaining) - set(killed)) | set(post_remaining))
        final = capture_cleanup_identities(token)
        observed += len(final)
        if observed > MAX_CLEANUP_IDENTITIES:
            close_process_identities(final)
            raise AuthorityError("cleanup identity limit exceeded")
        if final:
            final_pids = {item.pid for item in final}
            try:
                signal_cleanup_identities(final)
            finally:
                close_process_identities(final)
            cleaned.update(final_pids)
            remaining = sorted(set(remaining) | final_pids)
        return sorted(cleaned), remaining
