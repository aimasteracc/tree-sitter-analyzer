"""Independent raw-line binding checks for RFC-0022 live evidence."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from pathlib import Path

import pytest


def _assert_mapping_target_binding(
    target: str, raw_line: str, prior_lines: list[str]
) -> None:
    request = re.search(r" (?:madvise|mprotect|msync)\((0x[0-9a-f]+), (\d+),", raw_line)
    if request is None:
        raise AssertionError("mapping event lacks an exact address range")
    start = int(request.group(1), 16)
    end = start + int(request.group(2))
    for line in reversed(prior_lines):
        if re.search(r" execve(?:at)?\(.+\) = 0$", line):
            break
        if " mremap(" in line:
            raise AssertionError("mapping history contains unmodeled mremap")
        removal = re.search(r" munmap\((0x[0-9a-f]+), (\d+)\) = 0$", line)
        if removal is not None:
            base = int(removal.group(1), 16)
            limit = base + int(removal.group(2))
            if start < limit and base < end:
                raise AssertionError("mapping was removed before the event")
        mapping = re.search(r" mmap(?:2)?\([^,]+, (\d+), .+\) = (0x[0-9a-f]+)$", line)
        if mapping is None:
            continue
        base = int(mapping.group(2), 16)
        limit = base + int(mapping.group(1))
        if start < limit and base < end:
            assert base <= start and end <= limit
            assert f"<{target}>" in line
            return
    raise AssertionError("mapping event lacks live file provenance")


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


def _msync_event() -> dict[str, object]:
    return {
        "flags": None,
        "result": "0",
        "syscall": "msync",
        "target": "/case/fixture.txt",
        "timestamp": "1700000000.000002",
    }


def test_msync_binding_uses_prior_exact_mmap_interval() -> None:
    mapping = (
        "1700000000.000001 mmap(NULL, 4096, PROT_READ|PROT_WRITE, MAP_SHARED, "
        "3</case/fixture.txt>, 0) = 0x7f000000"
    )
    raw = "1700000000.000002 msync(0x7f000800, 8, MS_SYNC) = 0"
    assert_event_raw_binding(_msync_event(), raw, [mapping])


@pytest.mark.parametrize(
    ("mapping", "raw"),
    [
        (
            "1700000000.000001 mmap(NULL, 4096, PROT_READ|PROT_WRITE, "
            "MAP_SHARED, 3</case/unrelated.txt>, 0) = 0x7f000000",
            "1700000000.000002 msync(0x7f000800, 8, MS_SYNC) = 0",
        ),
        (
            "1700000000.000001 mmap(NULL, 4096, PROT_READ|PROT_WRITE, "
            "MAP_SHARED, 3</case/fixture.txt>, 0) = 0x7f000000",
            "1700000000.000002 msync(0x7f002000, 8, MS_SYNC) = 0",
        ),
        (
            "1700000000.000001 mmap(NULL, 4096, PROT_READ|PROT_WRITE, "
            "MAP_SHARED, 3</case/fixture.txt>, 0) = 0x7f000000",
            "1700000000.000002 msync(0x7f000800, 8, MS_ASYNC) = 0",
        ),
    ],
)
def test_msync_binding_rejects_wrong_provenance(mapping: str, raw: str) -> None:
    with pytest.raises(AssertionError):
        assert_event_raw_binding(_msync_event(), raw, [mapping])


def test_msync_binding_rejects_mapping_removed_before_event() -> None:
    mapping = (
        "1700000000.000001 mmap(NULL, 4096, PROT_READ|PROT_WRITE, MAP_SHARED, "
        "3</case/fixture.txt>, 0) = 0x7f000000"
    )
    removal = "1700000000.000002 munmap(0x7f000000, 4096) = 0"
    raw = "1700000000.000003 msync(0x7f000800, 8, MS_SYNC) = 0"
    event = {**_msync_event(), "timestamp": "1700000000.000003"}
    with pytest.raises(AssertionError, match="removed"):
        assert_event_raw_binding(event, raw, [mapping, removal])


def raw_exec_record(line: str) -> tuple[str, list[str]]:
    match = re.match(r'^\d+\.\d+ execve\(("(?:\\.|[^"\\])*")\s*,', line) or re.match(
        r'^\d+\.\d+ execveat\([^,]+, ("(?:\\.|[^"\\])*")\s*,',
        line,
    )
    if match is None:
        raise AssertionError("successful exec line lacks an exact executable")
    executable = ast.literal_eval(match.group(1))
    assert isinstance(executable, str)
    start = line.find("[", match.end())
    if start < 0:
        raise AssertionError("successful exec line lacks an exact argv")
    quoted = False
    escaped = False
    for index in range(start + 1, len(line)):
        char = line[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == "]":
            argv = ast.literal_eval(line[start : index + 1])
            assert isinstance(argv, list)
            assert all(isinstance(item, str) for item in argv)
            return executable, argv
    raise AssertionError("successful exec line has truncated argv")


def test_raw_exec_binding_uses_executable_and_exact_argv() -> None:
    line = (
        '1700000000.000001 execve("/bin/unrelated", ["/bin/expected"], ["LANG=C"]) = 0'
    )
    assert raw_exec_record(line) == ("/bin/unrelated", ["/bin/expected"])


def assert_policy_evidence(report: dict[str, object], policy_path: Path) -> None:
    evidence = report["policy"]
    assert set(evidence) == {"minimum_strace_version", "path", "sha256", "strace"}
    assert evidence["path"] == str(policy_path.resolve())
    assert evidence["sha256"] == hashlib.sha256(policy_path.read_bytes()).hexdigest()
    assert evidence["minimum_strace_version"] == "6.8"
    strace = evidence["strace"]
    assert set(strace) == {"executable", "package", "sha256", "version"}
    executable = Path("/usr/bin/strace")
    assert strace["executable"] == os.path.realpath(executable)
    assert strace["sha256"] == hashlib.sha256(executable.read_bytes()).hexdigest()
    assert re.fullmatch(r"strace=\S+", strace["package"])
    assert strace["version"] == "6.8"


def load_started_preflight(artifact_root: Path) -> dict[str, object]:
    top_files = sorted(path.name for path in artifact_root.iterdir() if path.is_file())
    assert top_files == ["job-result.json", "preflight.json"]
    assert json.loads((artifact_root / "job-result.json").read_text()) == {
        "status": "started"
    }
    preflight = json.loads((artifact_root / "preflight.json").read_text())
    assert preflight["authority_id"] == "rfc0022-linux-strace-v1"
    assert preflight["status"] == "available"
    return preflight


def result_class(result: str) -> str:
    if result.startswith("-1 "):
        return " ".join(result.split(maxsplit=2)[:2])
    if result == "changed":
        return "changed"
    return "success"
