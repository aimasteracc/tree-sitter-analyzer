#!/usr/bin/env python3
"""Strict trace parser and closed classifier for RFC-0022 Linux authority."""

import ast
import hashlib
import os
import posixpath
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any

from rfc0022_strace_classify import (
    causal_order,
    global_write_violation,
    harmless_fd_command,
    is_nonfilesystem,
    mapping_targets,
    page_length,
    reject_ambiguous_state_transition,
    validate_child_start_times,
    validate_trace_start_times,
    writeback_advice_violations,
)
from rfc0022_strace_model import AuthorityError, TraceCall, Violation
from rfc0022_strace_paths import classify_unix_bind
from rfc0022_strace_state import ProcessState, child_pid, process_graph
from rfc0022_strace_syntax import descriptor_path, split_arguments

TRACE_NAME = re.compile(r"^trace\.([1-9][0-9]*)$")
TIMESTAMP_RE = re.compile(r"^(\d+\.\d+)\s+(.*)$")
SYSCALL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\((.*)\)\s+=\s+(.+)$")
UNFINISHED_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\((.*)<unfinished \.\.\.>$")
RESUMED_RE = re.compile(r"^<\.\.\. ([A-Za-z_][A-Za-z0-9_]*) resumed>(.*)$")
TERMINAL_RE = re.compile(r"^\+\+\+ (?:exited with \d+|killed by .+) \+\+\+$")

DIRFD_AT_ZERO = frozenset(
    "fchmodat fchownat futimesat mkdirat mknodat openat openat2 unlinkat utimensat".split()
)
DIRFD_PAIRS = frozenset("linkat move_mount renameat renameat2".split())
ParsedTrace = tuple[list[TraceCall], dict[str, Any], Decimal]


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


def _decode_string_array(value: str) -> list[str]:
    try:
        decoded = ast.literal_eval(value)
    except (SyntaxError, ValueError) as exc:
        raise AuthorityError("exec argv is not an exact string array") from exc
    if not isinstance(decoded, list) or not all(
        isinstance(item, str) for item in decoded
    ):
        raise AuthorityError("exec argv is not an exact string array")
    return decoded


def _result_succeeded(result: str) -> bool:
    normalized = result.lstrip()
    if normalized.startswith("-1"):
        return False
    if normalized.startswith("?"):
        raise AuthorityError("state-bearing syscall result is not exact")
    return True


def _resolve_path(call: TraceCall, index: int, cwd: Path) -> str:
    if index >= len(call.arguments):
        raise AuthorityError(f"{call.syscall} omitted path argument {index}")
    raw = _decode_c_string(call.arguments[index])
    path = PurePosixPath(raw)
    if path.is_absolute():
        return posixpath.normpath(raw)
    base = cwd.as_posix()
    dirfd_index = None
    if call.syscall in DIRFD_AT_ZERO and index == 1:
        dirfd_index = 0
    elif call.syscall in DIRFD_PAIRS and index in {1, 3}:
        dirfd_index = index - 1
    elif call.syscall == "symlinkat" and index == 2:
        dirfd_index = 1
    if dirfd_index is not None:
        dirfd = call.arguments[dirfd_index]
        annotation = descriptor_path(dirfd)
        if annotation is not None:
            base = annotation
        elif not dirfd.startswith("AT_FDCWD"):
            raise AuthorityError(f"{call.syscall} has unannotated dirfd")
    return posixpath.normpath(posixpath.join(base, raw))


def _parse_trace(path: Path, pid: int) -> ParsedTrace:
    raw = path.read_bytes()
    if not raw or not raw.endswith(b"\n"):
        raise AuthorityError(f"trace.{pid} is empty or truncated")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise AuthorityError(f"trace.{pid} is not UTF-8") from exc
    calls: list[TraceCall] = []
    pending: tuple[str, str, int, str] | None = None
    terminals: list[tuple[int, str]] = []
    previous_timestamp: Decimal | None = None
    first_timestamp = Decimal(0)
    for lineno, raw_line in enumerate(lines, start=1):
        timestamp_match = TIMESTAMP_RE.match(raw_line)
        if timestamp_match is None:
            raise AuthorityError(f"trace.{pid}:{lineno} lacks a timestamp")
        timestamp, body = timestamp_match.groups()
        try:
            numeric_timestamp = Decimal(timestamp)
        except InvalidOperation as exc:
            raise AuthorityError(
                f"trace.{pid}:{lineno} has an invalid timestamp"
            ) from exc
        if previous_timestamp is not None and numeric_timestamp < previous_timestamp:
            raise AuthorityError(f"trace.{pid}:{lineno} timestamps moved backwards")
        if lineno == 1:
            first_timestamp = numeric_timestamp
        previous_timestamp = numeric_timestamp
        if TERMINAL_RE.match(body):
            terminals.append((lineno, body))
            continue
        if body.startswith("--- ") and body.endswith(" ---"):
            continue
        unfinished = UNFINISHED_RE.match(body)
        if unfinished:
            if pending is not None:
                raise AuthorityError(f"trace.{pid} has nested unfinished syscalls")
            pending = (unfinished.group(1), unfinished.group(2), lineno, timestamp)
            continue
        resumed = RESUMED_RE.match(body)
        if pending is not None and resumed is None:
            raise AuthorityError(
                f"trace.{pid}:{lineno} has a syscall before the pending resume"
            )
        started_timestamp = timestamp
        if resumed:
            if pending is None or pending[0] != resumed.group(1):
                raise AuthorityError(f"trace.{pid}:{lineno} has an unmatched resume")
            body = f"{pending[0]}({pending[1]}{resumed.group(2)}"
            started_timestamp = pending[3]
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
                split_arguments(arguments),
                result.strip(),
                started_timestamp,
            )
        )
    if pending is not None:
        raise AuthorityError(f"trace.{pid}:{pending[2]} has no resumed syscall")
    if len(terminals) != 1 or terminals[0][0] != len(lines):
        raise AuthorityError(f"trace.{pid} lacks one final terminal marker")
    digest = hashlib.sha256(raw).hexdigest()
    metadata = {"pid": pid, "sha256": digest, "terminal": terminals[0][1]}
    return calls, metadata, first_timestamp


def _open_target(call: TraceCall, cwd: Path) -> str:
    path_index = {"open": 0, "openat": 1, "openat2": 1}.get(call.syscall)
    result_annotation = (
        descriptor_path(call.result) if _result_succeeded(call.result) else None
    )
    if result_annotation is not None:
        return result_annotation
    if path_index is None:
        return "<file-handle>"
    return _resolve_path(call, path_index, cwd)


def classify_calls(
    calls: list[TraceCall],
    policy: dict[str, Any],
    initial_cwd: Path,
    trace_pids: set[int],
    trace_starts: dict[int, Decimal] | None = None,
) -> tuple[list[Violation], int, dict[int, tuple[int, TraceCall]]]:
    process_syscalls = set(policy["process_syscalls"])
    root, edges = process_graph(calls, trace_pids, process_syscalls)
    validate_child_start_times(calls, edges)
    if trace_starts is not None:
        validate_trace_start_times(trace_starts, edges)
    state = ProcessState(root, initial_cwd)
    violations: list[Violation] = []
    open_names = {"open", "openat", "openat2", "open_by_handle_at"}
    ordered = causal_order(calls, process_syscalls)
    state_transitions = {
        "chdir",
        "execve",
        "execveat",
        "fchdir",
        "mmap",
        "mmap2",
        "munmap",
    }
    for call in ordered:
        args = call.arguments
        if call.syscall in state_transitions and _result_succeeded(call.result):
            reject_ambiguous_state_transition(call, calls, state, policy)
        child = child_pid(call, process_syscalls)
        if child is not None:
            state.spawn(
                call.pid,
                child,
                "|".join(args),
                shares_vm=call.syscall == "vfork",
            )
        cwd = state.cwd(call.pid)
        if call.syscall in {"execve", "execveat"} and _result_succeeded(call.result):
            state.exec(call.pid)
        if call.syscall == "chdir" and _result_succeeded(call.result):
            state.chdir(call.pid, Path(_resolve_path(call, 0, cwd)))
        elif call.syscall == "fchdir" and _result_succeeded(call.result):
            path = descriptor_path(args[0])
            if not path or is_nonfilesystem(path, policy):
                raise AuthorityError("fchdir descriptor provenance is unknown")
            state.chdir(call.pid, Path(path))
        global_violation = global_write_violation(call, policy)
        if global_violation is not None:
            violations.append(global_violation)
            continue
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
            result = (
                descriptor_path(call.result) if _result_succeeded(call.result) else None
            )
            if matched and not (result and is_nonfilesystem(result, policy)):
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
            annotation = descriptor_path(args[index])
            if annotation is None:
                raise AuthorityError(f"{call.syscall} has unannotated destination fd")
            if not is_nonfilesystem(annotation, policy):
                violations.append(
                    Violation(
                        call.timestamp,
                        call.pid,
                        call.line,
                        call.syscall,
                        "descriptor_write",
                        annotation,
                        call.result,
                    )
                )
            continue
        if call.syscall in {"mmap", "mmap2"}:
            if len(args) < 6:
                raise AuthorityError("mmap arguments are incomplete")
            try:
                length = page_length(int(args[1], 0), policy)
            except ValueError as exc:
                raise AuthorityError("mmap length is not exact") from exc
            annotation = descriptor_path(args[4])
            anonymous = "MAP_ANONYMOUS" in args[3] or args[4].startswith("-1")
            if not anonymous and annotation is None:
                raise AuthorityError("mmap filesystem fd provenance is unknown")
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
                if not is_nonfilesystem(target, policy):
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
        writeback_advice = {"MADV_DONTNEED", "MADV_PAGEOUT", "MADV_REMOVE"}
        if call.syscall == "madvise" and len(args) < 3:
            raise AuthorityError("madvise arguments are incomplete")
        if call.syscall == "madvise" and args[2] in writeback_advice:
            try:
                address = int(args[0], 0)
                length = page_length(int(args[1], 0), policy)
            except ValueError as exc:
                raise AuthorityError("madvise range is not exact") from exc
            try:
                records = state.covering(call.pid, address, length)
            except AuthorityError:
                if args[2] == "MADV_DONTNEED":
                    raise
                records = []
            violations.extend(writeback_advice_violations(call, records, policy))
            continue
        if call.syscall in {"mprotect", "msync", "munmap"}:
            required_arguments = 2 if call.syscall == "munmap" else 3
            if len(args) < required_arguments:
                raise AuthorityError(f"{call.syscall} arguments are incomplete")
            try:
                address = int(args[0], 0)
                length = page_length(int(args[1], 0), policy)
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
                for target in mapping_targets(records, policy):
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
            annotation = descriptor_path(args[0]) if args else None
            if annotation is None:
                raise AuthorityError(f"{call.syscall} has unannotated fd")
            if not is_nonfilesystem(annotation, policy):
                command = args[1] if len(args) > 1 else ""
                harmless = harmless_fd_command(call, command, policy)
                if not harmless:
                    raise AuthorityError(
                        f"unclassified {call.syscall} on filesystem fd"
                    )
            continue
        if call.syscall in policy["safe_syscalls"] or call.syscall in process_syscalls:
            continue
        raise AuthorityError(f"unknown traced syscall: {call.syscall}")
    violations.sort(key=lambda item: (Decimal(item.timestamp), item.pid, item.line))
    return violations, root, edges


def parse_trace_directory(
    trace_dir: Path,
    policy: dict[str, Any],
    initial_cwd: Path,
    expected_executable: str | None = None,
    expected_argv: list[str] | None = None,
    minimum_root_execs: int = 1,
) -> tuple[list[Violation], list[dict[str, Any]], set[int]]:
    paths: dict[int, Path] = {}
    for path in trace_dir.iterdir():
        match = TRACE_NAME.fullmatch(path.name)
        if match is None or not path.is_file() or path.is_symlink():
            raise AuthorityError(f"unexpected trace directory entry: {path.name}")
        pid = int(match.group(1))
        paths[pid] = path
    if not paths:
        raise AuthorityError("strace produced no per-process trace files")
    all_calls: list[TraceCall] = []
    metadata_by_pid: dict[int, dict[str, Any]] = {}
    seen: dict[int, Decimal] = {}
    for pid, path in sorted(paths.items()):
        calls, trace_metadata, first_timestamp = _parse_trace(path, pid)
        all_calls.extend(calls)
        metadata_by_pid[pid] = trace_metadata
        seen[pid] = first_timestamp
    pids = set(paths)
    violations, root, edges = classify_calls(all_calls, policy, initial_cwd, pids, seen)
    if expected_executable is not None:
        expected = os.path.realpath(expected_executable)
        successful_execs = [
            call
            for call in all_calls
            if call.pid == root
            and call.syscall in {"execve", "execveat"}
            and _result_succeeded(call.result)
        ]
        if len(successful_execs) < minimum_root_execs:
            raise AuthorityError("root trace lacks mandatory exec transitions")
        final_exec = successful_execs[-1]
        path_index = 0 if final_exec.syscall == "execve" else 1
        actual = (
            _decode_c_string(final_exec.arguments[path_index])
            if path_index < len(final_exec.arguments)
            else ""
        )
        if not PurePosixPath(actual).is_absolute():
            raise AuthorityError("final root exec path is not absolute")
        if os.path.realpath(actual) != expected:
            raise AuthorityError("final root exec does not match the expected target")
        if expected_argv is not None:
            argv_index = 1 if final_exec.syscall == "execve" else 2
            actual_argv = (
                _decode_string_array(final_exec.arguments[argv_index])
                if argv_index < len(final_exec.arguments)
                else []
            )
            if actual_argv != expected_argv:
                raise AuthorityError("final root exec argv does not match the target")
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
