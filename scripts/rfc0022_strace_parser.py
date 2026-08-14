#!/usr/bin/env python3
"""Strict trace parser and closed classifier for RFC-0022 Linux authority."""

from __future__ import annotations

import ast
import hashlib
import os
import re
from pathlib import Path
from typing import Any

from rfc0022_strace_model import AuthorityError, TraceCall, Violation
from rfc0022_strace_paths import classify_unix_bind
from rfc0022_strace_state import ProcessState, child_pid, process_graph

TRACE_NAME = re.compile(r"^trace\.(\d+)$")
TIMESTAMP_RE = re.compile(r"^(\d+\.\d+)\s+(.*)$")
SYSCALL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\((.*)\)\s+=\s+(.+)$")
UNFINISHED_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\((.*)<unfinished \.\.\.>$")
RESUMED_RE = re.compile(r"^<\.\.\. ([A-Za-z_][A-Za-z0-9_]*) resumed>(.*)$")
TERMINAL_RE = re.compile(r"^\+\+\+ (?:exited with \d+|killed by .+) \+\+\+$")
FD_RE = re.compile(r"^(?:AT_FDCWD|-?\d+)(?:<([^>]*)>)?")
RESULT_FD_RE = re.compile(r"^-?\d+(?:<([^>]*)>)?")

DIRFD_AT_ZERO = frozenset(
    "fchmodat fchownat futimesat mkdirat mknodat openat openat2 unlinkat utimensat".split()
)
DIRFD_PAIRS = frozenset("linkat move_mount renameat renameat2".split())


def _split_arguments(text: str) -> tuple[str, ...]:
    values: list[str] = []
    start = 0
    stack: list[str] = []
    quote = False
    escaped = False
    pairs = {"(": ")", "[": "]", "{": "}"}
    for index, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = False
            continue
        if char == '"':
            quote = True
        elif char in pairs:
            stack.append(pairs[char])
        elif char in pairs.values():
            if not stack or stack.pop() != char:
                raise AuthorityError("unbalanced strace argument structure")
        elif char == "," and not stack:
            values.append(text[start:index].strip())
            start = index + 1
    if quote or stack:
        raise AuthorityError("truncated strace argument structure")
    tail = text[start:].strip()
    if tail or text:
        values.append(tail)
    return tuple(values)


def _decode_c_string(value: str) -> str:
    if not value.startswith('"'):
        raise AuthorityError(f"expected unabbreviated path string, got {value!r}")
    try:
        decoded = ast.literal_eval(value)
    except (SyntaxError, ValueError) as exc:
        raise AuthorityError(f"invalid strace C string: {value!r}") from exc
    if not isinstance(decoded, str) or "..." in value[-5:]:
        raise AuthorityError("truncated or non-string strace path")
    return decoded


def _fd_annotation(value: str) -> str | None:
    match = FD_RE.match(value)
    if match is None:
        raise AuthorityError(f"expected decoded descriptor, got {value!r}")
    return match.group(1)


def _is_nonfilesystem(annotation: str, policy: dict[str, Any]) -> bool:
    value = annotation.removeprefix("/")
    return any(
        annotation.startswith(prefix) or value.startswith(prefix)
        for prefix in policy["nonfilesystem_fd_prefixes"]
    )


def _result_succeeded(result: str) -> bool:
    return not result.lstrip().startswith("-1")


def _resolve_path(call: TraceCall, index: int, cwd: Path) -> str:
    if index >= len(call.arguments):
        raise AuthorityError(f"{call.syscall} omitted path argument {index}")
    raw = _decode_c_string(call.arguments[index])
    path = Path(raw)
    if path.is_absolute():
        return os.path.normpath(raw)
    base = cwd
    dirfd_index = None
    if call.syscall in DIRFD_AT_ZERO and index == 1:
        dirfd_index = 0
    elif call.syscall in DIRFD_PAIRS and index in {1, 3}:
        dirfd_index = index - 1
    elif call.syscall == "symlinkat" and index == 2:
        dirfd_index = 1
    if dirfd_index is not None:
        dirfd = call.arguments[dirfd_index]
        annotation = _fd_annotation(dirfd)
        if annotation is not None:
            base = Path(annotation.removesuffix(" (deleted)"))
        elif not dirfd.startswith("AT_FDCWD"):
            raise AuthorityError(f"{call.syscall} has unannotated dirfd")
    return os.path.normpath(os.fspath(base / path))


def _parse_trace(path: Path, pid: int) -> tuple[list[TraceCall], dict[str, Any]]:
    raw = path.read_bytes()
    if not raw or not raw.endswith(b"\n"):
        raise AuthorityError(f"trace.{pid} is empty or truncated")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise AuthorityError(f"trace.{pid} is not UTF-8") from exc
    calls: list[TraceCall] = []
    pending: tuple[str, str, int] | None = None
    terminals: list[tuple[int, str]] = []
    for lineno, raw_line in enumerate(lines, start=1):
        timestamp_match = TIMESTAMP_RE.match(raw_line)
        if timestamp_match is None:
            raise AuthorityError(f"trace.{pid}:{lineno} lacks a timestamp")
        timestamp, body = timestamp_match.groups()
        if TERMINAL_RE.match(body):
            terminals.append((lineno, body))
            continue
        if body.startswith("--- ") and body.endswith(" ---"):
            continue
        unfinished = UNFINISHED_RE.match(body)
        if unfinished:
            if pending is not None:
                raise AuthorityError(f"trace.{pid} has nested unfinished syscalls")
            pending = (unfinished.group(1), unfinished.group(2), lineno)
            continue
        resumed = RESUMED_RE.match(body)
        if resumed:
            if pending is None or pending[0] != resumed.group(1):
                raise AuthorityError(f"trace.{pid}:{lineno} has an unmatched resume")
            body = f"{pending[0]}({pending[1]}{resumed.group(2)}"
            pending = None
        syscall_match = SYSCALL_RE.match(body)
        if syscall_match is None:
            raise AuthorityError(f"trace.{pid}:{lineno} is unparseable: {body!r}")
        name, arguments, result = syscall_match.groups()
        calls.append(
            TraceCall(
                timestamp,
                pid,
                lineno,
                name,
                _split_arguments(arguments),
                result.strip(),
            )
        )
    if pending is not None:
        raise AuthorityError(f"trace.{pid}:{pending[2]} has no resumed syscall")
    if len(terminals) != 1 or terminals[0][0] != len(lines):
        raise AuthorityError(f"trace.{pid} lacks one final terminal marker")
    metadata = {
        "pid": pid,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "terminal": terminals[0][1],
    }
    return calls, metadata


def _open_target(call: TraceCall, cwd: Path) -> str:
    path_index = {"open": 0, "openat": 1, "openat2": 1}.get(call.syscall)
    result_match = RESULT_FD_RE.match(call.result)
    if result_match and result_match.group(1):
        return result_match.group(1).removesuffix(" (deleted)")
    if path_index is None:
        return "<file-handle>"
    return _resolve_path(call, path_index, cwd)


def _mapping_targets(
    records: list[tuple[int, int, bool, str | None]], policy: dict[str, Any]
) -> list[str]:
    return sorted(
        {
            target
            for _, _, shared, target in records
            if shared and target is not None and not _is_nonfilesystem(target, policy)
        }
    )


def _page_length(length: int, policy: dict[str, Any]) -> int:
    page_size = int(policy["page_size"])
    return ((length + page_size - 1) // page_size) * page_size


def classify_calls(
    calls: list[TraceCall],
    policy: dict[str, Any],
    initial_cwd: Path,
    trace_pids: set[int],
) -> tuple[list[Violation], int, dict[int, tuple[int, TraceCall]]]:
    process_syscalls = set(policy["process_syscalls"])
    root, edges = process_graph(calls, trace_pids, process_syscalls)
    state = ProcessState(root, initial_cwd)
    violations: list[Violation] = []
    open_names = {"open", "openat", "openat2", "open_by_handle_at"}
    ordered = sorted(calls, key=lambda call: (call.timestamp, call.pid, call.line))
    for call in ordered:
        args = call.arguments
        child = child_pid(call, process_syscalls)
        if child is not None:
            state.spawn(call.pid, child, "|".join(args))
        cwd = state.cwd(call.pid)
        if call.syscall in {"execve", "execveat"} and _result_succeeded(call.result):
            state.exec(call.pid)
        if call.syscall == "chdir" and _result_succeeded(call.result):
            state.chdir(call.pid, Path(_resolve_path(call, 0, cwd)))
        elif call.syscall == "fchdir" and _result_succeeded(call.result):
            annotation = _fd_annotation(args[0])
            if annotation is None or _is_nonfilesystem(annotation, policy):
                raise AuthorityError("fchdir descriptor provenance is unknown")
            state.chdir(call.pid, Path(annotation))
        if (
            call.syscall in policy["async_syscalls"]
            or call.syscall in policy["always_violation_syscalls"]
        ):
            violations.append(
                Violation(
                    call.timestamp,
                    call.pid,
                    call.line,
                    call.syscall,
                    "asynchronous_write_capability",
                    "<kernel-async>",
                    call.result,
                )
            )
            continue
        if call.syscall in open_names:
            flag_index = {"open": 1, "openat": 2, "openat2": 2, "open_by_handle_at": 2}[
                call.syscall
            ]
            if flag_index >= len(args):
                raise AuthorityError(f"{call.syscall} omitted flags")
            flags = args[flag_index]
            matched = sorted(
                flag
                for flag in policy["write_open_flags"]
                if re.search(rf"(?<![A-Z0-9_]){re.escape(flag)}(?![A-Z0-9_])", flags)
            )
            if matched:
                violations.append(
                    Violation(
                        call.timestamp,
                        call.pid,
                        call.line,
                        call.syscall,
                        "write_capable_open",
                        _open_target(call, cwd),
                        call.result,
                        "|".join(matched),
                    )
                )
            continue
        if call.syscall in policy["unix_path_mutators"]:
            violation = classify_unix_bind(call, cwd, _decode_c_string)
            if violation is not None:
                violations.append(violation)
            continue
        target_indices = policy["path_mutators"].get(call.syscall)
        if target_indices:
            for index in target_indices:
                violations.append(
                    Violation(
                        call.timestamp,
                        call.pid,
                        call.line,
                        call.syscall,
                        "pathname_mutation",
                        _resolve_path(call, int(index), cwd),
                        call.result,
                    )
                )
            continue
        if call.syscall in policy["fd_sinks"]:
            index = int(policy["fd_sinks"][call.syscall])
            if index >= len(args):
                raise AuthorityError(f"{call.syscall} omitted destination fd")
            annotation = _fd_annotation(args[index])
            if annotation is None:
                raise AuthorityError(f"{call.syscall} has unannotated destination fd")
            if not _is_nonfilesystem(annotation, policy):
                violations.append(
                    Violation(
                        call.timestamp,
                        call.pid,
                        call.line,
                        call.syscall,
                        "descriptor_write",
                        annotation.removesuffix(" (deleted)"),
                        call.result,
                    )
                )
            continue
        if call.syscall in {"mmap", "mmap2"}:
            if len(args) < 5:
                raise AuthorityError("mmap arguments are incomplete")
            try:
                length = _page_length(int(args[1], 0), policy)
            except ValueError as exc:
                raise AuthorityError("mmap length is not exact") from exc
            annotation = _fd_annotation(args[4])
            anonymous = "MAP_ANONYMOUS" in args[3] or args[4].startswith("-1")
            target = None if anonymous else annotation
            shared = "MAP_SHARED" in args[3]
            result_address = re.match(r"0x([0-9a-fA-F]+)$", call.result)
            if _result_succeeded(call.result) and result_address:
                state.map(
                    call.pid, int(result_address.group(1), 16), length, shared, target
                )
            if shared and "PROT_WRITE" in args[2] and not anonymous:
                if target is None:
                    raise AuthorityError(
                        "shared writable mmap has unknown fd provenance"
                    )
                if not _is_nonfilesystem(target, policy):
                    violations.append(
                        Violation(
                            call.timestamp,
                            call.pid,
                            call.line,
                            call.syscall,
                            "shared_writable_mapping",
                            target,
                            call.result,
                            f"{args[2]}|{args[3]}",
                        )
                    )
            continue
        if call.syscall == "madvise" and len(args) > 2 and "MADV_REMOVE" in args[2]:
            try:
                address = int(args[0], 0)
                length = _page_length(int(args[1], 0), policy)
            except ValueError as exc:
                raise AuthorityError("madvise range is not exact") from exc
            for target in _mapping_targets(
                state.covering(call.pid, address, length), policy
            ):
                violations.append(
                    Violation(
                        call.timestamp,
                        call.pid,
                        call.line,
                        call.syscall,
                        "shared_mapping_remove",
                        target,
                        call.result,
                        args[2],
                    )
                )
            continue
        if call.syscall in {"mprotect", "msync", "munmap"}:
            if len(args) < 2:
                raise AuthorityError(f"{call.syscall} arguments are incomplete")
            try:
                address = int(args[0], 0)
                length = _page_length(int(args[1], 0), policy)
            except ValueError as exc:
                raise AuthorityError(f"{call.syscall} range is not exact") from exc
            if call.syscall == "munmap":
                if _result_succeeded(call.result):
                    state.unmap(call.pid, address, length)
                continue
            needs_write = call.syscall == "msync" or (
                len(args) > 2 and "PROT_WRITE" in args[2]
            )
            if needs_write:
                records = state.covering(call.pid, address, length)
                for target in _mapping_targets(records, policy):
                    violations.append(
                        Violation(
                            call.timestamp,
                            call.pid,
                            call.line,
                            call.syscall,
                            "shared_mapping_write",
                            target,
                            call.result,
                        )
                    )
            continue
        if call.syscall in {"fcntl", "ioctl"}:
            annotation = _fd_annotation(args[0]) if args else None
            if annotation is None:
                raise AuthorityError(f"{call.syscall} has unannotated fd")
            if not _is_nonfilesystem(annotation, policy):
                command = args[1] if len(args) > 1 else ""
                harmless = (
                    call.syscall == "ioctl"
                    and (
                        command in policy["safe_ioctl_commands"]
                        or (
                            command in policy["enotty_ioctl_commands"]
                            and call.result.startswith("-1 ENOTTY")
                        )
                    )
                ) or (
                    call.syscall == "fcntl" and command in policy["safe_fcntl_commands"]
                )
                if not harmless:
                    raise AuthorityError(
                        f"unclassified {call.syscall} on filesystem fd"
                    )
            continue
        if call.syscall in policy["safe_syscalls"] or call.syscall in process_syscalls:
            continue
        raise AuthorityError(f"unknown traced syscall: {call.syscall}")
    return violations, root, edges


def parse_trace_directory(
    trace_dir: Path,
    policy: dict[str, Any],
    initial_cwd: Path,
    expected_executable: str | None = None,
) -> tuple[list[Violation], list[dict[str, Any]], set[int]]:
    paths: list[tuple[int, Path]] = []
    for path in trace_dir.iterdir():
        match = TRACE_NAME.match(path.name)
        if match and path.is_file():
            paths.append((int(match.group(1)), path))
    if not paths:
        raise AuthorityError("strace produced no per-process trace files")
    all_calls: list[TraceCall] = []
    metadata_by_pid: dict[int, dict[str, Any]] = {}
    for pid, path in sorted(paths):
        calls, trace_metadata = _parse_trace(path, pid)
        all_calls.extend(calls)
        metadata_by_pid[pid] = trace_metadata
    pids = {pid for pid, _ in paths}
    violations, root, edges = classify_calls(all_calls, policy, initial_cwd, pids)
    if expected_executable is not None:
        expected = os.path.realpath(expected_executable)
        successful_execs = [
            call
            for call in all_calls
            if call.pid == root
            and call.syscall in {"execve", "execveat"}
            and _result_succeeded(call.result)
        ]
        matched = False
        for call in successful_execs:
            path_index = 0 if call.syscall == "execve" else 1
            if path_index < len(call.arguments):
                actual = _decode_c_string(call.arguments[path_index])
                matched = matched or os.path.realpath(actual) == expected
        if not matched:
            raise AuthorityError("root trace lacks the expected successful target exec")
    metadata: list[dict[str, Any]] = []
    for pid in sorted(pids):
        parent = edges.get(pid)
        metadata.append(
            {
                **metadata_by_pid[pid],
                "role": "root" if pid == root else "descendant",
                "parent_pid": None if parent is None else parent[0],
            }
        )
    return violations, metadata, pids
