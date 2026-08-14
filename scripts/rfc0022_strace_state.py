#!/usr/bin/env python3
"""Process, cwd, and mapping provenance for RFC-0022 strace classification."""

from __future__ import annotations

import re
from pathlib import Path

from rfc0022_strace_model import AuthorityError, TraceCall

Mapping = tuple[int, int, bool, str | None]


class ProcessState:
    """Track fork/clone state without guessing for unknown processes or gaps."""

    def __init__(self, root_pid: int, initial_cwd: Path) -> None:
        self._cwd_space_by_pid = {root_pid: root_pid}
        self._cwd_spaces = {root_pid: initial_cwd}
        self._map_space_by_pid = {root_pid: root_pid}
        self._map_spaces: dict[int, list[Mapping]] = {root_pid: []}
        self._next_space = -1

    def _fresh_space(self) -> int:
        space = self._next_space
        self._next_space -= 1
        return space

    def cwd(self, pid: int) -> Path:
        try:
            return self._cwd_spaces[self._cwd_space_by_pid[pid]]
        except KeyError as exc:
            raise AuthorityError(f"process state missing for pid {pid}") from exc

    def chdir(self, pid: int, cwd: Path) -> None:
        try:
            self._cwd_spaces[self._cwd_space_by_pid[pid]] = cwd
        except KeyError as exc:
            raise AuthorityError(f"cwd state missing for pid {pid}") from exc

    def spawn(
        self, parent: int, child: int, flags: str, *, shares_vm: bool = False
    ) -> None:
        if child in self._cwd_space_by_pid or child in self._map_space_by_pid:
            raise AuthorityError(f"duplicate process state for pid {child}")
        try:
            parent_cwd_space = self._cwd_space_by_pid[parent]
            parent_map_space = self._map_space_by_pid[parent]
        except KeyError as exc:
            raise AuthorityError(f"parent state missing for pid {parent}") from exc
        if "CLONE_FS" in flags:
            self._cwd_space_by_pid[child] = parent_cwd_space
        else:
            cwd_space = self._fresh_space()
            self._cwd_space_by_pid[child] = cwd_space
            self._cwd_spaces[cwd_space] = self._cwd_spaces[parent_cwd_space]
        if "CLONE_VM" in flags or shares_vm:
            self._map_space_by_pid[child] = parent_map_space
        else:
            map_space = self._fresh_space()
            self._map_space_by_pid[child] = map_space
            self._map_spaces[map_space] = list(self._map_spaces[parent_map_space])

    def exec(self, pid: int) -> None:
        cwd = self.cwd(pid)
        cwd_space = self._fresh_space()
        map_space = self._fresh_space()
        self._cwd_space_by_pid[pid] = cwd_space
        self._cwd_spaces[cwd_space] = cwd
        self._map_space_by_pid[pid] = map_space
        self._map_spaces[map_space] = []

    def _space(self, pid: int) -> tuple[int, list[Mapping]]:
        try:
            key = self._map_space_by_pid[pid]
            return key, self._map_spaces[key]
        except KeyError as exc:
            raise AuthorityError(f"mapping state missing for pid {pid}") from exc

    @staticmethod
    def _remove_range(records: list[Mapping], start: int, length: int) -> list[Mapping]:
        end = start + length
        remaining: list[Mapping] = []
        for record_start, record_length, shared, target in records:
            record_end = record_start + record_length
            if record_end <= start or end <= record_start:
                remaining.append((record_start, record_length, shared, target))
                continue
            if record_start < start:
                remaining.append((record_start, start - record_start, shared, target))
            if end < record_end:
                remaining.append((end, record_end - end, shared, target))
        return sorted(remaining)

    def map(
        self,
        pid: int,
        start: int,
        length: int,
        shared: bool,
        target: str | None,
    ) -> None:
        key, records = self._space(pid)
        records = self._remove_range(records, start, length)
        records.append((start, length, shared, target))
        self._map_spaces[key] = sorted(records)

    def unmap(self, pid: int, start: int, length: int) -> None:
        key, records = self._space(pid)
        self._map_spaces[key] = self._remove_range(records, start, length)

    def covering(self, pid: int, start: int, length: int) -> list[Mapping]:
        _, records = self._space(pid)
        end = start + length
        overlaps = [
            record
            for record in records
            if start < record[0] + record[1] and record[0] < end
        ]
        cursor = start
        for record_start, record_length, _, _ in overlaps:
            if record_start > cursor:
                raise AuthorityError("mapping provenance has an uncovered gap")
            cursor = max(cursor, record_start + record_length)
        if cursor < end:
            raise AuthorityError(
                "mapping provenance does not cover the requested range"
            )
        return overlaps


def child_pid(call: TraceCall, process_syscalls: set[str]) -> int | None:
    if call.syscall not in process_syscalls:
        return None
    result = call.result.lstrip()
    if result.startswith("-1"):
        return None
    match = re.fullmatch(r"(\d+)", result)
    if match is None:
        raise AuthorityError("process creation result is not an exact child pid")
    return int(match.group(1))


def process_graph(
    calls: list[TraceCall], trace_pids: set[int], process_syscalls: set[str]
) -> tuple[int, dict[int, tuple[int, TraceCall]]]:
    edges: dict[int, tuple[int, TraceCall]] = {}
    for call in calls:
        child = child_pid(call, process_syscalls)
        if child is None:
            continue
        if child in edges:
            raise AuthorityError(f"duplicate creation edge for pid {child}")
        edges[child] = (call.pid, call)
    missing = set(edges) - trace_pids
    if missing:
        raise AuthorityError(f"child trace files missing: {sorted(missing)}")
    roots = trace_pids - set(edges)
    if len(roots) != 1:
        raise AuthorityError(f"trace graph must have exactly one root: {sorted(roots)}")
    root = next(iter(roots))
    if any(parent not in trace_pids for parent, _ in edges.values()):
        raise AuthorityError("trace graph contains an unknown parent")
    return root, edges
