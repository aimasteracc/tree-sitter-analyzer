"""Tests for incremental sync engine (incremental_sync module)."""

import os
import sys
import time

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
        assert result.updated_files >= 1
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
        assert result.deleted_files >= 1
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
        assert result.new_files >= 1
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
        assert result.new_files >= 1
        assert result.deleted_files >= 1
        assert result.updated_files >= 1


class TestSyncMaxFiles:
    def test_respects_max_files(self, sync, cache, project):
        (project / "src" / "extra1.py").write_text("x = 1\n")
        (project / "src" / "extra2.py").write_text("y = 2\n")
        result = sync.sync(max_files=2)
        assert result.scanned <= 2


class TestSyncCallback:
    def test_callback_receives_details(self, sync, cache, project):
        received = []
        sync.sync(callback=lambda d: received.append(d))
        assert len(received) >= 3


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
        assert len(changes["modified"]) >= 1

    def test_get_changes_detects_deletion(self, sync, cache, project):
        sync.sync()
        (project / "src" / "helper.js").unlink()
        changes = sync.get_changes()
        assert len(changes["deleted"]) >= 1

    def test_get_changes_detects_new_file(self, sync, cache, project):
        sync.sync()
        (project / "src" / "brand_new.py").write_text("z = 3\n")
        changes = sync.get_changes()
        assert len(changes["new"]) >= 1


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
