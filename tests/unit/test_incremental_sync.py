"""Tests for incremental sync engine (incremental_sync module)."""

import json
import os
import sys
import time
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.incremental_sync import IncrementalSync
from tree_sitter_analyzer.indexing_snapshot import (
    IndexCandidateSnapshot,
    IndexSnapshotEntry,
    build_index_candidate_snapshot,
)


@pytest.fixture
def project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("def hello():\n    pass\n")
    (src / "util.py").write_text("def add(a, b):\n    return a + b\n")
    (src / "helper.js").write_text("function foo() { return 1; }\n")
    return tmp_path


@pytest.fixture
def cache(project):
    c = ASTCache(str(project))
    yield c
    c.close()


@pytest.fixture
def sync(cache):
    return IncrementalSync(cache)


def _python_language(path: str) -> str | None:
    return "python" if path.endswith(".py") else None


def _snapshot(tmp_path, *paths) -> IndexCandidateSnapshot:
    return build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: tuple(str(path) for path in paths),
        language_fn=_python_language,
    )


class TestSyncFromScratch:
    def test_sync_indexes_all_new_files(self, sync, project):
        result = sync.sync()
        assert result.new_files == 3
        assert result.updated_files == 0
        assert result.deleted_files == 0
        assert result.unchanged_files == 0

    def test_sync_populates_cache(self, sync, cache, project):
        sync.sync()
        stats = cache.get_stats()
        assert stats["total_files"] == 3

    def test_sync_details_list(self, sync, project):
        result = sync.sync()
        assert len(result.details) == 3
        for d in result.details:
            assert d["action"] == "indexed"
            assert "file" in d


class TestSyncNoChanges:
    def test_sync_unchanged_after_initial_index(self, sync, cache):
        sync.sync()
        result = sync.sync()
        assert result.new_files == 0
        assert result.updated_files == 0
        assert result.deleted_files == 0
        assert result.unchanged_files == 3


class TestSyncModifiedFile:
    def test_detects_modified_file(self, sync, cache, project):
        sync.sync()
        time.sleep(0.05)
        main_py = project / "src" / "main.py"
        main_py.write_text("def goodbye():\n    pass\n")
        os.utime(str(main_py), times=None)
        result = sync.sync()
        assert result.updated_files == 1
        assert any("main.py" in d["file"] for d in result.details)

    def test_reindexes_modified_content(self, sync, cache, project):
        sync.sync()
        time.sleep(0.05)
        main_py = project / "src" / "main.py"
        main_py.write_text("def goodbye():\n    pass\n")
        os.utime(str(main_py), times=None)
        sync.sync()
        lookup = cache.lookup(str(main_py))
        syms = lookup["symbols"]["symbols"]
        names = [s["name"] for s in syms]
        assert "goodbye" in names
        assert "hello" not in names

    def test_bulk_reindex_runs_synapse_backfill_once(self, sync, cache, project):
        sync.sync()
        (project / "src" / "main.py").write_text("def changed():\n    return 1\n")
        (project / "src" / "util.py").write_text("def changed_too():\n    return 2\n")

        with patch.object(
            cache,
            "_run_synapse_backfill",
            return_value={"resolved": 0, "errors": 0},
        ) as backfill:
            result = sync.sync()

        assert result.updated_files == 2
        assert backfill.call_count == 1
        assert cache.call_graph_built() is True


class TestSyncDeletedFile:
    def test_detects_deleted_file(self, sync, cache, project):
        sync.sync()
        (project / "src" / "helper.js").unlink()
        result = sync.sync()
        assert result.deleted_files == 1
        assert any("helper.js" in d["file"] for d in result.details)

    def test_removes_deleted_from_cache(self, sync, cache, project):
        sync.sync()
        helper = project / "src" / "helper.js"
        helper.unlink()
        sync.sync()
        assert cache.lookup(str(helper)) is None

    def test_complete_deletion_sync_restores_graph_marker(self, sync, cache, project):
        sync.sync()
        (project / "src" / "helper.js").unlink()

        with patch.object(
            cache,
            "_run_synapse_backfill",
            return_value={"resolved": 0, "errors": 0},
        ):
            sync.sync()

        assert cache.call_graph_built() is True

    def test_deletion_sync_backfill_error_keeps_graph_incomplete(
        self, sync, cache, project
    ):
        sync.sync()
        (project / "src" / "helper.js").unlink()

        with patch.object(
            cache,
            "_run_synapse_backfill",
            return_value={"resolved": 0, "errors": 1},
        ):
            sync.sync()

        assert cache.call_graph_built() is False

    def test_deletion_sync_indeterminate_backfill_keeps_graph_incomplete(
        self, sync, cache, project
    ):
        sync.sync()
        (project / "src" / "helper.js").unlink()

        with patch.object(cache, "_run_synapse_backfill", return_value=None):
            sync.sync()

        assert cache.call_graph_built() is False


class TestSyncNewFile:
    def test_detects_new_file(self, sync, cache, project):
        sync.sync()
        (project / "src" / "new_module.py").write_text("def fresh():\n    pass\n")
        result = sync.sync()
        assert result.new_files == 1
        assert any("new_module.py" in d["file"] for d in result.details)


def test_snapshot_mutation_during_backfill_is_invalidated(tmp_path):
    # PR #1172: the final backfill must not certify a stale snapshot.
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = _snapshot(tmp_path, path)
    cache = ASTCache(str(tmp_path))

    def backfill_then_mutate():
        path.write_text("value = 200\n")
        return {"resolved": 0, "errors": 0}

    try:
        with patch.object(
            cache, "_run_synapse_backfill", side_effect=backfill_then_mutate
        ):
            result = IncrementalSync(cache).sync(
                max_files=10, candidate_snapshot=snapshot
            )
        outcome = (
            result.changed_during_run_files,
            result.processed,
            cache.lookup(str(path)),
            cache.call_graph_built(),
        )
    finally:
        cache.close()

    assert outcome == (["app.py"], 0, None, False)


def test_empty_incremental_scan_keeps_graph_incomplete(tmp_path):
    # PR #1172: zero live candidates are not a complete call graph.
    cache = ASTCache(str(tmp_path))
    try:
        result = IncrementalSync(cache).sync()
        outcome = (result.scanned, cache.call_graph_built())
    finally:
        cache.close()

    assert outcome == (0, False)


class TestSyncMixedChanges:
    def test_handles_mixed_changes(self, sync, cache, project):
        sync.sync()
        (project / "src" / "new_module.py").write_text("def fresh():\n    pass\n")
        (project / "src" / "helper.js").unlink()
        time.sleep(0.05)
        main_py = project / "src" / "main.py"
        main_py.write_text("def updated():\n    pass\n")
        os.utime(str(main_py), times=None)
        result = sync.sync()
        assert result.new_files == 1
        assert result.deleted_files == 1
        assert result.updated_files == 1


class TestSyncMaxFiles:
    def test_respects_max_files(self, sync, cache, project):
        (project / "src" / "extra1.py").write_text("x = 1\n")
        (project / "src" / "extra2.py").write_text("y = 2\n")
        result = sync.sync(max_files=2)
        assert result.scanned == 2
        assert result.truncated_by_max_files is True
        assert result.to_dict()["truncated_by_max_files"] is True

    def test_truncated_scan_does_not_delete_unseen_indexed_files(self, sync, cache):
        # Incident 2026-07-26: capped scans invalidated live files beyond the cap.
        sync.sync()

        result = sync.sync(max_files=1)

        assert result.deleted_files == 0
        assert cache.get_stats()["total_files"] == 3

    def test_zero_limit_is_rejected_without_deleting_existing_index(self, sync, cache):
        # Issue #1169: zero is invalid, and validation must precede mutations.
        sync.sync()

        with pytest.raises(ValueError, match="max_files must be a positive integer"):
            sync.sync(max_files=0)

        assert cache.get_stats()["total_files"] == 3

    def test_truncated_scan_defers_real_deletion_until_complete_scan(
        self, sync, cache, project
    ):
        # Incident 2026-07-26: incomplete scans could not distinguish unseen/deleted.
        sync.sync()
        (project / "src" / "helper.js").unlink()

        truncated = sync.sync(max_files=1)

        assert truncated.deleted_files == 0
        assert cache.get_stats()["total_files"] == 3

        complete = sync.sync()
        assert complete.deleted_files == 1
        assert cache.get_stats()["total_files"] == 2


class TestSyncExcludePatterns:
    def test_excluded_new_file_is_not_indexed(self, sync, cache):
        # Incident 2026-07-26: full-index sync ignored the requested scope.
        result = sync.sync(exclude_patterns=frozenset({"src/helper.js"}))

        assert result.scanned == 2
        assert result.new_files == 2
        assert cache.get_stats()["total_files"] == 2
        assert {detail["file"] for detail in result.details} == {
            "src/main.py",
            "src/util.py",
        }

    def test_excluded_cached_file_is_not_treated_as_deleted(self, sync, cache):
        # Incident 2026-07-26: exclusion filtering could mimic a disk deletion.
        sync.sync()

        result = sync.sync(exclude_patterns=frozenset({"src/helper.js"}))

        assert result.deleted_files == 0
        assert cache.get_stats()["total_files"] == 3

    def test_deleted_excluded_file_is_removed_after_complete_scan(
        self, sync, cache, project
    ):
        # Incident 2026-07-26: exclusions must not hide real deletions forever.
        sync.sync()
        (project / "src" / "helper.js").unlink()

        result = sync.sync(exclude_patterns=frozenset({"src/helper.js"}))

        assert result.deleted_files == 1
        assert cache.get_stats()["total_files"] == 2

    def test_excluded_file_consumes_the_shared_file_limit(self, sync, cache, project):
        # Incident 2026-07-26: AST and sync phases counted scoped files differently.
        excluded = project / "src" / "helper.js"
        included = project / "src" / "main.py"
        with patch(
            "tree_sitter_analyzer.incremental_sync._walk_source_files",
            return_value=iter([str(excluded), str(included)]),
        ):
            sync.sync(
                max_files=1,
                exclude_patterns=frozenset({"src/helper.js"}),
            )

        assert cache.get_stats()["total_files"] == 0


class TestSyncCallback:
    def test_callback_receives_details(self, sync, cache, project):
        received = []
        sync.sync(callback=lambda d: received.append(d))
        assert len(received) == 3


class TestGetChanges:
    def test_get_changes_empty(self, sync, project):
        changes = sync.get_changes()
        assert len(changes["new"]) == 3
        assert len(changes["modified"]) == 0
        assert len(changes["deleted"]) == 0

    def test_get_changes_after_index(self, sync, cache, project):
        sync.sync()
        changes = sync.get_changes()
        assert len(changes["new"]) == 0
        assert len(changes["modified"]) == 0
        assert len(changes["deleted"]) == 0

    def test_get_changes_detects_modification(self, sync, cache, project):
        sync.sync()
        time.sleep(0.05)
        main_py = project / "src" / "main.py"
        main_py.write_text("def changed():\n    pass\n")
        os.utime(str(main_py), times=None)
        changes = sync.get_changes()
        assert len(changes["modified"]) == 1

    def test_get_changes_detects_deletion(self, sync, cache, project):
        sync.sync()
        (project / "src" / "helper.js").unlink()
        changes = sync.get_changes()
        assert len(changes["deleted"]) == 1

    def test_get_changes_detects_new_file(self, sync, cache, project):
        sync.sync()
        (project / "src" / "brand_new.py").write_text("z = 3\n")
        changes = sync.get_changes()
        assert len(changes["new"]) == 1


class TestSyncResultDict:
    def test_to_dict_keys(self, sync, project):
        result = sync.sync()
        d = result.to_dict()
        assert "scanned" in d
        assert "new_files" in d
        assert "updated_files" in d
        assert "deleted_files" in d
        assert "unchanged_files" in d
        assert "errors" in d
        assert "details" in d


class TestContentHashComparison:
    @pytest.mark.skipif(
        sys.platform == "win32", reason="Windows path drift — tracked separately"
    )
    def test_mtime_only_change_not_reindexed(self, sync, cache, project):
        sync.sync()
        main_py = project / "src" / "main.py"
        main_py.read_text()
        os.utime(str(main_py), times=None)
        result = sync.sync()
        assert result.updated_files == 0


class TestReturnedErrorDetails:
    """Incident 2026-07-26: returned parse failures must keep their reason."""

    def test_new_file_error_result_preserves_reason(self, sync, cache):
        with patch.object(
            cache,
            "index_file",
            return_value={
                "status": "error",
                "reason": "Swift grammar not installed",
            },
        ):
            detail = sync._index_new_file(
                "src/bad.swift",
                "/project/src/bad.swift",
                cache.get_conn(),
            )

        assert detail == {
            "file": "src/bad.swift",
            "considered": "indexed",
            "action": "indexed",
            "status": "error",
            "reason": "Swift grammar not installed",
        }

    def test_modified_file_error_result_preserves_reason(self, sync, cache):
        with (
            patch.object(cache, "invalidate"),
            patch.object(
                cache,
                "index_file",
                return_value={
                    "status": "error",
                    "reason": "LUA grammar not installed",
                },
            ),
        ):
            detail = sync._reindex_modified(
                "src/bad.lua",
                "/project/src/bad.lua",
                cache.get_conn(),
            )

        assert detail == {
            "file": "src/bad.lua",
            "considered": "updated",
            "action": "updated",
            "status": "error",
            "reason": "LUA grammar not installed",
        }

    def test_public_sync_attributes_returned_error_and_continues(
        self, sync, cache, project
    ):
        bad_file = project / "src" / "bad.swift"
        bad_file.write_text("func broken() {}\n")
        original_index_file = cache.index_file

        def index_file(path):
            if path == str(bad_file):
                return {
                    "status": "error",
                    "reason": "Swift grammar not installed",
                }
            return original_index_file(path)

        with patch.object(cache, "index_file", side_effect=index_file):
            result = sync.sync()

        assert result.errors == 1
        assert result.new_files == 4
        assert [d for d in result.details if d.get("status") == "error"] == [
            {
                "file": "src/bad.swift",
                "considered": "indexed",
                "action": "indexed",
                "status": "error",
                "reason": "Swift grammar not installed",
            }
        ]


class TestRecursionErrorHandling:
    """Issue #805: RecursionError from deeply-nested AST must not abort sync."""

    def test_recursion_error_in_one_file_does_not_abort_sync(self, project, cache):
        """A RecursionError in index_file must be caught per-file; sibling files
        must still be indexed and the error count must equal exactly 1."""
        src = project / "src"
        # pathological.py triggers RecursionError; good.py must still be indexed.
        (src / "pathological.py").write_text("x = 1\n")
        (src / "good.py").write_text("def ok(): pass\n")

        original_index_file = cache.index_file

        def _boom_on_pathological(path, language=None):
            if "pathological" in path:
                raise RecursionError("maximum recursion depth exceeded")
            return original_index_file(path, language)

        sync = IncrementalSync(cache)
        with patch.object(cache, "index_file", side_effect=_boom_on_pathological):
            result = sync.sync()

        # Exactly 1 file must have errored — not more, not less.
        assert result.errors == 1
        # The total new-file attempts includes all files; the pathological one
        # is counted as an attempt but ends in error.
        # good.py (+ the original 3 fixtures) must have been attempted and
        # succeeded; the pathological file must appear in details as an error.
        error_details = [d for d in result.details if d.get("status") == "error"]
        assert len(error_details) == 1
        assert "pathological" in error_details[0]["file"]
        # The error detail must carry exception type and message (Issue #806).
        assert "RecursionError" in error_details[0].get("error_type", "")
        assert error_details[0].get("error_message") != ""

    def test_recursion_error_detail_has_file_attribution(self, project, cache):
        """Error envelope must contain file path (Issue #806 partial fix)."""
        src = project / "src"
        (src / "deep_nest.py").write_text("y = 2\n")

        original_index_file = cache.index_file

        def _boom(path, language=None):
            if "deep_nest" in path:
                raise RecursionError("max depth")
            return original_index_file(path, language)

        sync = IncrementalSync(cache)
        with patch.object(cache, "index_file", side_effect=_boom):
            result = sync.sync()

        error_details = [d for d in result.details if d.get("status") == "error"]
        assert len(error_details) == 1
        detail = error_details[0]
        assert "deep_nest" in detail["file"]
        assert detail.get("error_type") == "RecursionError"


class TestAnyExceptionDoesNotAbortSync:
    """Issue #806: non-RecursionError per-file exceptions must not abort the whole sync."""

    def test_value_error_in_one_file_does_not_abort_sync(self, project, cache):
        """A ValueError in index_file must be caught; sibling files must still be indexed."""
        src = project / "src"
        (src / "bad.py").write_text("x = 1\n")
        (src / "good.py").write_text("def ok(): pass\n")

        original_index_file = cache.index_file

        def _boom_on_bad(path, language=None):
            if "bad.py" in path:
                raise ValueError("unexpected content")
            return original_index_file(path, language)

        sync = IncrementalSync(cache)
        with patch.object(cache, "index_file", side_effect=_boom_on_bad):
            result = sync.sync()

        assert result.errors == 1
        error_details = [d for d in result.details if d.get("status") == "error"]
        assert len(error_details) == 1
        assert "bad.py" in error_details[0]["file"]
        assert error_details[0].get("error_type") == "ValueError"
        assert error_details[0].get("error_message") == "unexpected content"

    def test_os_error_in_one_file_does_not_abort_sync(self, project, cache):
        """An OSError in index_file must be caught; remaining files still indexed."""
        src = project / "src"
        (src / "unreadable.py").write_text("y = 2\n")

        original_index_file = cache.index_file

        def _boom_os(path, language=None):
            if "unreadable" in path:
                raise OSError("permission denied")
            return original_index_file(path, language)

        sync = IncrementalSync(cache)
        with patch.object(cache, "index_file", side_effect=_boom_os):
            result = sync.sync()

        assert result.errors == 1
        error_details = [d for d in result.details if d.get("status") == "error"]
        assert len(error_details) == 1
        assert "unreadable" in error_details[0]["file"]
        assert error_details[0].get("error_type") == "OSError"


class TestSavepointRollbackOnPartialWrite:
    """Issue #886: savepoint must roll back partial ast_index writes on mid-write failure.

    Scenario: index_file inserts into ast_index then raises before conn.commit().
    Without a savepoint, the outer sync's final commit picks up the partial row —
    the file then appears as "unchanged" on the next sync, hiding missing symbols.
    """

    def test_partial_write_rolled_back_so_next_sync_treats_file_as_new(
        self, project, cache
    ):
        src = project / "src"
        (src / "flaky.py").write_text("def boom(): pass\n")

        original_write_imports = cache._write_imports_for_file

        def _fail_after_ast_index(conn, rel_path, language, imports):
            if "flaky.py" in rel_path:
                # Simulate failure AFTER ast_index INSERT but BEFORE conn.commit().
                raise RuntimeError("simulated mid-write failure")
            return original_write_imports(conn, rel_path, language, imports)

        sync = IncrementalSync(cache)
        with patch.object(
            cache, "_write_imports_for_file", side_effect=_fail_after_ast_index
        ):
            result = sync.sync()

        assert result.errors == 1

        # #886: savepoint must have rolled back the partial ast_index row so
        # the file does NOT silently appear unchanged on the next sync.
        conn = cache.get_conn()
        row = conn.execute(
            "SELECT file_path FROM ast_index WHERE file_path LIKE '%flaky.py'",
        ).fetchone()
        assert row is None, (
            "ast_index must have no row for flaky.py after a mid-write rollback"
        )

    def test_second_sync_reindexes_file_after_savepoint_rollback(self, project, cache):
        src = project / "src"
        (src / "fragile.py").write_text("def ok(): pass\n")

        original_write_imports = cache._write_imports_for_file
        call_count = {"n": 0}

        def _fail_once(conn, rel_path, language, imports):
            if "fragile.py" in rel_path and call_count["n"] == 0:
                call_count["n"] += 1
                raise RuntimeError("first attempt fails")
            return original_write_imports(conn, rel_path, language, imports)

        sync = IncrementalSync(cache)
        with patch.object(cache, "_write_imports_for_file", side_effect=_fail_once):
            first_result = sync.sync()

        assert first_result.errors == 1

        # Second sync must index fragile.py as NEW (not see it as unchanged).
        second_result = sync.sync()
        new_file_names = [
            d["file"] for d in second_result.details if d.get("considered") == "indexed"
        ]
        assert any("fragile.py" in f for f in new_file_names), (
            f"fragile.py must be re-indexed as new on second sync; got {new_file_names}"
        )


def test_incremental_sync_preserves_snapshot_candidate_order(tmp_path):
    first = tmp_path / "z.py"
    second = tmp_path / "a.py"
    first.write_text("z = 1\n")
    second.write_text("a = 1\n")
    snapshot = _snapshot(tmp_path, first, second)
    cache = ASTCache(str(tmp_path))
    seen: list[str] = []
    original = cache.index_file

    def record(path: str, language: str | None = None):
        seen.append(os.path.basename(path))
        return original(path, language)

    try:
        with patch.object(cache, "index_file", side_effect=record):
            result = IncrementalSync(cache).sync(
                max_files=10,
                candidate_snapshot=snapshot,
            )
    finally:
        cache.close()

    assert result.processed == 2
    assert seen == ["z.py", "a.py"]


def test_incremental_sync_snapshot_error_does_not_mark_graph_complete(tmp_path):
    missing = tmp_path / "missing.py"
    snapshot = IndexCandidateSnapshot(
        project_root=os.path.abspath(tmp_path),
        max_files=10,
        entries=(
            IndexSnapshotEntry(
                abs_path=str(missing),
                rel_path="missing.py",
                language="python",
                decision="error",
                reason="stat failed",
            ),
        ),
        present_paths=frozenset({"missing.py"}),
        discovered=1,
        selected=0,
        excluded=0,
        skipped=0,
        errors=1,
        limited=0,
    )
    cache = ASTCache(str(tmp_path))

    try:
        result = IncrementalSync(cache).sync(
            max_files=10,
            candidate_snapshot=snapshot,
        )
        graph_built = cache.call_graph_built()
    finally:
        cache.close()

    assert result.errors == 0
    assert graph_built is False


def test_incremental_sync_reports_mutation_during_processing(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = _snapshot(tmp_path, path)
    cache = ASTCache(str(tmp_path))
    original = cache.index_file
    callback_details: list[dict] = []

    def index_then_mutate(file_path: str, language: str | None = None):
        indexed = original(file_path, language)
        path.write_text("value = 200\n")
        return indexed

    try:
        with patch.object(cache, "index_file", side_effect=index_then_mutate):
            result = IncrementalSync(cache).sync(
                max_files=10,
                candidate_snapshot=snapshot,
                callback=callback_details.append,
            )
    finally:
        cache.close()

    assert result.changed_during_run == 1
    assert result.changed_during_run_files == ["app.py"]
    assert result.processed == 0
    assert result.details[-1]["reason"] == "file changed after candidate snapshot"
    assert callback_details[-1]["reason"] == "file changed after candidate snapshot"


def test_incremental_sync_rolls_back_mutation_during_processing(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("import os\n\ndef before():\n    return os.getcwd()\n")
    snapshot = _snapshot(tmp_path, path)
    cache = ASTCache(str(tmp_path))
    original = cache.index_file

    def index_then_mutate(file_path: str, language: str | None = None):
        indexed = original(file_path, language)
        path.write_text("def after():\n    return 2\n")
        return indexed

    try:
        with patch.object(cache, "index_file", side_effect=index_then_mutate):
            IncrementalSync(cache).sync(
                max_files=10,
                candidate_snapshot=snapshot,
            )
        conn = cache.get_conn()
        counts = {
            table: conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE file_path = ?",
                ("app.py",),
            ).fetchone()[0]
            for table in (
                "ast_index",
                "ast_symbol_rows",
                "ast_symbols_fts",
                "ast_imports",
                "ast_symbol_activation",
                "edges",
            )
        }
    finally:
        cache.close()

    assert counts == {
        "ast_index": 0,
        "ast_symbol_rows": 0,
        "ast_symbols_fts": 0,
        "ast_imports": 0,
        "ast_symbol_activation": 0,
        "edges": 0,
    }


def test_incremental_sync_detects_late_mutation_without_callback(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = _snapshot(tmp_path, path)
    cache = ASTCache(str(tmp_path))
    original = cache.index_file

    def index_then_mutate(file_path: str, language: str | None = None):
        indexed = original(file_path, language)
        path.write_text("value = 200\n")
        return indexed

    try:
        with patch.object(cache, "index_file", side_effect=index_then_mutate):
            result = IncrementalSync(cache).sync(
                max_files=10,
                candidate_snapshot=snapshot,
            )
    finally:
        cache.close()

    assert result.changed_during_run_files == ["app.py"]


def test_incremental_sync_reports_preexisting_snapshot_change_to_callback(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = _snapshot(tmp_path, path)
    path.unlink()
    cache = ASTCache(str(tmp_path))
    callback_details: list[dict] = []

    try:
        result = IncrementalSync(cache).sync(
            max_files=10,
            candidate_snapshot=snapshot,
            callback=callback_details.append,
        )
    finally:
        cache.close()

    assert result.changed_during_run == 1
    assert result.processed == 0
    assert callback_details == [
        {
            "file": "app.py",
            "considered": "skipped",
            "action": "skipped",
            "status": "skipped",
            "reason": "file disappeared after candidate snapshot",
        }
    ]


def test_preexisting_snapshot_modification_invalidates_cached_rows(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("import os\n\ndef before():\n    return os.getcwd()\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    snapshot = _snapshot(tmp_path, path)
    path.write_text("def after():\n    return 2\n")

    try:
        IncrementalSync(cache).sync(
            max_files=10,
            candidate_snapshot=snapshot,
        )
        conn = cache.get_conn()
        counts = {
            table: conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE file_path = ?",
                ("app.py",),
            ).fetchone()[0]
            for table in (
                "ast_index",
                "ast_symbol_rows",
                "ast_symbols_fts",
                "ast_imports",
                "ast_symbol_activation",
                "edges",
            )
        }
    finally:
        cache.close()

    assert counts == {
        "ast_index": 0,
        "ast_symbol_rows": 0,
        "ast_symbols_fts": 0,
        "ast_imports": 0,
        "ast_symbol_activation": 0,
        "edges": 0,
    }


def test_preexisting_snapshot_deletion_invalidates_cached_row(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    snapshot = _snapshot(tmp_path, path)
    path.unlink()

    try:
        IncrementalSync(cache).sync(
            max_files=10,
            candidate_snapshot=snapshot,
        )
        cached = cache.lookup(str(path))
    finally:
        cache.close()

    assert cached is None


def test_preexisting_snapshot_mutation_removes_ladybug_mirror(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    snapshot = _snapshot(tmp_path, path)
    mirror = tmp_path / ".ast-cache" / "knowledge-graph.lbug"
    mirror.write_text("stale")
    path.write_text("value = 200\n")

    try:
        IncrementalSync(cache).sync(
            max_files=10,
            candidate_snapshot=snapshot,
        )
        mirror_exists = mirror.exists()
    finally:
        cache.close()

    assert mirror_exists is False


def test_incremental_sync_rejects_snapshot_root_mismatch(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = _snapshot(tmp_path, path)
    other = tmp_path / "other"
    other.mkdir()
    other_cache = ASTCache(str(other))

    try:
        with pytest.raises(ValueError, match="different project root"):
            IncrementalSync(other_cache)._scan_disk_files(
                10,
                candidate_snapshot=snapshot,
            )
    finally:
        other_cache.close()


def test_incremental_sync_rejects_snapshot_limit_mismatch(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = _snapshot(tmp_path, path)
    cache = ASTCache(str(tmp_path))

    try:
        with pytest.raises(ValueError, match="different max_files"):
            IncrementalSync(cache)._scan_disk_files(
                11,
                candidate_snapshot=snapshot,
            )
    finally:
        cache.close()


def test_incremental_sync_rejects_selected_entry_without_fingerprint(tmp_path):
    snapshot = IndexCandidateSnapshot(
        project_root=os.path.abspath(tmp_path),
        max_files=10,
        entries=(
            IndexSnapshotEntry(
                abs_path=str(tmp_path / "bad.py"),
                rel_path="bad.py",
                language="python",
                decision="selected",
            ),
        ),
        present_paths=frozenset({"bad.py"}),
        discovered=1,
        selected=1,
        excluded=0,
        skipped=0,
        errors=0,
        limited=0,
    )
    cache = ASTCache(str(tmp_path))

    try:
        with pytest.raises(ValueError, match="lacks fingerprint"):
            IncrementalSync(cache)._scan_disk_files(
                10,
                candidate_snapshot=snapshot,
            )
    finally:
        cache.close()


def test_incremental_sync_ignores_file_that_disappears_during_live_scan(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))

    try:
        with (
            patch(
                "tree_sitter_analyzer.incremental_sync._walk_source_files",
                return_value=iter((str(path),)),
            ),
            patch(
                "tree_sitter_analyzer.incremental_sync.os.stat",
                side_effect=OSError("file disappeared"),
            ),
        ):
            disk_files, present_paths, truncated, changed = IncrementalSync(
                cache
            )._scan_disk_files(10)
    finally:
        cache.close()

    assert disk_files == {}
    assert present_paths == {"app.py"}
    assert truncated is False
    assert changed == []


def test_late_new_file_mutation_rolls_back_new_counter(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = _snapshot(tmp_path, path)
    cache = ASTCache(str(tmp_path))
    original = cache.index_file

    def index_then_mutate(file_path: str, language: str | None = None):
        indexed = original(file_path, language)
        path.write_text("value = 200\n")
        return indexed

    try:
        with patch.object(cache, "index_file", side_effect=index_then_mutate):
            result = IncrementalSync(cache).sync(
                max_files=10,
                candidate_snapshot=snapshot,
            )
    finally:
        cache.close()

    assert result.new_files == 0


def test_late_disappearance_reclassifies_index_error_as_snapshot_change(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = _snapshot(tmp_path, path)
    cache = ASTCache(str(tmp_path))
    original = cache.index_file

    def disappear_before_index(file_path: str, language: str | None = None):
        path.unlink()
        return original(file_path, language)

    try:
        with patch.object(cache, "index_file", side_effect=disappear_before_index):
            result = IncrementalSync(cache).sync(
                max_files=10,
                candidate_snapshot=snapshot,
            )
    finally:
        cache.close()

    assert result.errors == 0
    assert result.new_files == 0
    assert result.changed_during_run_files == ["app.py"]
    assert result.details == [
        {
            "file": "app.py",
            "considered": "skipped",
            "action": "skipped",
            "status": "skipped",
            "reason": "file disappeared after candidate snapshot",
        }
    ]


def test_late_updated_file_mutation_rolls_back_updated_counter(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    path.write_text("value = 2\n")
    snapshot = _snapshot(tmp_path, path)
    original = cache.index_file

    def index_then_mutate(file_path: str, language: str | None = None):
        indexed = original(file_path, language)
        path.write_text("value = 300\n")
        return indexed

    try:
        with patch.object(cache, "index_file", side_effect=index_then_mutate):
            result = IncrementalSync(cache).sync(
                max_files=10,
                candidate_snapshot=snapshot,
            )
    finally:
        cache.close()

    assert result.updated_files == 0


def test_late_unchanged_file_mutation_rolls_back_unchanged_counter(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    snapshot = _snapshot(tmp_path, path)

    def unchanged_then_mutate(*_args):
        path.write_text("value = 200\n")
        return False

    try:
        sync = IncrementalSync(cache)
        with patch.object(sync, "_file_changed", side_effect=unchanged_then_mutate):
            result = sync.sync(
                max_files=10,
                candidate_snapshot=snapshot,
            )
    finally:
        cache.close()

    assert result.unchanged_files == 0


def test_late_mutation_unresolves_edges_from_other_files(tmp_path):
    target = tmp_path / "target.py"
    caller = tmp_path / "caller.py"
    target.write_text("def target():\n    return 1\n")
    caller.write_text(
        "from target import target\n\ndef caller():\n    return target()\n"
    )
    cache = ASTCache(str(tmp_path))
    cache.index_project(workers=0)
    snapshot = _snapshot(tmp_path, target, caller)
    sync = IncrementalSync(cache)
    real_file_changed = sync._file_changed
    conn = cache.get_conn()
    before = conn.execute(
        "SELECT callee_resolved_file FROM edges "
        "WHERE kind = 'calls' AND file_path = 'caller.py' "
        "AND callee_name = 'target'"
    ).fetchone()

    def unchanged_then_mutate(disk_info, indexed_info, rel_path):
        if rel_path == "target.py":
            target.write_text("def target():\n    return 200\n")
            return False
        return real_file_changed(disk_info, indexed_info, rel_path)

    try:
        with patch.object(sync, "_file_changed", side_effect=unchanged_then_mutate):
            sync.sync(max_files=10, candidate_snapshot=snapshot)
        after = conn.execute(
            "SELECT callee_resolution, callee_resolved_file, "
            "callee_symbol_id, metadata FROM edges "
            "WHERE kind = 'calls' AND file_path = 'caller.py' "
            "AND callee_name = 'target'"
        ).fetchone()
    finally:
        cache.close()

    metadata = json.loads(after["metadata"])
    assert (
        before["callee_resolved_file"],
        after["callee_resolution"],
        after["callee_resolved_file"],
        after["callee_symbol_id"],
        metadata["callee_resolution"],
        metadata["callee_resolved_file"],
        metadata["callee_symbol_id"],
    ) == ("target.py", "unknown", "", None, "unknown", "", None)
