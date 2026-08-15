"""Non-mutating snapshot contracts for the RFC-0022 Linux authority."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import rfc0022_strace_snapshot as snapshot  # noqa: E402
from rfc0022_strace_authority import snapshot_root  # noqa: E402
from rfc0022_strace_model import AuthorityError  # noqa: E402

LINUX_NOATIME = sys.platform == "linux" and hasattr(os, "O_NOATIME")


def test_snapshot_workflow_dependencies_are_complete() -> None:
    workflow = (ROOT / ".github/workflows/rfc0022-linux-write-authority.yml").read_text(
        encoding="utf-8"
    )
    assert workflow.count('"scripts/rfc0022_strace_snapshot.py"') == 2
    assert workflow.count("tests/contracts/test_rfc0022_strace_snapshot.py") == 3


def test_snapshot_schema_includes_access_time(tmp_path: Path) -> None:
    path = tmp_path / "value.txt"
    path.write_bytes(b"value")
    records = snapshot_root(tmp_path)["records"]
    file_record = next(record for record in records if record["path"] == "value.txt")
    assert set(file_record) == {
        "atime_ns",
        "ctime_ns",
        "device",
        "gid",
        "inode",
        "kind",
        "mode",
        "mtime_ns",
        "nlink",
        "path",
        "sha256",
        "size",
        "uid",
    }
    assert file_record["atime_ns"] == path.stat().st_atime_ns
    expected_sha = "cd42404d52ad55ccfa9aca4adc828aa5800ad9d385a0671fbcbf724118320619"  # pragma: allowlist secret
    assert file_record["sha256"] == expected_sha


def test_authority_requires_nonmutating_snapshots() -> None:
    source = (ROOT / "scripts/rfc0022_strace_authority.py").read_text(encoding="utf-8")
    assert source.count("snapshot_root(root, require_noatime=True)") == 3


def test_required_noatime_support_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(snapshot.sys, "platform", "unsupported")
    with pytest.raises(AuthorityError, match="O_NOATIME snapshot support"):
        snapshot_root(tmp_path, require_noatime=True)


# PR #1259 / discussion_r3785351132: authority measurement must not change atime.
@pytest.mark.skipif(
    not LINUX_NOATIME,
    reason="tracked: RFC-0022 Linux O_NOATIME authority contract",
)
def test_snapshot_hash_and_traversal_preserve_access_times(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    path = nested / "value.txt"
    path.write_bytes(b"value")
    now = time.time_ns()
    for index, item in enumerate((path, nested, tmp_path), start=1):
        os.utime(
            item,
            ns=(now - (index + 3) * 86_400_000_000_000, now - 1_000_000_000),
        )
    expected = {item: item.stat().st_atime_ns for item in (path, nested, tmp_path)}
    opened_flags: list[int] = []
    original_open = snapshot.os.open

    def tracked_open(*args: object, **kwargs: object) -> int:
        opened_flags.append(int(args[1]))
        return original_open(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(snapshot.os, "open", tracked_open)
    result = snapshot_root(tmp_path, require_noatime=True)
    required = os.O_CLOEXEC | os.O_NOATIME | os.O_NOFOLLOW | os.O_NONBLOCK
    assert opened_flags and all(flags & required == required for flags in opened_flags)
    assert {item: item.stat().st_atime_ns for item in expected} == expected
    by_path = {record["path"]: record for record in result["records"]}
    assert by_path["."]["atime_ns"] == expected[tmp_path]
    assert by_path["nested"]["atime_ns"] == expected[nested]
    assert by_path["nested/value.txt"]["atime_ns"] == expected[path]


# PR #1259 / discussion_r3785351132: external reads remain snapshot-visible.
@pytest.mark.skipif(
    not LINUX_NOATIME,
    reason="tracked: RFC-0022 Linux O_NOATIME authority contract",
)
def test_snapshot_detects_access_time_only_change(tmp_path: Path) -> None:
    path = tmp_path / "value.txt"
    path.write_bytes(b"same bytes")
    now = time.time_ns()
    os.utime(
        path,
        ns=(now - 2 * 86_400_000_000_000, now - 86_400_000_000_000),
    )
    before = snapshot_root(tmp_path, require_noatime=True)
    assert path.read_bytes() == b"same bytes"
    recorded_atime = next(
        item["atime_ns"] for item in before["records"] if item["path"] == "value.txt"
    )
    if path.stat().st_atime_ns == recorded_atime:
        pytest.skip("tracked: PR #1259 filesystem does not update read atime")
    after = snapshot_root(tmp_path, require_noatime=True)
    old_file = next(item for item in before["records"] if item["path"] == "value.txt")
    new_file = next(item for item in after["records"] if item["path"] == "value.txt")
    assert old_file["sha256"] == new_file["sha256"]
    assert old_file["atime_ns"] != new_file["atime_ns"]
    assert before != after


# PR #1259 / discussion_r3785351132: symlink evidence is non-mutating.
@pytest.mark.skipif(
    not LINUX_NOATIME,
    reason="tracked: RFC-0022 Linux O_NOATIME authority contract",
)
def test_snapshot_does_not_read_or_follow_symlink(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_bytes(b"outside")
    link = tmp_path / "link"
    link.symlink_to(outside)
    old_atime = time.time_ns() - 4 * 86_400_000_000_000
    os.utime(link, ns=(old_atime, old_atime), follow_symlinks=False)
    link_atime = link.lstat().st_atime_ns
    target_atime = outside.stat().st_atime_ns
    result = snapshot_root(tmp_path, require_noatime=True)
    record = next(item for item in result["records"] if item["path"] == "link")
    assert record["kind"] == "symlink"
    assert "target" not in record
    assert link.lstat().st_atime_ns == link_atime
    assert outside.stat().st_atime_ns == target_atime


# PR #1259 / discussion_r3785351132: O_NOATIME failure has no ordinary-read retry.
def test_noatime_open_failure_has_no_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = 0

    def denied(*args: object, **kwargs: object) -> int:
        nonlocal attempts
        attempts += 1
        raise PermissionError("O_NOATIME denied")

    monkeypatch.setattr(snapshot, "_noatime_flags", lambda **kwargs: 0)
    monkeypatch.setattr(snapshot.os, "open", denied)
    with pytest.raises(AuthorityError, match="unable to open snapshot inode"):
        snapshot._linux_snapshot(tmp_path)
    assert attempts == 1
