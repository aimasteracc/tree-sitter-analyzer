"""Exact lexical contracts for RFC-0022 decoded descriptor syntax."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from rfc0022_strace_authority import load_policy  # noqa: E402
from rfc0022_strace_model import AuthorityError  # noqa: E402
from rfc0022_strace_parser import parse_trace_directory  # noqa: E402
from rfc0022_strace_syntax import (  # noqa: E402
    descriptor_annotation,
    descriptor_path,
    split_arguments,
)

POLICY, _ = load_policy(ROOT / "config/rfc0022-linux-strace-policy.json")


def _parse_lines(tmp_path: Path, lines: list[str]) -> list[object]:
    traces = tmp_path / "traces"
    traces.mkdir()
    body = "".join(
        f"1700000000.{index:06d} {line}\n" for index, line in enumerate(lines, 1)
    )
    (traces / "trace.100").write_text(
        f"{body}1700000000.{len(lines) + 1:06d} +++ exited with 0 +++\n",
        encoding="utf-8",
    )
    violations, _, _ = parse_trace_directory(traces, POLICY, Path("/project"))
    return violations


def _parse_line(tmp_path: Path, line: str) -> list[object]:
    return _parse_lines(tmp_path, [line])


def test_syntax_workflow_dependencies_are_complete() -> None:
    workflow = (ROOT / ".github/workflows/rfc0022-linux-write-authority.yml").read_text(
        encoding="utf-8"
    )
    assert workflow.count('"scripts/rfc0022_strace_syntax.py"') == 2
    assert workflow.count("tests/contracts/test_rfc0022_strace_syntax.py") == 3


@pytest.mark.parametrize(
    ("value", "annotation"),
    [
        ("3</dev/null<char 1:3>>", "/dev/null<char 1:3>"),
        ("3<TCP:[127.0.0.1:1->127.0.0.1:2]>", "TCP:[127.0.0.1:1->127.0.0.1:2]"),
        ("3<TCPv6:[[::1]:1->[::1]:2]>", "TCPv6:[[::1]:1->[::1]:2]"),
        (
            '3<UNIX-STREAM:[10->11,"/tmp/a,b[}(<>)"]>',
            'UNIX-STREAM:[10->11,"/tmp/a,b[}(<>)"]',
        ),
        ("3<NETLINK:[SOCK_DIAG:42]>", "NETLINK:[SOCK_DIAG:42]"),
        (r"3</project/q\"u\\o\74x\76>", '/project/q"u\\o<x>'),
        (r"3</project/caf\303\251>", "/project/café"),
        (r"3</project/bad\377>", "/project/bad\udcff"),
    ],
)
def test_descriptor_annotations_are_atomic(value: str, annotation: str) -> None:
    assert descriptor_annotation(value) == annotation
    assert split_arguments(f'{value}, "x", 1') == (value, '"x"', "1")


@pytest.mark.parametrize(
    "protocol",
    [
        "TCP",
        "TCPv6",
        "UDP",
        "UDPv6",
        "UDPLITE",
        "UDPLITEv6",
        "DCCP",
        "DCCPv6",
        "SCTP",
        "SCTPv6",
        "L2TP/IP",
        "L2TP/IPv6",
        "PING",
        "PINGv6",
        "RAW",
        "RAWv6",
    ],
)
def test_strace_6_8_socket_protocol_names_are_exact(protocol: str) -> None:
    value = f"3<{protocol}:[left->right]>"
    assert descriptor_annotation(value) == f"{protocol}:[left->right]"
    assert split_arguments(f"{value}, 1") == (value, "1")


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("3</project/a,b[", "truncated strace descriptor annotation"),
        ("3</dev/null<char 1:3>", "truncated strace descriptor annotation"),
        ('3<UNIX-STREAM:[1->2,"/tmp/x>', "truncated socket descriptor annotation"),
        ("3<TCP:[1->2>", "malformed socket descriptor annotation"),
        ("3</project/a->b>", "invalid descriptor token boundary"),
        ("3</project/x>garbage", "invalid descriptor token boundary"),
        (r"3</project/x\>", "invalid strace descriptor escape"),
        ("3<>", "empty descriptor annotation"),
        ("3(deleted)", "deleted suffix requires"),
        ("AT_FDCWD(deleted)", "deleted suffix requires"),
        ("٣</project/x>", "expected decoded descriptor"),
        ("３</project/x>", "expected decoded descriptor"),
        ("3</project/café>", "raw non-ASCII/control descriptor byte"),
        ("3</project/a\n>", "raw non-ASCII/control descriptor byte"),
        (r"3</project/nul\000>", "NUL in descriptor annotation"),
        (r"3</project/bad\400>", "out-of-range strace descriptor escape"),
        ("3<TCP:[left<right]>", "raw angle in socket"),
        ("3<TCP:[left][right]>", "trailing socket descriptor structure"),
        ("3</project/x>>", "invalid descriptor token boundary"),
    ],
)
def test_malformed_descriptor_annotations_fail_closed(value: str, message: str) -> None:
    with pytest.raises(AuthorityError, match=message):
        descriptor_annotation(value)


def test_symbolic_shift_expressions_are_not_fd_annotations() -> None:
    assert split_arguments(
        "30<<MFD_HUGE_SHIFT, 0x4 /* 1<<KG_CTRL */, 8>>PAGE_SHIFT"
    ) == (
        "30<<MFD_HUGE_SHIFT",
        "0x4 /* 1<<KG_CTRL */",
        "8>>PAGE_SHIFT",
    )


def test_public_parser_accepts_strace_symbolic_left_shift(tmp_path: Path) -> None:
    line = 'memfd_create("x", 30<<MFD_HUGE_SHIFT) = -1 EINVAL (Invalid argument)'
    assert _parse_line(tmp_path, line) == []


def test_non_descriptor_arrow_keeps_normal_argument_structure() -> None:
    assert split_arguments("[1 => 2], 3</project/x>") == (
        "[1 => 2]",
        "3</project/x>",
    )
    with pytest.raises(AuthorityError, match="unbalanced strace argument structure"):
        split_arguments("3</project/x>, {bad], 0")


# PR #1259 / discussion_r3785351138: malformed annotations cannot hide in safe calls.
@pytest.mark.parametrize(
    "descriptor",
    [
        "3<>",
        "3</project/x>garbage",
        "3</project/x>>",
        r"3</project/nul\000>",
        r"3</project/bad\400>",
        "3</project/café>",
        "3<TCP:[]>",
        "3(deleted)",
    ],
)
def test_public_parser_rejects_malformed_safe_fd(
    tmp_path: Path, descriptor: str
) -> None:
    with pytest.raises(AuthorityError):
        _parse_line(tmp_path, f"close({descriptor}) = 0")


# PR #1259 / discussion_r3785351138: decoded nonfilesystem FDs stay clean.
@pytest.mark.parametrize(
    "annotation",
    [
        "TCP:[127.0.0.1:1->127.0.0.1:2]",
        "L2TP/IPv6:[[::1]:1->[::1]:2]",
        'UNIX-STREAM:[10->11,"/tmp/socket"]',
        "NETLINK:[SOCK_DIAG:42]",
        "signalfd:[mask 00000000]",
        "pid:123",
        "pidfd:[123]",
    ],
)
def test_public_parser_ignores_exact_nonfilesystem_fd(
    tmp_path: Path, annotation: str
) -> None:
    assert _parse_line(tmp_path, f'write(3<{annotation}>, "x", 1) = 1') == []


# PR #1259 / discussion_r3786037050: deleted cwd provenance is unnameable.
def test_deleted_fchdir_descriptor_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(
        AuthorityError, match="deleted descriptor pathname is unnameable"
    ):
        _parse_line(tmp_path, "fchdir(3</project/old>(deleted)) = 0")


def test_literal_deleted_suffix_fchdir_updates_exact_cwd(tmp_path: Path) -> None:
    assert descriptor_path("3</project/old (deleted)>") == "/project/old (deleted)"
    violations = _parse_lines(
        tmp_path,
        ["fchdir(3</project/old (deleted)>) = 0", 'unlink("file") = 0'],
    )
    assert [(item.operation, item.target) for item in violations] == [
        ("pathname_mutation", "/project/old (deleted)/file")
    ]


def test_failed_deleted_fchdir_preserves_original_cwd(tmp_path: Path) -> None:
    violations = _parse_lines(
        tmp_path,
        ["fchdir(3</project/old>(deleted)) = -1 ENOENT", 'unlink("file") = 0'],
    )
    assert [(item.operation, item.target) for item in violations] == [
        ("pathname_mutation", "/project/file")
    ]


@pytest.mark.parametrize(
    ("line", "operation"),
    [
        ('unlinkat(3</project/old (deleted)>, "file", 0) = 0', "pathname_mutation"),
        ('open("alias", O_WRONLY) = 4</project/old (deleted)>', "write_capable_open"),
        ('write(4</project/old (deleted)>, "x", 1) = 1', "descriptor_write"),
    ],
)
def test_literal_deleted_suffix_remains_exact_path_provenance(
    tmp_path: Path, line: str, operation: str
) -> None:
    violations = _parse_line(tmp_path, line)
    assert [(item.operation, item.target) for item in violations] == [
        (
            operation,
            "/project/old (deleted)/file"
            if line.startswith("unlinkat")
            else "/project/old (deleted)",
        )
    ]


# PR #1259 / discussion_r3786037054: successful IPC opens are not filesystem writes.
@pytest.mark.parametrize(
    ("result", "flags"),
    [("4<pipe:[42]>", "O_WRONLY"), ("5<socket:[43]>", "O_PATH|O_WRONLY")],
)
def test_write_capable_open_of_nonfilesystem_descriptor_is_clean(
    tmp_path: Path, result: str, flags: str
) -> None:
    assert (
        _parse_line(
            tmp_path,
            f'openat(AT_FDCWD</project>, "/proc/self/fd/1", {flags}) = {result}',
        )
        == []
    )


def test_failed_write_capable_open_remains_an_attempt(tmp_path: Path) -> None:
    violations = _parse_line(
        tmp_path, 'openat(AT_FDCWD</project>, "/dev/stdout", O_WRONLY) = -1 EACCES'
    )
    assert [(item.operation, item.target) for item in violations] == [
        ("write_capable_open", "/dev/stdout")
    ]


@pytest.mark.parametrize(
    "line",
    [
        'openat(3</project/old>(deleted), "file", O_WRONLY) = -1 ENOENT',
        'unlinkat(3</project/old>(deleted), "file", 0) = -1 ENOENT',
    ],
)
def test_deleted_relative_dirfd_provenance_fails_closed(
    tmp_path: Path, line: str
) -> None:
    with pytest.raises(
        AuthorityError, match="deleted descriptor pathname is unnameable"
    ):
        _parse_line(tmp_path, line)


def test_write_capable_magic_fd_open_of_regular_file_remains_a_violation(
    tmp_path: Path,
) -> None:
    violations = _parse_line(
        tmp_path,
        'openat(AT_FDCWD</project>, "/proc/self/fd/3", O_WRONLY) = 4</project/out>',
    )
    assert [(item.operation, item.target) for item in violations] == [
        ("write_capable_open", "/project/out")
    ]
