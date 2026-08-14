"""Independent raw-line binding checks for RFC-0022 live evidence."""

from __future__ import annotations

import json
import re

import pytest


def _assert_mapping_target_binding(
    target: str, raw_line: str, prior_lines: list[str]
) -> None:
    request = re.search(r" (?:madvise|mprotect|msync)\((0x[0-9a-f]+), (\d+),", raw_line)
    if request is None:
        raise AssertionError("mapping event lacks an exact address range")
    start = int(request.group(1), 16)
    length = int(request.group(2))
    bindings: list[tuple[int, int]] = []
    for line in prior_lines:
        if " mmap" not in line or f"<{target}>" not in line:
            continue
        mapping = re.search(r" mmap(?:2)?\([^,]+, (\d+), .+\) = (0x[0-9a-f]+)$", line)
        if mapping is not None:
            bindings.append((int(mapping.group(2), 16), int(mapping.group(1))))
    assert any(
        base <= start and start + length <= base + size for base, size in bindings
    )


def assert_event_raw_binding(
    event: dict[str, object], raw_line: str, prior_lines: list[str] | None = None
) -> None:
    assert raw_line.startswith(f"{event['timestamp']} {event['syscall']}(")
    assert raw_line.endswith(f" = {event['result']}")
    target = str(event["target"]).removesuffix(" (deleted)")
    direct_target = json.dumps(target) in raw_line or f"<{target}>" in raw_line
    if direct_target is False:
        if prior_lines is None:
            raise AssertionError("address-based event lacks mapping history")
        _assert_mapping_target_binding(target, raw_line, prior_lines)
    flags = event["flags"]
    if flags is not None:
        assert all(token in raw_line for token in str(flags).split("|"))
    if event["syscall"] == "msync":
        assert ", MS_SYNC)" in raw_line
    if event["syscall"] == "mprotect":
        assert "PROT_WRITE" in raw_line


def test_raw_event_binding_rejects_unrelated_trace_line() -> None:
    event = {
        "flags": "O_CREAT|O_WRONLY",
        "result": "3</case/native-created.txt>",
        "syscall": "openat",
        "target": "/case/native-created.txt",
        "timestamp": "1700000000.000001",
    }
    unrelated = (
        '1700000000.000001 openat(AT_FDCWD</case>, "unrelated.txt", O_RDONLY) '
        "= 3</case/unrelated.txt>"
    )
    with pytest.raises(AssertionError):
        assert_event_raw_binding(event, unrelated)
