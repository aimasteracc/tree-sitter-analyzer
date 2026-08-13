"""Portable snapshot exactness coverage for constraint checking."""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.unit.mcp.tools._constraint_check_support import (
    make_tool as _make_tool,
)
from tests.unit.mcp.tools._constraint_check_support import (
    run as _run,
)
from tests.unit.mcp.tools._constraint_check_support import (
    stage_minimal_constraints as _stage_minimal_constraints,
)

pytest.importorskip("yaml")


def test_portable_snapshot_rejects_symlinked_database(
    tmp_path: Path,
) -> None:
    # PR #1254 review 3767273223: pathname fallback must never follow links.
    from tree_sitter_analyzer.mcp.tools.constraint_index_snapshot import (
        portable_ordinary_snapshot,
    )

    cache = tmp_path / ".ast-cache"
    cache.mkdir()
    real = tmp_path / "real.db"
    sqlite3.connect(real).close()
    (cache / "index.db").symlink_to(real)

    with pytest.raises(ValueError, match="^INDEX_PATH_SYMLINK$"):
        with portable_ordinary_snapshot(str(tmp_path), deadline=time.monotonic() + 1.0):
            pytest.fail("symlink snapshot published")


def test_portable_snapshot_rejects_nonempty_writer_sidecar(
    tmp_path: Path,
) -> None:
    # PR #1254 review 3767273223: WAL bytes make a pathname copy ambiguous.
    from tree_sitter_analyzer.mcp.tools.constraint_index_snapshot import (
        portable_ordinary_snapshot,
    )

    cache = tmp_path / ".ast-cache"
    cache.mkdir()
    sqlite3.connect(cache / "index.db").close()
    (cache / "index.db-wal").write_bytes(b"writer")

    with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
        with portable_ordinary_snapshot(str(tmp_path), deadline=time.monotonic() + 1.0):
            pytest.fail("sidecar snapshot published")


def test_portable_snapshot_rejects_pathname_swap_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 P1: an opened fd must match the exact pre-open lstat identity.
    import os

    import tree_sitter_analyzer.mcp.tools.constraint_index_snapshot as owner

    cache = tmp_path / ".ast-cache"
    cache.mkdir()
    database = cache / "index.db"
    replacement = cache / "replacement.db"
    sqlite3.connect(database).close()
    sqlite3.connect(replacement).close()
    real_open = owner._open
    swapped = False

    def swap_then_open(path, flags):
        nonlocal swapped
        if not swapped and Path(path) == database:
            swapped = True
            os.replace(replacement, database)
        return real_open(path, flags)

    monkeypatch.setattr(owner, "_open", swap_then_open)

    with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
        with owner.portable_ordinary_snapshot(
            str(tmp_path), deadline=time.monotonic() + 1.0
        ):
            pytest.fail("mismatched opened descriptor published")


@pytest.mark.parametrize("failure", [FileNotFoundError, OSError])
def test_portable_missing_cache_is_structured_index_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: type[OSError],
) -> None:
    # Windows CI incident 2026-07-01: portable acquisition may see a missing cache.
    import tree_sitter_analyzer.mcp.tools.constraint_index_snapshot as owner

    _stage_minimal_constraints(tmp_path)
    monkeypatch.setattr(owner, "portable_snapshot_required", lambda: True)
    monkeypatch.setattr(
        owner,
        "_identity",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            failure("portable cache unavailable")
        ),
    )

    result = _run(
        _make_tool(tmp_path).execute({"persist": False, "output_format": "json"})
    )

    assert result == {
        "success": False,
        "verdict": "ERROR",
        "error_code": "CONSTRAINT_INDEX_UNKNOWN",
        "error": "portable cache unavailable",
    }


def test_portable_corrupt_copy_closes_connections_before_temporary_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Windows CI incident 2026-07-01: open SQLite handles block temp unlink.
    import tree_sitter_analyzer.mcp.tools.constraint_index_snapshot as owner

    cache = tmp_path / ".ast-cache"
    cache.mkdir()
    database = cache / "index.db"
    sqlite3.connect(database).close()
    events: list[str] = []

    class Source:
        def execute(self, _sql):
            return self

        def fetchone(self):
            return (4096,)

        def backup(self, *_args, **_kwargs):
            raise sqlite3.DatabaseError("corrupt private copy")

        def close(self):
            events.append("source.close")

    class Private:
        def execute(self, _sql):
            return self

        def fetchone(self):
            return (2,)

        def close(self):
            events.append("private.close")

    connections = iter((Source(), Private()))

    @contextmanager
    def locked_temporary_copy(_fd, _expected, _root, *, deadline):
        assert deadline > time.monotonic()
        try:
            yield tmp_path / "private-index.db"
        finally:
            events.append("temporary.exit")
            if events[:2] != ["source.close", "private.close"]:
                raise PermissionError("temporary copy is still locked")

    monkeypatch.setattr(owner, "_temporary_copy", locked_temporary_copy)
    monkeypatch.setattr(
        owner.sqlite3, "connect", lambda *_args, **_kwargs: next(connections)
    )
    monkeypatch.setattr(owner, "require_memory_temp_store", lambda _conn: None)

    with pytest.raises(sqlite3.DatabaseError, match="^corrupt private copy$"):
        with owner.portable_ordinary_snapshot(
            str(tmp_path), deadline=time.monotonic() + 1.0
        ):
            pytest.fail("corrupt snapshot published")

    assert events == ["source.close", "private.close", "temporary.exit"]


def test_constraint_source_capture_selects_portable_certifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # PR #1254 review 3768096778: Windows must not reuse the POSIX-only oracle.
    from types import SimpleNamespace

    import tree_sitter_analyzer.mcp.tools.constraint_index_snapshot as owner

    expected = SimpleNamespace(state="exact")
    calls: list[tuple[str, object, float]] = []
    monkeypatch.setattr(owner, "portable_snapshot_required", lambda: True)
    monkeypatch.setattr(
        owner,
        "capture_current_source_snapshot",
        lambda *_args, **_kwargs: pytest.fail("selected POSIX source certifier"),
    )
    monkeypatch.setattr(
        owner,
        "capture_portable_source_snapshot",
        lambda root, scope, *, deadline: (
            calls.append((root, scope, deadline)) or expected
        ),
    )
    scope = object()

    result = owner._capture_constraint_sources("C:/project", scope, 9.0)

    assert result is expected
    assert calls == [("C:/project", scope, 9.0)]


def test_portable_source_certifier_hashes_stable_supported_scope(
    tmp_path: Path,
) -> None:
    # PR #1254 review 3768096778: portable capture can certify real source bytes.
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor
    from tree_sitter_analyzer.portable_source_snapshot import (
        capture_portable_source_snapshot,
    )

    source = tmp_path / "pkg" / "sample.py"
    source.parent.mkdir()
    source.write_bytes(b"value = 1\r\n")
    (tmp_path / ".module.py").write_text("hidden = True\n")

    result = capture_portable_source_snapshot(
        str(tmp_path),
        make_source_scope_descriptor(),
        deadline=time.monotonic() + 5.0,
    )

    import hashlib

    from tree_sitter_analyzer.index_source_snapshot import inventory_fingerprint

    digest = hashlib.sha256(b"value = 1\n").hexdigest()
    hidden_digest = hashlib.sha256(b"hidden = True\n").hexdigest()
    expected_rows = frozenset(
        {
            ("pkg/sample.py", digest, "python"),
            (".module.py", hidden_digest, "python"),
        }
    )
    expected_fingerprint = inventory_fingerprint(expected_rows)
    assert (result.state, result.reason, result.rows) == (
        "exact",
        None,
        expected_rows,
    )
    assert result.fingerprint == expected_fingerprint
    assert result.generation == "idxsrc-v3:" + expected_fingerprint.removeprefix(
        "sha256:"
    )


def test_private_copy_rejects_source_change_during_certification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # PR #1254 review 3768452289: final source evidence must equal initial evidence.
    from types import SimpleNamespace

    import tree_sitter_analyzer.mcp.tools.constraint_index_snapshot as owner
    from tests.unit.mcp.tools.test_constraint_index_snapshot import (
        _certification_dependencies,
    )

    manifest = {
        "source_scope_descriptor": "scope",
        "canonical_root": "/project",
        "source_fingerprint": "source",
        "index_fingerprint": "index",
        "file_count": 1,
        "manifest_version": 2,
    }
    _certification_dependencies(monkeypatch, manifest=manifest)
    snapshots = iter(
        (
            SimpleNamespace(
                state="exact",
                reason=None,
                rows=(("a.py", "hash"),),
                fingerprint="source",
            ),
            SimpleNamespace(
                state="exact",
                reason=None,
                rows=(("a.py", "changed"),),
                fingerprint="changed",
            ),
        )
    )
    monkeypatch.setattr(
        owner, "_capture_constraint_sources", lambda *_args: next(snapshots)
    )
    conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(ValueError, match="^CONCURRENT_SOURCE$"):
            owner._certify_private_copy(
                conn, "/project", deadline=time.monotonic() + 1.0
            )
    finally:
        conn.close()


def test_live_config_snapshot_uses_portable_reader_when_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3768708964: Windows guards the same bytes it evaluates.
    import tree_sitter_analyzer.mcp.tools.constraint_check_live as live

    config = tmp_path / "architectural-constraints.yml"
    config.write_bytes(b"version: 1\nconstraints: []\n")
    monkeypatch.setattr(live, "_portable_config_required", lambda: True)
    monkeypatch.setattr(
        live,
        "safe_workspace_path",
        lambda *_args, **_kwargs: pytest.fail("selected POSIX config reader"),
    )

    result = live.live_config_snapshot(str(tmp_path), time.monotonic() + 1.0)

    assert result[0] == "architectural-constraints.yml"
    assert result[1] == b"version: 1\nconstraints: []\n"
    assert len(result[2]) == 2


def test_portable_live_config_detects_changed_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3768708964: final portable identity changes fail closed.
    import tree_sitter_analyzer.mcp.tools.constraint_check_live as live

    config = tmp_path / "architectural-constraints.yml"
    config.write_bytes(b"version: 1\nconstraints: []\n")
    before = live._portable_probe(
        str(tmp_path), "architectural-constraints.yml", time.monotonic() + 1.0
    )
    config.write_bytes(b"version: 1\nconstraints: [changed]\n")
    after = live._portable_probe(
        str(tmp_path), "architectural-constraints.yml", time.monotonic() + 1.0
    )

    assert before != after
    assert before[0] == b"version: 1\nconstraints: []\n"
    assert after[0] == b"version: 1\nconstraints: [changed]\n"


def test_live_constraint_loader_parses_the_captured_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3768708964: rules and publish evidence share one byte read.
    import tree_sitter_analyzer.mcp.tools.constraint_check_live as live

    config = tmp_path / "architectural-constraints.yml"
    empty = b"version: 1\nconstraints: []\n"
    config.write_bytes(empty)
    captured = ("architectural-constraints.yml", empty, (b"identity",))

    def snapshot(_root: str, _deadline: float):
        config.write_text(
            "version: 1\nconstraints:\n"
            "  - {id: later, severity: error, rule: forbid, from: 'a/**', "
            "to: 'b/**', reason: later}\n"
        )
        return captured

    monkeypatch.setattr(live, "live_config_snapshot", snapshot)
    observed, constraints = live.load_live_constraints(
        str(tmp_path), time.monotonic() + 1.0
    )

    assert observed == captured
    assert constraints == []


def test_private_copy_reports_final_source_unknown(monkeypatch):
    from types import SimpleNamespace

    import tree_sitter_analyzer.mcp.tools.constraint_index_snapshot as owner
    from tests.unit.mcp.tools.test_constraint_index_snapshot import (
        _certification_dependencies,
    )

    manifest = {
        "source_scope_descriptor": "scope",
        "canonical_root": "/project",
        "source_fingerprint": "source",
        "index_fingerprint": "index",
        "file_count": 1,
        "manifest_version": 2,
    }
    _certification_dependencies(monkeypatch, manifest=manifest)
    snapshots = iter(
        (
            SimpleNamespace(
                state="exact",
                reason=None,
                rows=(("a.py", "hash"),),
                fingerprint="source",
            ),
            SimpleNamespace(
                state="unknown",
                reason="SOURCE_SCOPE_UNREADABLE",
                rows=(),
                fingerprint=None,
            ),
        )
    )
    monkeypatch.setattr(
        owner, "_capture_constraint_sources", lambda *_args: next(snapshots)
    )
    conn = sqlite3.connect(":memory:")
    try:
        result = owner._certify_private_copy(
            conn, "/project", deadline=time.monotonic() + 1
        )
    finally:
        conn.close()
    assert (result.completeness, result.reason) == (
        "partial",
        "SOURCE_SCOPE_UNREADABLE",
    )


def test_ordinary_read_only_revalidates_sources_after_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3769193817: graph evaluation cannot outlive source evidence.
    from contextlib import contextmanager
    from types import SimpleNamespace

    import tree_sitter_analyzer.index_snapshot as index_snapshots
    import tree_sitter_analyzer.mcp.tools.constraint_index_snapshot as owner

    scope = SimpleNamespace(roots=(".",), exclude_patterns=())
    deadlines: list[float | None] = []

    @contextmanager
    def lease(_root, *, deadline=None):
        deadlines.append(deadline)
        yield SimpleNamespace(
            snapshot_id="is_source_guard",
            completeness="complete",
            source_generation="idxsrc-v3:before",
            source_fingerprint="sha256:before",
            source_scope=scope,
            canonical_root=str(tmp_path.resolve()),
            reason=None,
        )

    @contextmanager
    def acquire(_snapshot_id, _root, _generation, *, deadline=None):
        deadlines.append(deadline)
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE edges(kind TEXT)")
        try:
            yield SimpleNamespace(), conn
        finally:
            conn.close()

    monkeypatch.setattr(owner, "portable_snapshot_required", lambda: False)
    monkeypatch.setattr(index_snapshots, "lease_existing_snapshot", lease)
    monkeypatch.setattr(index_snapshots, "acquire_index_snapshot", acquire)
    monkeypatch.setattr(owner, "ordinary_source_scope_is_full", lambda _scope: True)
    monkeypatch.setattr(
        owner,
        "_capture_constraint_sources",
        lambda *_args: SimpleNamespace(
            state="exact",
            reason=None,
            generation="idxsrc-v3:after",
            fingerprint="sha256:after",
        ),
    )

    with pytest.raises(ValueError, match="^SOURCE_GENERATION_MISMATCH$"):
        _make_tool(tmp_path)._run_read_only(
            tmp_path / "ignored.db",
            [object()],
            path_filter="",
            min_severity_rank=1,
            evaluator=lambda _constraints, _conn: [],
        )
    assert len(deadlines) == 2
    assert deadlines[0] == deadlines[1]
    assert isinstance(deadlines[0], float)
