"""Tests for incremental sync engine (incremental_sync module)."""

import os
import sys
import time
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.incremental_sync import IncrementalSync


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


class TestSyncNewFile:
    def test_detects_new_file(self, sync, cache, project):
        sync.sync()
        (project / "src" / "new_module.py").write_text("def fresh():\n    pass\n")
        result = sync.sync()
        assert result.new_files == 1
        assert any("new_module.py" in d["file"] for d in result.details)


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
