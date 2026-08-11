from __future__ import annotations

import os
import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.indexer import walk_and_partition
from tree_sitter_analyzer.indexing_snapshot import (
    IndexCandidateSnapshot,
    build_index_candidate_snapshot,
)
from tree_sitter_analyzer.source_oracle import SourceOracleError

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")


def _python_language(path: str) -> str | None:
    return "python" if path.endswith(".py") else None


class _CacheRoot:
    def __init__(self, project_root: str) -> None:
        self.project_root = project_root


def _index_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index ("
        "file_path TEXT PRIMARY KEY, content_hash TEXT, mtime_ns INTEGER, "
        "file_size INTEGER, extractor_version INTEGER)"
    )
    return conn


def _partition(snapshot: IndexCandidateSnapshot, conn: sqlite3.Connection):
    return walk_and_partition(
        _CacheRoot(snapshot.project_root),
        conn,
        max_files=snapshot.max_files,
        force=False,
        activation_enabled=False,
        walk_fn=lambda _root: (),
        language_fn=_python_language,
        extractor_version=1,
        make_error_entry=lambda path, reason: {
            "file": path,
            "status": "error",
            "reason": reason,
        },
        candidate_snapshot=snapshot,
    )


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_regular_candidate_then_symlink_alias_still_records_error(tmp_path):
    # PR #1253 review thread 2077: realpath de-dup must not hide an unsafe alias.
    target = tmp_path / "target.py"
    target.write_text("value = 1\n")
    linked = tmp_path / "linked.py"
    linked.symlink_to(target)

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: [str(target), str(linked)],
        language_fn=_python_language,
    )

    assert (
        snapshot.discovered,
        snapshot.selected,
        snapshot.errors,
        tuple(entry.decision for entry in snapshot.entries),
    ) == (2, 1, 1, ("selected", "error"))


def test_posix_worker_never_parses_symlink_swap_target(tmp_path, monkeypatch):
    # PR #1253 review 3755216342: parsing consumes only the pinned oracle bytes.
    if os.name != "posix":
        pytest.skip("GH-1253: descriptor-backed worker is POSIX-only")
    from tree_sitter_analyzer.cache import extraction

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    outside = tmp_path.parent / "outside.py"
    outside.write_text("outside_secret = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=1,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: [str(source)],
        language_fn=_python_language,
    )
    expected = snapshot.selected_entries[0].fingerprint
    source.unlink()
    source.symlink_to(outside)
    monkeypatch.setattr(
        extraction.Parser,
        "parse_code",
        lambda *_args, **_kwargs: pytest.fail("parser reached swapped target"),
    )

    result = extraction._worker_index_file(
        (str(source), str(tmp_path), "python", expected)
    )

    assert (result["status"], result["reason"]) == (
        "source_changed",
        "file changed after candidate snapshot",
    )


def test_indexer_classifies_worker_source_changed_without_restat():
    # PR #1253: worker admission failures propagate as candidate changes.
    from tree_sitter_analyzer.cache.indexer import _snapshot_result_change_reason

    result = {"rel_path": "app.py", "status": "source_changed"}
    entry = SimpleNamespace()

    assert _snapshot_result_change_reason(result, {"app.py": entry}) == (
        "app.py",
        "file changed after candidate snapshot",
    )


@requires_posix_fd
def test_worker_rejects_nonfile_oracle_result(tmp_path, monkeypatch):
    # PR #1253: workers reject special-file oracle responses before parsing.
    from tree_sitter_analyzer.cache import extraction

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    monkeypatch.setattr(
        extraction,
        "safe_workspace_path",
        lambda *_a, **_k: SimpleNamespace(kind="directory", data=None),
    )
    result = extraction._worker_index_file((str(source), str(tmp_path), "python"))
    assert result["status"] == "io_error"


@requires_posix_fd
def test_worker_rejects_content_hash_mismatch(tmp_path):
    # PR #1253: descriptor identity alone cannot authorize changed bytes.
    from dataclasses import replace

    from tree_sitter_analyzer.cache import extraction

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=1,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: [str(source)],
        language_fn=_python_language,
    )
    expected = replace(snapshot.selected_entries[0].fingerprint, content_hash="forged")
    result = extraction._worker_index_file(
        (str(source), str(tmp_path), "python", expected)
    )
    assert result["status"] == "source_changed"


def test_windows_worker_reads_the_admitted_regular_file(tmp_path, monkeypatch):
    # PR #1253: the legacy non-POSIX worker path remains functional.
    from tree_sitter_analyzer.cache import extraction

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    monkeypatch.setattr(
        extraction, "os", SimpleNamespace(name="nt", path=os.path, stat=os.stat)
    )
    result = extraction._worker_index_file((str(source), str(tmp_path), "python"))
    physical_size = os.stat(source).st_size
    assert (result["status"], result["file_size"]) == ("ok", physical_size)


def test_candidate_capture_rejects_nonfile_oracle(tmp_path, monkeypatch):
    # PR #1253: candidate capture accepts only regular-file oracle bytes.
    import tree_sitter_analyzer.indexing_snapshot as snapshot_module

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    monkeypatch.setattr(
        snapshot_module,
        "safe_workspace_path",
        lambda *_a, **_k: SimpleNamespace(kind="directory", data=None),
    )
    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_SPECIAL_FILE"):
        snapshot_module._capture_candidate_fingerprint(
            str(tmp_path), "app.py", source.stat()
        )


def test_candidate_capture_rejects_lstat_open_identity_mismatch(tmp_path, monkeypatch):
    # PR #1253: capture must bind the admitted lstat identity to opened bytes.
    import tree_sitter_analyzer.indexing_snapshot as snapshot_module

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    admitted = source.stat()
    metadata = (b"0,0,0,0,0,0",)
    monkeypatch.setattr(
        snapshot_module,
        "safe_workspace_path",
        lambda *_a, **_k: SimpleNamespace(
            kind="file", data=b"value = 1\n", metadata=metadata
        ),
    )
    monkeypatch.setattr(snapshot_module, "stable_descriptor_chain", lambda _m: ())
    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_SOURCE_CHANGED"):
        snapshot_module._capture_candidate_fingerprint(
            str(tmp_path), "app.py", admitted
        )


@requires_posix_fd
def test_candidate_capture_failure_becomes_snapshot_error(tmp_path, monkeypatch):
    # PR #1253: an oracle race is recorded instead of selecting unsafe work.
    import tree_sitter_analyzer.indexing_snapshot as snapshot_module

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    monkeypatch.setattr(
        snapshot_module,
        "_capture_candidate_fingerprint",
        lambda *_a: (_ for _ in ()).throw(SourceOracleError("changed")),
    )
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=1,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: [str(source)],
        language_fn=_python_language,
    )
    assert (snapshot.selected, snapshot.errors, snapshot.entries[0].reason) == (
        0,
        1,
        "changed",
    )


def test_empty_candidate_hash_uses_windows_metadata_cache_semantics(tmp_path):
    # PR #1253 thread 3756001907: Windows fingerprints carry no captured hash.
    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=1,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: [str(source)],
        language_fn=_python_language,
    )
    entry = snapshot.selected_entries[0]
    empty = replace(entry.fingerprint, content_hash="")
    snapshot = replace(snapshot, entries=(replace(entry, fingerprint=empty),))
    conn = _index_conn()
    conn.execute(
        "INSERT INTO ast_index VALUES (?, ?, ?, ?, ?)",
        ("app.py", "writer-hash", empty.mtime_ns, empty.file_size, 1),
    )

    stats, candidates, count = _partition(snapshot, conn)

    assert (stats["cached"], candidates, count) == (1, [], 1)


def test_candidate_discovery_rejects_unstringifiable_path_without_close(tmp_path):
    # PR #1253: malformed walker entries consume the bounded error path.
    class BadPath:
        def __str__(self):
            raise UnicodeError("bad path")

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=1,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: iter((BadPath(),)),
        language_fn=_python_language,
    )

    assert (snapshot.errors, snapshot.discovery_error) == (
        1,
        "INDEX_CANDIDATE_DISCOVERY_BUDGET",
    )


def test_module_exports_exact_focused_surface() -> None:
    from tree_sitter_analyzer import indexing_snapshot_worker

    assert indexing_snapshot_worker.__all__ == [
        "IndexFileFingerprint",
        "IndexSnapshotEntry",
    ]


def test_candidate_captures_share_one_absolute_discovery_deadline(
    tmp_path, monkeypatch
):
    # PR #1253 thread 3757429372: each file consumes the outer five-second budget.
    import tree_sitter_analyzer.indexing_snapshot as snapshot_module

    sources = [tmp_path / "a.py", tmp_path / "b.py"]
    for source in sources:
        source.write_text("value = 1\n")
    deadlines = []

    def capture(_root, _rel_path, admitted, deadline=None):
        deadlines.append(deadline)
        return snapshot_module.IndexFileFingerprint.from_stat(admitted)

    monkeypatch.setattr(snapshot_module, "_capture_candidate_fingerprint", capture)
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=2,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: [str(source) for source in sources],
        language_fn=_python_language,
    )

    assert (snapshot.selected, deadlines[0], deadlines[1]) == (
        2,
        deadlines[0],
        deadlines[0],
    )


def test_production_scandir_charges_unsupported_entries_and_closes(
    monkeypatch, tmp_path
):
    # PR #1253 review thread 3757754336: filtered names must consume discovery budget.
    import tree_sitter_analyzer.indexing_snapshot as snapshot_module

    class UnsupportedEntries:
        def __init__(self) -> None:
            self.consumed = 0
            self.closed = False

        def __iter__(self):
            return self

        def __next__(self):
            if self.consumed == 1_000_000:
                raise StopIteration
            self.consumed += 1
            return SimpleNamespace(
                path=str(tmp_path / f"unsupported-{self.consumed}.txt"),
                name=f"unsupported-{self.consumed}.txt",
                is_dir=lambda *, follow_symlinks: False,
            )

        def close(self) -> None:
            self.closed = True

    entries = UnsupportedEntries()
    monkeypatch.setattr(snapshot_module, "_CANDIDATE_ENTRY_BUDGET", 3)
    monkeypatch.setattr(snapshot_module.os, "scandir", lambda _path: entries)

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=snapshot_module.walk_index_candidate_entries,
        language_fn=_python_language,
    )

    assert (entries.consumed, entries.closed) == (4, True)
    assert (snapshot.skipped, snapshot.errors, snapshot.discovery_error) == (
        3,
        1,
        "INDEX_CANDIDATE_DISCOVERY_BUDGET",
    )


@pytest.mark.parametrize("workers", [0, 2])
def test_definition_rewrite_rebinds_incoming_call_before_marker(
    tmp_path, monkeypatch, workers
):
    # PR #1253 review thread 3757754342: generation IDs must not outlive rewrites.
    from tree_sitter_analyzer.cache import indexer

    callee = tmp_path / "callee.py"
    caller = tmp_path / "caller.py"
    callee.write_text("def target():\n    return 1\n")
    caller.write_text(
        "from callee import target\n\ndef caller():\n    return target()\n"
    )
    cache = ASTCache(str(tmp_path))
    cache.index_project(workers=workers)
    conn = cache.get_conn()
    old_id = conn.execute(
        "SELECT callee_symbol_id FROM edges WHERE kind='calls'"
    ).fetchone()[0]
    observed_at_marker = []
    real_marker = indexer._mark_call_graph_built_strict

    def assert_rebound_before_marker(connection):
        edge_id = connection.execute(
            "SELECT callee_symbol_id FROM edges WHERE kind='calls'"
        ).fetchone()[0]
        target_id = connection.execute(
            "SELECT id FROM ast_symbol_rows WHERE name='target'"
        ).fetchone()[0]
        observed_at_marker.append((edge_id, target_id))
        real_marker(connection)

    monkeypatch.setattr(
        indexer, "_mark_call_graph_built_strict", assert_rebound_before_marker
    )
    callee.write_text("def helper():\n    return 0\n\ndef target():\n    return 200\n")
    result = cache.index_project(workers=workers)
    current_id = conn.execute(
        "SELECT id FROM ast_symbol_rows WHERE name='target'"
    ).fetchone()[0]
    cache.close()

    assert (result["indexed"], observed_at_marker) == (1, [(current_id, current_id)])
    assert current_id != old_id


def test_candidate_budget_exception_without_close_is_stable(tmp_path):
    # PR #1253 review thread 3757754336: custom walkers need not expose close().
    import tree_sitter_analyzer.indexing_snapshot as snapshot_module

    class ExhaustedWalker:
        def __iter__(self):
            return self

        def __next__(self):
            raise snapshot_module._CandidateDiscoveryBudgetExceeded

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: ExhaustedWalker(),
        language_fn=_python_language,
    )

    assert (snapshot.errors, snapshot.discovery_error) == (
        1,
        "INDEX_CANDIDATE_DISCOVERY_BUDGET",
    )


def test_import_write_stops_when_schema_insert_is_rejected(monkeypatch):
    # PR #1253: a rejected import projection must stop the current generation.
    from tree_sitter_analyzer.cache import write

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_imports (file_path TEXT, language TEXT, module_path TEXT)"
    )
    rejected = []

    def reject(*args):
        rejected.append(args)
        return False

    monkeypatch.setattr(write, "_insert_import_entry", reject)
    write.write_imports_for_file(conn, "sample.py", "python", ["import package"])

    assert len(rejected) == 1
