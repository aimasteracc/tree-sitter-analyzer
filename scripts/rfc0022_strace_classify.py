#!/usr/bin/env python3
"""Closed policy helpers for RFC-0022 strace classification."""

from __future__ import annotations

from typing import Any

from rfc0022_strace_model import TraceCall, Violation


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
