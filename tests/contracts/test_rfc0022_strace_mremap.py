"""#1731: ``mremap`` is classified, not rejected as an unknown traced syscall.

glibc ``realloc`` grows large anonymous allocations with ``mremap``, so whether a
traced target issues it depends on the allocator, not on what the target
writes. The qualification failed intermittently on ``unknown traced syscall:
mremap`` even for the clean control. ``mremap`` moves or resizes an existing
mapping: the new range inherits the source mapping's provenance (shared flag and
file target), so later ``mprotect`` / ``msync`` / writeback advice on the new range
is judged exactly like the original mapping.
"""

import sys
from dataclasses import asdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from rfc0022_strace_authority import load_policy  # noqa: E402
from rfc0022_strace_model import AuthorityError  # noqa: E402
from rfc0022_strace_parser import parse_trace_directory  # noqa: E402

POLICY, _ = load_policy(ROOT / "config/rfc0022-linux-strace-policy.json")


def _parse(tmp_path: Path, bodies: list[str]) -> list[dict[str, object]]:
    trace = tmp_path / "trace"
    trace.mkdir()
    lines = (f"1700000000.{index:06d} {body}\n" for index, body in enumerate(bodies, 1))
    (trace / "trace.100").write_text("".join(lines), encoding="utf-8")
    violations, _, _ = parse_trace_directory(trace, POLICY, Path("/project"))
    return [asdict(item) for item in violations]


def test_policy_classifies_the_allocator_syscalls() -> None:
    # brk / madvise are safe; mmap, munmap, mprotect and mremap are tracked mappings.
    assert {"brk", "madvise"} <= set(POLICY["safe_syscalls"])
    assert {"mmap", "munmap", "mprotect", "mremap"} <= set(POLICY["mapping_syscalls"])


def test_anonymous_realloc_mremap_is_clean(tmp_path: Path) -> None:
    assert (
        _parse(
            tmp_path,
            [
                "mmap(NULL, 1052672, PROT_READ|PROT_WRITE, "
                "MAP_PRIVATE|MAP_ANONYMOUS, -1, 0) = 0x7f0000000000",
                "mremap(0x7f0000000000, 1052672, 2101248, MREMAP_MAYMOVE) "
                "= 0x7f0000200000",
                "munmap(0x7f0000200000, 2101248) = 0",
                "+++ exited with 0 +++",
            ],
        )
        == []
    )


def test_moved_shared_file_mapping_keeps_its_target(tmp_path: Path) -> None:
    # The moved range is still the shared file mapping: making it writable is a
    # write to that file, at the new address.
    violations = _parse(
        tmp_path,
        [
            "mmap(NULL, 4096, PROT_READ, MAP_SHARED, 4</project/data.bin>, 0) = 0x4000",
            "mremap(0x4000, 4096, 8192, MREMAP_MAYMOVE) = 0x9000",
            "mprotect(0x9000, 8192, PROT_READ|PROT_WRITE) = 0",
            "+++ exited with 0 +++",
        ],
    )
    assert [(v["syscall"], v["operation"], v["target"]) for v in violations] == [
        ("mprotect", "shared_mapping_write", "/project/data.bin")
    ]


def test_old_range_is_gone_after_a_move(tmp_path: Path) -> None:
    with pytest.raises(AuthorityError, match="mapping provenance"):
        _parse(
            tmp_path,
            [
                "mmap(NULL, 4096, PROT_READ, MAP_SHARED, 4</project/data.bin>, 0) "
                "= 0x4000",
                "mremap(0x4000, 4096, 8192, MREMAP_MAYMOVE) = 0x9000",
                "mprotect(0x4000, 4096, PROT_READ|PROT_WRITE) = 0",
                "+++ exited with 0 +++",
            ],
        )


def test_failed_mremap_keeps_the_original_mapping(tmp_path: Path) -> None:
    violations = _parse(
        tmp_path,
        [
            "mmap(NULL, 4096, PROT_READ, MAP_SHARED, 4</project/data.bin>, 0) = 0x4000",
            "mremap(0x4000, 4096, 8192, 0) = -1 ENOMEM (Cannot allocate memory)",
            "mprotect(0x4000, 4096, PROT_READ|PROT_WRITE) = 0",
            "+++ exited with 0 +++",
        ],
    )
    assert [(v["syscall"], v["target"]) for v in violations] == [
        ("mprotect", "/project/data.bin")
    ]


@pytest.mark.parametrize(
    "body",
    [
        # source range was never mapped in this trace: provenance unknown
        "mremap(0x5000, 4096, 8192, MREMAP_MAYMOVE) = 0x9000",
        # truncated arguments
        "mremap(0x5000, 4096) = 0x9000",
        # zero-length duplicate of a shared mapping cannot be attributed exactly
        "mremap(0x4000, 0, 4096, MREMAP_MAYMOVE) = 0x9000",
    ],
)
def test_unattributable_mremap_fails_closed(tmp_path: Path, body: str) -> None:
    with pytest.raises(AuthorityError, match="mremap|mapping provenance"):
        _parse(
            tmp_path,
            [
                "mmap(NULL, 4096, PROT_READ, MAP_SHARED, 4</project/data.bin>, 0) "
                "= 0x4000",
                body,
                "+++ exited with 0 +++",
            ],
        )


def test_mremap_spanning_two_different_mappings_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(AuthorityError, match="mremap"):
        _parse(
            tmp_path,
            [
                "mmap(NULL, 4096, PROT_READ, MAP_SHARED, 4</project/a>, 0) = 0x4000",
                "mmap(0x5000, 4096, PROT_READ, MAP_PRIVATE|MAP_FIXED, "
                "5</project/b>, 0) = 0x5000",
                "mremap(0x4000, 8192, 16384, MREMAP_MAYMOVE) = 0x9000",
                "+++ exited with 0 +++",
            ],
        )
