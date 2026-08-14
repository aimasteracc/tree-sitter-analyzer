#!/usr/bin/env python3
"""Closed policy helpers for RFC-0022 strace classification."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from rfc0022_strace_model import AuthorityError, TraceCall, Violation
from rfc0022_strace_state import ProcessState, child_pid


def _timestamp_interval(call: TraceCall) -> tuple[Decimal, Decimal]:
    try:
        start = Decimal(call.started_timestamp or call.timestamp)
        end = Decimal(call.timestamp)
    except InvalidOperation as exc:
        raise AuthorityError("syscall timestamp is not numeric") from exc
    if start > end:
        raise AuthorityError("syscall result predates its entry")
    return start, end


def causal_order(calls: list[TraceCall], process_syscalls: set[str]) -> list[TraceCall]:
    buckets: dict[Decimal, list[TraceCall]] = {}
    for call in calls:
        start, end = _timestamp_interval(call)
        order = start if call.syscall in process_syscalls else end
        buckets.setdefault(order, []).append(call)
    ordered: list[TraceCall] = []
    for timestamp in sorted(buckets):
        group = buckets[timestamp]
        dependencies: dict[int, set[int]] = {
            index: set() for index in range(len(group))
        }
        by_pid: dict[int, list[int]] = {}
        for index, call in enumerate(group):
            by_pid.setdefault(call.pid, []).append(index)
        for indices in by_pid.values():
            indices.sort(key=lambda index: group[index].line)
            for before, after in zip(indices, indices[1:], strict=False):
                dependencies[after].add(before)
        for index, call in enumerate(group):
            child = child_pid(call, process_syscalls)
            if child is None:
                continue
            for child_index in by_pid.get(child, []):
                dependencies[child_index].add(index)
        emitted: set[int] = set()
        while len(emitted) < len(group):
            ready = [
                index
                for index, required in dependencies.items()
                if index not in emitted and required <= emitted
            ]
            if len(ready) != 1:
                raise AuthorityError(
                    f"ambiguous cross-process syscall entry order at {timestamp}"
                )
            current = ready[0]
            emitted.add(current)
            ordered.append(group[current])
    return ordered


def validate_child_start_times(
    calls: list[TraceCall], edges: dict[int, tuple[int, TraceCall]]
) -> None:
    creation_starts = {
        child: _timestamp_interval(creation)[0]
        for child, (_, creation) in edges.items()
    }
    for call in calls:
        creation_start = creation_starts.get(call.pid)
        if creation_start is not None and _timestamp_interval(call)[0] < creation_start:
            raise AuthorityError("child syscall predates process creation entry")


def reject_ambiguous_state_transition(
    call: TraceCall,
    calls: list[TraceCall],
    state: ProcessState,
    process_syscalls: set[str],
) -> None:
    mapping_transition = call.syscall in {
        "execve",
        "execveat",
        "mmap",
        "mmap2",
        "munmap",
    }
    cwd_transition = call.syscall in {"chdir", "execve", "execveat", "fchdir"}
    if not mapping_transition and not cwd_transition:
        return
    start, end = _timestamp_interval(call)
    for other in calls:
        if other.pid == call.pid:
            continue
        other_start, other_end = _timestamp_interval(other)
        if start == end and other_start == other_end:
            continue
        if max(start, other_start) > min(end, other_end):
            continue
        if child_pid(other, process_syscalls) == call.pid:
            continue
        if mapping_transition and state.shares_mapping(call.pid, other.pid):
            raise AuthorityError("ambiguous cross-process mapping transition")
        if cwd_transition and state.shares_cwd(call.pid, other.pid):
            raise AuthorityError("ambiguous cross-process cwd transition")


def is_nonfilesystem(annotation: str, policy: dict[str, Any]) -> bool:
    return any(
        annotation.startswith(prefix) for prefix in policy["nonfilesystem_fd_prefixes"]
    )


def page_length(length: int, policy: dict[str, Any]) -> int:
    page_size = int(policy["page_size"])
    return ((length + page_size - 1) // page_size) * page_size


def mapping_targets(
    records: list[tuple[int, int, bool, str | None]], policy: dict[str, Any]
) -> list[str]:
    return sorted(
        {
            target
            for _, _, shared, target in records
            if shared and target is not None and not is_nonfilesystem(target, policy)
        }
    )


def writeback_advice_violations(
    call: TraceCall,
    records: list[tuple[int, int, bool, str | None]],
    policy: dict[str, Any],
) -> list[Violation]:
    advice = call.arguments[2]
    shared_targets = mapping_targets(records, policy)
    all_targets = sorted(
        {
            target
            for _, _, _, target in records
            if target is not None and not is_nonfilesystem(target, policy)
        }
    )
    targets = all_targets if advice == "MADV_REMOVE" else shared_targets
    violations = [
        Violation(
            call.timestamp,
            call.pid,
            call.line,
            call.syscall,
            "shared_mapping_writeback",
            target,
            call.result,
            advice,
        )
        for target in targets
    ]
    needs_global = advice in {"MADV_PAGEOUT", "MADV_REMOVE"} and (
        not records
        or any(
            not shared or target is None or is_nonfilesystem(target, policy)
            for _, _, shared, target in records
        )
    )
    if needs_global:
        violations.append(
            Violation(
                call.timestamp,
                call.pid,
                call.line,
                call.syscall,
                "global_writeback",
                f"<memory-{advice.removeprefix('MADV_').lower()}>",
                call.result,
                advice,
            )
        )
    return violations


def harmless_fd_command(call: TraceCall, command: str, policy: dict[str, Any]) -> bool:
    if call.syscall == "fcntl":
        return command in policy["safe_fcntl_commands"]
    return command in policy["safe_ioctl_commands"] or (
        command in policy["enotty_ioctl_commands"]
        and call.result.startswith("-1 ENOTTY")
    )


def global_write_violation(call: TraceCall, policy: dict[str, Any]) -> Violation | None:
    if call.syscall not in policy["global_write_syscalls"]:
        return None
    return Violation(
        call.timestamp,
        call.pid,
        call.line,
        call.syscall,
        "global_writeback",
        "<all-filesystems>",
        call.result,
    )
