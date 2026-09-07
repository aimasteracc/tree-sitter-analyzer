"""Behavioral tests for ordinary constraint index snapshot authority."""

from __future__ import annotations

import io
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

import tree_sitter_analyzer.mcp.tools.constraint_index_snapshot as owner


def _database(root: Path, rows: int = 1) -> Path:
    cache = root / ".ast-cache"
    cache.mkdir()
    path = cache / "index.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE payload(value TEXT)")
        conn.executemany(
            "INSERT INTO payload VALUES (?)", [(str(i),) for i in range(rows)]
        )
    return path


def test_portable_snapshot_pins_bytes_and_publishes_certified_private_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database(tmp_path, 2)
    certified: list[tuple[str, int]] = []

    def certify(conn: sqlite3.Connection, root: str, *, deadline: float):
        certified.append(
            (root, conn.execute("SELECT COUNT(*) FROM payload").fetchone()[0])
        )
        return owner.OrdinaryConstraintSnapshot("complete", None, "scope")

    monkeypatch.setattr(owner, "_certify_private_copy", certify)
    with owner.portable_ordinary_snapshot(
        str(tmp_path), deadline=time.monotonic() + 2
    ) as (snapshot, conn):
        values = [
            tuple(row)
            for row in conn.execute("SELECT value FROM payload ORDER BY value")
        ]
        query_only = conn.execute("PRAGMA query_only").fetchone()[0]

    assert (snapshot.completeness, snapshot.reason, snapshot.source_scope) == (
        "complete",
        None,
        "scope",
    )
    assert certified == [(str(tmp_path.resolve()), 2)]
    assert values == [("0",), ("1",)]
    assert query_only == 1


def test_portable_snapshot_removes_private_temporary_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database(tmp_path)
    staged: list[Path] = []
    real_copy = owner._temporary_copy

    @contextmanager
    def observe(fd: int, expected: tuple[int, ...], root: str, *, deadline: float):
        with real_copy(fd, expected, root, deadline=deadline) as path:
            staged.append(path.parent)
            yield path

    monkeypatch.setattr(owner, "_temporary_copy", observe)
    monkeypatch.setattr(
        owner,
        "_certify_private_copy",
        lambda *_args, **_kwargs: owner.OrdinaryConstraintSnapshot(
            "complete", None, None
        ),
    )
    with owner.portable_ordinary_snapshot(str(tmp_path), deadline=time.monotonic() + 2):
        assert len(staged) == 1

    assert staged[0].exists() is False


def test_open_database_fd_rejects_descriptor_identity_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path)
    expected = owner._identity(database, directory=False)
    monkeypatch.setattr(owner, "_stat_identity", lambda _info: (9, 9, 9, 9, 9))

    with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
        owner._open_database_fd(database, expected)


def test_open_database_fd_preserves_binary_control_bytes(tmp_path, monkeypatch):
    """PR #1350 / Windows job 101720195177：CRT 文本模式会把数据库中的 Ctrl-Z 当成 EOF。"""
    database = tmp_path / "binary.db"
    payload = b"SQLite format 3\x00\r\n\x1a\x00remaining bytes"
    database.write_bytes(payload)
    expected = owner._identity(database, directory=False)
    native_binary = getattr(os, "O_BINARY", 0)
    binary_flag = native_binary or 0x8000
    real_open = os.open
    flags_seen = []

    def open_binary(path, flags):
        flags_seen.append(flags & binary_flag)
        return real_open(path, flags if native_binary else flags & ~binary_flag)

    monkeypatch.setattr(owner.os, "O_BINARY", binary_flag, raising=False)
    monkeypatch.setattr(owner, "_open", open_binary)
    fd = owner._open_database_fd(database, expected)
    try:
        assert os.read(fd, len(payload) + 1) == payload
    finally:
        os.close(fd)
    assert flags_seen == [binary_flag]


def test_copy_pinned_database_writes_exact_advertised_bytes(tmp_path: Path) -> None:
    path = tmp_path / "bytes"
    path.write_bytes(b"abcdef")
    output = tmp_path / "copy"
    fd = os.open(path, os.O_RDONLY)
    try:
        expected = owner._stat_identity(os.fstat(fd))
        with output.open("xb", buffering=0) as stream:
            owner._copy_pinned_database(
                fd, expected, stream, deadline=time.monotonic() + 1
            )
    finally:
        os.close(fd)

    assert output.read_bytes() == b"abcdef"


def test_copy_pinned_database_rejects_truncation(tmp_path: Path) -> None:
    path = tmp_path / "bytes"
    path.write_bytes(b"x")
    fd = os.open(path, os.O_RDONLY)
    expected = list(owner._stat_identity(os.fstat(fd)))
    expected[2] = 2
    try:
        with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
            owner._copy_pinned_database(
                fd, tuple(expected), io.BytesIO(), deadline=time.monotonic() + 1
            )
    finally:
        os.close(fd)


def test_copy_pinned_database_rejects_growth(tmp_path: Path) -> None:
    path = tmp_path / "bytes"
    path.write_bytes(b"xy")
    fd = os.open(path, os.O_RDONLY)
    expected = list(owner._stat_identity(os.fstat(fd)))
    expected[2] = 1
    try:
        with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
            owner._copy_pinned_database(
                fd, tuple(expected), io.BytesIO(), deadline=time.monotonic() + 1
            )
    finally:
        os.close(fd)


def test_copy_pinned_database_enforces_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "bytes"
    path.write_bytes(b"x")
    fd = os.open(path, os.O_RDONLY)
    expected = owner._stat_identity(os.fstat(fd))
    monkeypatch.setattr(owner.time, "monotonic", lambda: 2.0)
    try:
        with pytest.raises(RuntimeError, match="^INDEX_SNAPSHOT_DEADLINE$"):
            owner._copy_pinned_database(fd, expected, io.BytesIO(), deadline=1.0)
    finally:
        os.close(fd)


@pytest.mark.parametrize("suffix", ["-wal", "-journal"])
def test_sidecar_state_rejects_nonempty_transaction_sidecars(
    tmp_path: Path, suffix: str
) -> None:
    database = _database(tmp_path)
    Path(str(database) + suffix).write_bytes(b"active")

    with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
        owner._sidecar_state(database)


def test_sidecar_state_allows_shm_and_empty_transaction_sidecars(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    Path(str(database) + "-wal").touch()
    Path(str(database) + "-journal").touch()
    Path(str(database) + "-shm").write_bytes(b"coordination")

    states = owner._sidecar_state(database)

    assert tuple(suffix for suffix, _identity in states) == ("-wal", "-journal", "-shm")
    assert tuple(identity is None for _suffix, identity in states) == (
        False,
        False,
        False,
    )


def test_temporary_copy_rejects_unsafe_parent_before_allocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3772454765: read-only staging never touches the project.
    calls = []
    monkeypatch.setattr(
        owner,
        "safe_external_temp_parent",
        lambda _root: (_ for _ in ()).throw(
            owner.SourceOracleError("DIFF_SNAPSHOT_UNSAFE_TEMP")
        ),
    )
    monkeypatch.setattr(
        owner.tempfile, "TemporaryDirectory", lambda **kwargs: calls.append(kwargs)
    )
    source = tmp_path / "source"
    source.write_bytes(b"data")
    fd = os.open(source, os.O_RDONLY)
    try:
        with pytest.raises(ValueError, match="^INDEX_TEMP_OUTSIDE_PROJECT_REQUIRED$"):
            with owner._temporary_copy(
                fd,
                owner._stat_identity(os.fstat(fd)),
                str(tmp_path.resolve()),
                deadline=time.monotonic() + 1,
            ):
                pytest.fail("unsafe temporary copy published")
    finally:
        os.close(fd)
    assert calls == []


def test_temporary_copy_rejects_project_path_after_allocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    @contextmanager
    def allocate(**kwargs):
        assert kwargs["dir"] == str(tmp_path.parent)
        yield str(tmp_path / "allocated")

    monkeypatch.setattr(
        owner, "safe_external_temp_parent", lambda _root: str(tmp_path.parent)
    )
    monkeypatch.setattr(owner.tempfile, "TemporaryDirectory", allocate)
    with pytest.raises(ValueError, match="^INDEX_TEMP_OUTSIDE_PROJECT_REQUIRED$"):
        with owner._temporary_copy(
            -1, (0, 0, 0, 0, 0), str(tmp_path), deadline=float("inf")
        ):
            pytest.fail("project-local copy published")


def _certification_dependencies(
    monkeypatch: pytest.MonkeyPatch, *, manifest: object
) -> None:
    import tree_sitter_analyzer.index_snapshot as snapshot_module
    import tree_sitter_analyzer.index_source_snapshot as source_module

    scope = object()
    current = SimpleNamespace(
        state="exact",
        reason=None,
        rows=(("a.py", "hash"),),
        fingerprint="source",
        generation="generation",
    )
    monkeypatch.setattr(owner, "validate_snapshot_schema", lambda *_a, **_k: None)
    monkeypatch.setattr(owner, "build_in_progress", lambda _conn: False)
    monkeypatch.setattr(snapshot_module, "_read_bounded_manifest", lambda *_a: manifest)
    monkeypatch.setattr(snapshot_module, "_validate_manifest_scalars", lambda _m: None)
    monkeypatch.setattr(
        source_module, "parse_source_scope_descriptor", lambda _raw: scope
    )
    monkeypatch.setattr(owner, "_capture_constraint_sources", lambda *_a: current)
    monkeypatch.setattr(owner, "recorded_source_rows", lambda *_a, **_k: current.rows)
    monkeypatch.setattr(owner, "index_fingerprint", lambda *_a, **_k: "index")
    monkeypatch.setattr(owner, "exact_call_graph_marker", lambda *_a, **_k: True)
    monkeypatch.setattr(owner, "sqlite_compile_supports_fts5", lambda _conn: True)
    monkeypatch.setattr(owner, "has_ordinary_symbol_projection", lambda *_a: True)
    monkeypatch.setattr(owner, "symbol_projection_is_exact", lambda *_a, **_k: True)


def test_certify_private_copy_accepts_exact_full_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = {
        "source_scope_descriptor": "scope",
        "canonical_root": "/project",
        "source_fingerprint": "source",
        "index_fingerprint": "index",
        "file_count": 1,
        "manifest_version": 2,
    }
    _certification_dependencies(monkeypatch, manifest=manifest)
    conn = sqlite3.connect(":memory:")
    try:
        result = owner._certify_private_copy(
            conn, "/project", deadline=time.monotonic() + 1
        )
    finally:
        conn.close()

    assert (
        result.completeness,
        result.reason,
        result.source_generation,
        result.source_fingerprint,
        result.canonical_root,
    ) == ("complete", None, "generation", "source", "/project")
    assert result.source_scope is not None


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"manifest": None}, "SOURCE_SCOPE_DESCRIPTOR_MISSING"),
        ({"canonical_root": "/other"}, "NO_EXACT_FULL_INDEX_MANIFEST"),
        ({"projection": False}, "SYMBOL_PROJECTION_INCOMPLETE"),
    ],
)
def test_certify_private_copy_reports_non_authoritative_states(
    monkeypatch: pytest.MonkeyPatch, mutation: dict[str, object], reason: str
) -> None:
    manifest = {
        "source_scope_descriptor": "scope",
        "canonical_root": "/project",
        "source_fingerprint": "source",
        "index_fingerprint": "index",
        "file_count": 1,
        "manifest_version": 2,
    }
    if "canonical_root" in mutation:
        manifest["canonical_root"] = mutation["canonical_root"]
    _certification_dependencies(
        monkeypatch, manifest=mutation.get("manifest", manifest)
    )
    if mutation.get("projection") is False:
        monkeypatch.setattr(
            owner, "symbol_projection_is_exact", lambda *_a, **_k: False
        )
    conn = sqlite3.connect(":memory:")
    try:
        result = owner._certify_private_copy(
            conn, "/project", deadline=time.monotonic() + 1
        )
    finally:
        conn.close()

    assert (result.completeness, result.reason) == ("partial", reason)


def test_evaluate_ordinary_snapshot_uses_portable_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = sqlite3.connect(":memory:")
    scope = object()
    authority = SimpleNamespace(
        completeness="complete",
        reason=None,
        source_scope=scope,
        source_generation=None,
        source_fingerprint="fingerprint",
        canonical_root="/project",
    )

    @contextmanager
    def portable(root: str, *, deadline: float):
        assert (root, deadline) == ("/project", 7.0)
        yield authority, conn

    monkeypatch.setattr(owner, "portable_snapshot_required", lambda: True)
    monkeypatch.setattr(owner, "portable_ordinary_snapshot", portable)
    monkeypatch.setattr(
        owner, "ordinary_source_scope_is_full", lambda value: value is scope
    )
    monkeypatch.setattr(
        owner,
        "_capture_constraint_sources",
        lambda *_args: SimpleNamespace(
            state="exact",
            reason=None,
            generation="different-generation",
            fingerprint="fingerprint",
        ),
    )
    calls: list[tuple[object, ...]] = []
    tool = SimpleNamespace(
        project_root="/project",
        _evaluate_connection=lambda *args, **kwargs: (
            calls.append((args, kwargs)) or ([{"ok": True}], 3)
        ),
    )
    result = owner.evaluate_ordinary_snapshot(
        tool,
        ["rule"],
        path_filter="src",
        min_severity_rank=2,
        scope_paths=frozenset({"src"}),
        evaluator="eval",
        deadline=7.0,
    )

    assert result == ([{"ok": True}], 3)
    assert calls[0][0] == (conn, ["rule"])
    assert calls[0][1] == {
        "path_filter": "src",
        "min_severity_rank": 2,
        "scope_paths": frozenset({"src"}),
        "evaluator": "eval",
        "deadline": 7.0,
    }
    conn.close()


def test_evaluate_ordinary_snapshot_uses_registry_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tree_sitter_analyzer.index_snapshot as registry

    conn = sqlite3.connect(":memory:")
    scope = SimpleNamespace(roots=(".",), exclude_patterns=())
    index = SimpleNamespace(
        snapshot_id="snap",
        completeness="complete",
        reason=None,
        source_scope=scope,
        source_generation="gen",
        canonical_root="/project",
    )
    events: list[tuple[object, ...]] = []

    @contextmanager
    def lease(root: str, *, deadline: float):
        events.append(("lease", root, deadline))
        yield index

    @contextmanager
    def acquire(snapshot_id: str, root: str, generation: str, *, deadline: float):
        events.append(("acquire", snapshot_id, root, generation, deadline))
        yield index, conn

    monkeypatch.setattr(owner, "portable_snapshot_required", lambda: False)
    monkeypatch.setattr(registry, "lease_existing_snapshot", lease)
    monkeypatch.setattr(registry, "acquire_index_snapshot", acquire)
    monkeypatch.setattr(
        owner, "ordinary_source_scope_is_full", lambda candidate: candidate is scope
    )
    current = SimpleNamespace(
        state="exact", reason=None, generation="gen", fingerprint="fingerprint"
    )
    monkeypatch.setattr(owner, "_capture_constraint_sources", lambda *_args: current)
    tool = SimpleNamespace(
        project_root="/project", _evaluate_connection=lambda *_a, **_k: ([], 0)
    )

    result = owner.evaluate_ordinary_snapshot(
        tool,
        [],
        path_filter="",
        min_severity_rank=0,
        scope_paths=None,
        evaluator=None,
        deadline=8.0,
    )

    assert result == ([], 0)
    assert events == [
        ("lease", "/project", 8.0),
        ("acquire", "snap", "/project", "gen", 8.0),
    ]
    conn.close()


def test_evaluate_ordinary_snapshot_rejects_registry_scope_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def portable(*_args, **_kwargs):
        yield owner.OrdinaryConstraintSnapshot("complete", None, object()), object()

    monkeypatch.setattr(owner, "portable_snapshot_required", lambda: True)
    monkeypatch.setattr(owner, "portable_ordinary_snapshot", portable)
    monkeypatch.setattr(owner, "ordinary_source_scope_is_full", lambda _scope: False)
    tool = SimpleNamespace(project_root="/project")

    with pytest.raises(ValueError, match="^CONSTRAINT_INDEX_SCOPE_MISMATCH$"):
        owner.evaluate_ordinary_snapshot(
            tool,
            [],
            path_filter="",
            min_severity_rank=0,
            scope_paths=None,
            evaluator=None,
            deadline=1.0,
        )


def test_constraint_source_capture_selects_descriptor_oracle(monkeypatch) -> None:
    expected = object()
    monkeypatch.setattr(owner, "portable_snapshot_required", lambda: False)
    monkeypatch.setattr(
        owner, "capture_current_source_snapshot", lambda *_a, **_k: expected
    )
    assert owner._capture_constraint_sources("/project", object(), 1.0) is expected


@pytest.mark.parametrize("portable", [False, True])
def test_real_partial_projection_rejects_constraint_evaluation(
    tmp_path, monkeypatch, portable
):
    # PR #1350：普通便携副本与新增 WAL 资格门分别验证，未获资格不宣称检查过投影。
    import tree_sitter_analyzer.index_snapshot as snapshot_owner
    import tree_sitter_analyzer.index_snapshot_capability as capability
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_snapshot import REGISTRY, stamp_full_index_manifest
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import ConstraintCheckTool

    source = tmp_path / "app.py"
    source.write_text("def answer(): return 42\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_file(str(source))
        conn = cache.get_conn()
        conn.execute("DELETE FROM ast_symbol_rows")
        stamp_full_index_manifest(conn, str(tmp_path))
    finally:
        cache.close()
    monkeypatch.setattr(owner, "portable_snapshot_required", lambda: portable)
    projection_calls = []
    real_projection = owner.symbol_projection_is_exact

    def check_projection(conn, **kwargs):
        projection_calls.append(True)
        return real_projection(conn, **kwargs)

    monkeypatch.setattr(owner, "symbol_projection_is_exact", check_projection)
    monkeypatch.setattr(snapshot_owner, "symbol_projection_is_exact", check_projection)
    tool = ConstraintCheckTool(str(tmp_path))
    monkeypatch.setattr(
        tool,
        "_evaluate_connection",
        lambda *_a, **_k: pytest.fail("incomplete snapshot evaluated constraints"),
    )
    try:
        wal_supported = (
            os.name == "posix"
            and hasattr(os, "O_NOFOLLOW")
            and capability._WAL_FD_COPY_SUPPORTED
        )
        reason = (
            "WAL_PRIVATE_SNAPSHOT_UNSUPPORTED"
            if not portable and not wal_supported
            else "SOURCE_SCOPE_UNSUPPORTED"
            if not portable and not os.path.exists("/dev/fd")
            else "SYMBOL_PROJECTION_INCOMPLETE"
        )
        with pytest.raises(ValueError, match=f"^{reason}$"):
            owner.evaluate_ordinary_snapshot(
                tool,
                [],
                path_filter="",
                min_severity_rank=0,
                scope_paths=None,
                evaluator=None,
                deadline=time.monotonic() + 10,
            )
        if not portable and not wal_supported:
            assert projection_calls == []
        else:
            assert projection_calls == [True]
    finally:
        REGISTRY.close_all()


def test_unsupported_read_existing_does_not_attempt_projection(tmp_path, monkeypatch):
    """PR #1350：普通索引可用不赋予 WAL 资格，拒绝必须发生在读取和投影核验之前。"""
    import tree_sitter_analyzer.index_snapshot_capability as capability
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import ConstraintCheckTool

    source = tmp_path / "app.py"
    source.write_text("def answer(): return 42\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        assert cache.index_file(str(source))["status"] == "indexed"
        assert cache.get_stats()["total_files"] == 1
    finally:
        cache.close()
    monkeypatch.setattr(capability, "_WAL_FD_COPY_SUPPORTED", False)
    monkeypatch.setattr(owner, "portable_snapshot_required", lambda: False)
    exists = os.path.exists
    monkeypatch.setattr(
        os.path, "exists", lambda path: False if path == "/dev/fd" else exists(path)
    )
    monkeypatch.setattr(
        capability,
        "open_bound_database",
        lambda *_a, **_k: pytest.fail("unsupported capture opened source"),
    )
    with pytest.raises(ValueError, match="^WAL_PRIVATE_SNAPSHOT_UNSUPPORTED$"):
        owner.evaluate_ordinary_snapshot(
            ConstraintCheckTool(str(tmp_path)),
            [],
            path_filter="",
            min_severity_rank=0,
            scope_paths=None,
            evaluator=None,
            deadline=time.monotonic() + 10,
        )


def test_missing_registry_index_is_rejected_without_creation(tmp_path, monkeypatch):
    # PR #1350：无索引不是部分索引，读取约束不能悄悄创建缓存。
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import ConstraintCheckTool

    monkeypatch.setattr(owner, "portable_snapshot_required", lambda: False)
    with pytest.raises(ValueError, match="^MISSING_INDEX$"):
        owner.evaluate_ordinary_snapshot(
            ConstraintCheckTool(str(tmp_path)),
            [],
            path_filter="",
            min_severity_rank=0,
            scope_paths=None,
            evaluator=None,
            deadline=time.monotonic() + 10,
        )
    assert (tmp_path / ".ast-cache").exists() is False
