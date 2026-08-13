"""Budget and final-sidecar checks for portable constraint index snapshots."""

from __future__ import annotations

import io
import os
import time
from pathlib import Path

import pytest

import tree_sitter_analyzer.mcp.tools.constraint_index_snapshot as owner
from tests.unit.mcp.tools.test_constraint_index_snapshot import _database


def test_portable_snapshot_rejects_page_count_budget_after_pinned_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database(tmp_path)

    class Source:
        def execute(self, sql: str):
            self.sql = sql
            return self

        def fetchone(self):
            if "page_count" in self.sql:
                monkeypatch.setattr(owner, "_MAX_BACKUP_BYTES", 1)
                return (1,)
            return (4096,)

        def close(self):
            pass

    monkeypatch.setattr(owner.sqlite3, "connect", lambda *_a, **_k: Source())
    monkeypatch.setattr(owner, "require_memory_temp_store", lambda _conn: None)

    with pytest.raises(RuntimeError, match="^INDEX_BACKUP_BUDGET$"):
        with owner.portable_ordinary_snapshot(
            str(tmp_path), deadline=time.monotonic() + 1
        ):
            pytest.fail("oversized page set published")


def test_portable_snapshot_progress_rechecks_backup_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database(tmp_path)

    class Source:
        def execute(self, sql: str):
            self.sql = sql
            return self

        def fetchone(self):
            return (4096,) if "page_size" in self.sql else (0,)

        def backup(self, _private, **kwargs):
            monkeypatch.setattr(owner, "_MAX_BACKUP_BYTES", 1)
            kwargs["progress"](0, 0, 1)

        def close(self):
            pass

    class Private:
        def close(self):
            pass

    connections = iter((Source(), Private()))
    monkeypatch.setattr(owner.sqlite3, "connect", lambda *_a, **_k: next(connections))
    monkeypatch.setattr(owner, "require_memory_temp_store", lambda _conn: None)

    with pytest.raises(RuntimeError, match="^INDEX_BACKUP_BUDGET$"):
        with owner.portable_ordinary_snapshot(
            str(tmp_path), deadline=time.monotonic() + 1
        ):
            pytest.fail("progress budget violation published")


@pytest.mark.parametrize("changed_on_call", [3, 4])
def test_portable_snapshot_rechecks_sidecars_before_and_after_certification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed_on_call: int
) -> None:
    _database(tmp_path)
    calls = 0
    stable = (("-wal", None), ("-journal", None), ("-shm", None))

    def sidecars(_path: Path):
        nonlocal calls
        calls += 1
        return stable if calls != changed_on_call else (("-wal", (1, 2, 3, 4, 5)),)

    monkeypatch.setattr(owner, "_sidecar_state", sidecars)
    monkeypatch.setattr(
        owner,
        "_certify_private_copy",
        lambda *_a, **_k: owner.OrdinaryConstraintSnapshot("complete", None, None),
    )

    with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
        with owner.portable_ordinary_snapshot(
            str(tmp_path), deadline=time.monotonic() + 1
        ):
            pytest.fail("changed sidecar state published")

    assert calls == changed_on_call


class _RecordingWriter:
    def __init__(self, events: list[tuple[str, bytes]]) -> None:
        self.events = events

    def write(self, data: memoryview) -> int:
        payload = bytes(data)
        self.events.append(("write", payload))
        return len(payload)


def test_pinned_copy_interleaves_bounded_reads_and_staging_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3768545528: never accumulate a second whole DB in memory.
    source = tmp_path / "source.db"
    source.write_bytes(b"abcdef")
    fd = owner.os.open(source, owner.os.O_RDONLY)
    expected = owner._stat_identity(owner.os.fstat(fd))
    chunks = iter((b"abc", b"def", b""))
    events: list[tuple[str, bytes]] = []

    def read(_fd: int, _size: int) -> bytes:
        chunk = next(chunks)
        events.append(("read", chunk))
        return chunk

    monkeypatch.setattr(owner.os, "read", read)
    try:
        owner._copy_pinned_database(
            fd,
            expected,
            _RecordingWriter(events),
            deadline=time.monotonic() + 1,
        )
    finally:
        owner.os.close(fd)

    assert events == [
        ("read", b"abc"),
        ("write", b"abc"),
        ("read", b"def"),
        ("write", b"def"),
        ("read", b""),
    ]


def test_pinned_copy_polls_deadline_after_partial_staging_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3768614248: staging writes share the absolute deadline.
    source = tmp_path / "source.db"
    source.write_bytes(b"abcdef")
    fd = owner.os.open(source, owner.os.O_RDONLY)
    expected = owner._stat_identity(owner.os.fstat(fd))
    checks = 0
    writes: list[bytes] = []

    class PartialWriter:
        def write(self, data: memoryview) -> int:
            writes.append(bytes(data))
            return 1

    def deadline(_absolute: float) -> None:
        nonlocal checks
        checks += 1
        if checks == 3:
            raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")

    monkeypatch.setattr(owner, "_deadline", deadline)
    try:
        with pytest.raises(RuntimeError, match="^INDEX_SNAPSHOT_DEADLINE$"):
            owner._copy_pinned_database(fd, expected, PartialWriter(), deadline=1.0)
    finally:
        owner.os.close(fd)

    assert (writes, checks) == ([b"abcdef"], 3)


@pytest.mark.parametrize("written", [None, 0, -1, 7])
def test_pinned_copy_rejects_invalid_staging_write_count(
    tmp_path: Path, written: int | None
) -> None:
    source = tmp_path / "source.db"
    source.write_bytes(b"abcdef")
    fd = owner.os.open(source, owner.os.O_RDONLY)
    expected = owner._stat_identity(owner.os.fstat(fd))

    class InvalidWriter:
        def write(self, _data: memoryview):
            return written

    try:
        with pytest.raises(OSError, match="^INDEX_STAGE_WRITE_FAILED$"):
            owner._copy_pinned_database(
                fd, expected, InvalidWriter(), deadline=time.monotonic() + 1
            )
    finally:
        owner.os.close(fd)


def test_portable_snapshot_maps_disappearing_cache_to_missing_index(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="^MISSING_INDEX$"):
        with owner.portable_ordinary_snapshot(
            str(tmp_path), deadline=time.monotonic() + 1
        ):
            pytest.fail("missing index published")


def test_copy_pinned_database_rejects_backup_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "bytes"
    path.write_bytes(b"xx")
    fd = os.open(path, os.O_RDONLY)
    expected = owner._stat_identity(os.fstat(fd))
    monkeypatch.setattr(owner, "_MAX_BACKUP_BYTES", 1)
    try:
        with pytest.raises(RuntimeError, match="^INDEX_BACKUP_BUDGET$"):
            owner._copy_pinned_database(
                fd, expected, io.BytesIO(), deadline=time.monotonic() + 1
            )
    finally:
        os.close(fd)
