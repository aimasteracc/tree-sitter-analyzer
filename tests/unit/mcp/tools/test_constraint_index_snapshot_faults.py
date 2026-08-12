"""Fault-boundary behaviors for ordinary constraint index snapshots."""

from __future__ import annotations

import io
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import tree_sitter_analyzer.mcp.tools.constraint_index_snapshot as owner
from tests.unit.mcp.tools.test_constraint_index_snapshot import (
    _certification_dependencies,
    _database,
)


def test_identity_rejects_non_directory_and_non_regular_paths(tmp_path: Path) -> None:
    regular = tmp_path / "file"
    regular.touch()
    directory = tmp_path / "directory"
    directory.mkdir()

    with pytest.raises(ValueError, match="^INDEX_PATH_UNSAFE$"):
        owner._identity(regular, directory=True)
    with pytest.raises(ValueError, match="^INDEX_PATH_UNSAFE$"):
        owner._identity(directory, directory=False)


def test_copy_pinned_database_rejects_identity_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "bytes"
    path.write_bytes(b"x")
    fd = owner._open(path, 0)
    expected = owner._stat_identity(owner.os.fstat(fd))
    monkeypatch.setattr(owner, "_stat_identity", lambda _info: (9, 9, 9, 9, 9))
    try:
        with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
            owner._copy_pinned_database(
                fd, expected, io.BytesIO(), deadline=time.monotonic() + 1
            )
    finally:
        owner.os.close(fd)


def test_temporary_copy_handles_incomparable_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_commonpath = owner.os.path.commonpath
    monkeypatch.setattr(
        owner.os.path, "commonpath", lambda _paths: (_ for _ in ()).throw(ValueError())
    )

    source = tmp_path / "source"
    source.write_bytes(b"exact")
    fd = owner._open(source, owner.os.O_RDONLY)
    try:
        expected = owner._stat_identity(owner.os.fstat(fd))
        with owner._temporary_copy(
            fd, expected, str(tmp_path), deadline=time.monotonic() + 1
        ) as copy:
            contents = copy.read_bytes()
    finally:
        owner.os.close(fd)

    monkeypatch.setattr(owner.os.path, "commonpath", real_commonpath)
    assert contents == b"exact"


def test_certify_private_copy_rejects_active_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(owner, "validate_snapshot_schema", lambda *_a, **_k: None)
    monkeypatch.setattr(owner, "build_in_progress", lambda _conn: True)
    conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
            owner._certify_private_copy(conn, "/project", deadline=time.monotonic() + 1)
    finally:
        conn.close()


def test_certify_private_copy_reports_invalid_scope_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = {"source_scope_descriptor": "invalid"}
    _certification_dependencies(monkeypatch, manifest=manifest)
    import tree_sitter_analyzer.index_source_snapshot as source_module

    monkeypatch.setattr(
        source_module,
        "parse_source_scope_descriptor",
        lambda _raw: (_ for _ in ()).throw(ValueError()),
    )
    conn = sqlite3.connect(":memory:")
    try:
        result = owner._certify_private_copy(
            conn, "/project", deadline=time.monotonic() + 1
        )
    finally:
        conn.close()

    assert (result.completeness, result.reason, result.source_scope) == (
        "partial",
        "SOURCE_SCOPE_DESCRIPTOR_INVALID",
        None,
    )


def test_certify_private_copy_reports_inexact_current_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = {"source_scope_descriptor": "scope"}
    _certification_dependencies(monkeypatch, manifest=manifest)
    monkeypatch.setattr(
        owner,
        "_capture_constraint_sources",
        lambda *_a: SimpleNamespace(state="partial", reason="SOURCE_CHANGED"),
    )
    conn = sqlite3.connect(":memory:")
    try:
        result = owner._certify_private_copy(
            conn, "/project", deadline=time.monotonic() + 1
        )
    finally:
        conn.close()

    assert (result.completeness, result.reason) == ("partial", "SOURCE_CHANGED")
    assert result.source_scope is not None


def test_portable_snapshot_rejects_identity_change_after_pinned_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database(tmp_path)
    real_identity = owner._identity
    root_calls = 0

    def identity(path: Path, *, directory: bool):
        nonlocal root_calls
        value = real_identity(path, directory=directory)
        if path == tmp_path:
            root_calls += 1
            if root_calls == 2:
                return (value[0] + 1, *value[1:])
        return value

    monkeypatch.setattr(owner, "_identity", identity)
    with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
        with owner.portable_ordinary_snapshot(
            str(tmp_path), deadline=time.monotonic() + 1
        ):
            pytest.fail("changed identity published")


def test_portable_snapshot_rejects_missing_private_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database(tmp_path)

    class Source:
        def execute(self, sql: str):
            self.sql = sql
            return self

        def fetchone(self):
            return (4096,) if "page_size" in self.sql else (0,)

        def backup(self, _private, **_kwargs):
            pass

        def close(self):
            pass

    connections = iter((Source(), None))
    monkeypatch.setattr(owner.sqlite3, "connect", lambda *_a, **_k: next(connections))
    monkeypatch.setattr(owner, "require_memory_temp_store", lambda _conn: None)

    with pytest.raises(ValueError, match="^CONSTRAINT_INDEX_UNKNOWN$"):
        with owner.portable_ordinary_snapshot(
            str(tmp_path), deadline=time.monotonic() + 1
        ):
            pytest.fail("missing connection published")


def test_portable_snapshot_retries_source_cleanup_after_close_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database(tmp_path)

    class Source:
        closes = 0

        def execute(self, sql: str):
            self.sql = sql
            return self

        def fetchone(self):
            return (4096,) if "page_size" in self.sql else (0,)

        def backup(self, _private, **_kwargs):
            pass

        def close(self):
            self.closes += 1
            if self.closes == 1:
                raise RuntimeError("close failed")

    source = Source()
    private = SimpleNamespace(close=lambda: None)
    connections = iter((source, private))
    monkeypatch.setattr(owner.sqlite3, "connect", lambda *_a, **_k: next(connections))
    monkeypatch.setattr(owner, "require_memory_temp_store", lambda _conn: None)

    with pytest.raises(RuntimeError, match="^close failed$"):
        with owner.portable_ordinary_snapshot(
            str(tmp_path), deadline=time.monotonic() + 1
        ):
            pytest.fail("failed cleanup published")

    assert source.closes == 2


def test_portable_snapshot_closes_no_descriptor_when_open_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database(tmp_path)
    monkeypatch.setattr(
        owner,
        "_open_database_fd",
        lambda *_a: (_ for _ in ()).throw(OSError("open failed")),
    )

    with pytest.raises(OSError, match="^open failed$"):
        with owner.portable_ordinary_snapshot(
            str(tmp_path), deadline=time.monotonic() + 1
        ):
            pytest.fail("failed open published")


def test_portable_snapshot_closes_private_connection_when_backup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database(tmp_path)

    class Source:
        def execute(self, sql: str):
            self.sql = sql
            return self

        def fetchone(self):
            return (4096,) if "page_size" in self.sql else (0,)

        def backup(self, _private, **_kwargs):
            raise RuntimeError("backup failed")

        def close(self):
            pass

    closed: list[str] = []
    private = SimpleNamespace(close=lambda: closed.append("private"))
    connections = iter((Source(), private))
    monkeypatch.setattr(owner.sqlite3, "connect", lambda *_a, **_k: next(connections))
    monkeypatch.setattr(owner, "require_memory_temp_store", lambda _conn: None)

    with pytest.raises(RuntimeError, match="^backup failed$"):
        with owner.portable_ordinary_snapshot(
            str(tmp_path), deadline=time.monotonic() + 1
        ):
            pytest.fail("failed backup published")

    assert closed == ["private"]


def test_portable_snapshot_rejects_unavailable_source_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database(tmp_path)
    monkeypatch.setattr(owner.sqlite3, "connect", lambda *_a, **_k: None)

    with pytest.raises(AttributeError, match="execute"):
        with owner.portable_ordinary_snapshot(
            str(tmp_path), deadline=time.monotonic() + 1
        ):
            pytest.fail("unavailable source published")


def test_close_optional_fd_handles_absent_and_open_descriptor(monkeypatch):
    calls = []
    monkeypatch.setattr(owner.os, "close", calls.append)
    owner._close_optional_fd(None)
    owner._close_optional_fd(7)
    assert calls == [7]


def test_portable_snapshot_maps_certification_database_error(tmp_path, monkeypatch):
    _database(tmp_path)
    monkeypatch.setattr(
        owner,
        "_certify_private_copy",
        lambda *_a, **_kw: (_ for _ in ()).throw(sqlite3.DatabaseError("bad schema")),
    )
    with pytest.raises(ValueError, match="^CORRUPT_INDEX$"):
        with owner.portable_ordinary_snapshot(
            str(tmp_path), deadline=time.monotonic() + 1
        ):
            pytest.fail("corrupt certification published")
