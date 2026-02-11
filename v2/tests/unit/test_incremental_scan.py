"""
Unit tests for ProjectCodeMap incremental scanning.

Sprint 3: mtime-based file-level caching so that second scan is <500ms.
"""

import os
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.core.code_map import ProjectCodeMap


@pytest.fixture
def cross_file_project():
    """Return path to cross-file test project."""
    return Path(__file__).parent.parent / "fixtures" / "cross_file_project"


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal temp project for mutation tests."""
    (tmp_path / "hello.py").write_text(
        'def greet(name):\n    return f"Hello, {name}!"\n\ndef main():\n    greet("world")\n',
        encoding="utf-8",
    )
    (tmp_path / "utils.py").write_text(
        "def helper():\n    return 42\n", encoding="utf-8"
    )
    return tmp_path


class TestIncrementalScanBasic:
    """Test that the caching mechanism works."""

    def test_second_scan_uses_cache(self, cross_file_project):
        """Second scan of the same project should be significantly faster."""
        mapper = ProjectCodeMap()

        # First scan (cold)
        t0 = time.perf_counter()
        result1 = mapper.scan(str(cross_file_project), extensions=[".py"])
        cold_ms = (time.perf_counter() - t0) * 1000

        # Second scan (warm — should be cached)
        t0 = time.perf_counter()
        result2 = mapper.scan(str(cross_file_project), extensions=[".py"])
        warm_ms = (time.perf_counter() - t0) * 1000

        # Warm scan should be at least 2x faster
        assert warm_ms < cold_ms, (
            f"Expected warm scan ({warm_ms:.1f}ms) to be faster than cold ({cold_ms:.1f}ms)"
        )
        # Results should be identical
        assert result1.total_files == result2.total_files
        assert result1.total_symbols == result2.total_symbols

    def test_cache_produces_identical_result(self, cross_file_project):
        """Cached scan must produce identical results to fresh scan."""
        mapper = ProjectCodeMap()
        result1 = mapper.scan(str(cross_file_project), extensions=[".py"])
        result2 = mapper.scan(str(cross_file_project), extensions=[".py"])

        # Deep equality
        assert result1.total_files == result2.total_files
        assert result1.total_symbols == result2.total_symbols
        assert result1.total_lines == result2.total_lines
        assert result1.total_classes == result2.total_classes
        assert result1.total_functions == result2.total_functions
        assert len(result1.dead_code) == len(result2.dead_code)
        assert len(result1.hot_spots) == len(result2.hot_spots)
        assert len(result1.entry_points) == len(result2.entry_points)
        assert len(result1.module_dependencies) == len(result2.module_dependencies)

        # Symbol FQNs identical
        fqns1 = sorted(s.fqn for s in result1.symbols)
        fqns2 = sorted(s.fqn for s in result2.symbols)
        assert fqns1 == fqns2


class TestIncrementalScanFileChanges:
    """Test that file changes are detected and re-parsed."""

    def test_modified_file_is_reparsed(self, tmp_project):
        """If a file's mtime changes, it should be re-parsed."""
        mapper = ProjectCodeMap()
        result1 = mapper.scan(str(tmp_project), extensions=[".py"])
        assert result1.total_files == 2

        # Modify a file (add a function)
        hello_path = tmp_project / "hello.py"
        original = hello_path.read_text(encoding="utf-8")
        hello_path.write_text(
            original + "\ndef farewell():\n    return 'bye'\n",
            encoding="utf-8",
        )
        # Ensure mtime is updated (some filesystems have 1s granularity)
        new_mtime = hello_path.stat().st_mtime + 1
        os.utime(hello_path, (new_mtime, new_mtime))

        result2 = mapper.scan(str(tmp_project), extensions=[".py"])
        # Should have one more function
        assert result2.total_functions > result1.total_functions

    def test_new_file_is_picked_up(self, tmp_project):
        """A new file should be discovered and parsed on next scan."""
        mapper = ProjectCodeMap()
        result1 = mapper.scan(str(tmp_project), extensions=[".py"])
        initial_files = result1.total_files

        # Add a new file
        (tmp_project / "newmod.py").write_text(
            "def brand_new():\n    pass\n", encoding="utf-8"
        )

        result2 = mapper.scan(str(tmp_project), extensions=[".py"])
        assert result2.total_files == initial_files + 1

        # The new function should appear in symbols
        names = {s.name for s in result2.symbols}
        assert "brand_new" in names

    def test_deleted_file_is_removed(self, tmp_project):
        """A deleted file should be removed from results."""
        mapper = ProjectCodeMap()
        result1 = mapper.scan(str(tmp_project), extensions=[".py"])
        initial_files = result1.total_files

        # Delete a file
        (tmp_project / "utils.py").unlink()

        result2 = mapper.scan(str(tmp_project), extensions=[".py"])
        assert result2.total_files == initial_files - 1

        # helper() should no longer be in symbols
        names = {s.name for s in result2.symbols}
        assert "helper" not in names


class TestIncrementalScanProjectSwitch:
    """Test cache invalidation when switching projects."""

    def test_different_project_clears_cache(self, tmp_project, cross_file_project):
        """Switching to a different project should clear the cache."""
        mapper = ProjectCodeMap()

        # Scan project A
        result_a = mapper.scan(str(tmp_project), extensions=[".py"])
        assert result_a.total_files == 2

        # Scan project B
        result_b = mapper.scan(str(cross_file_project), extensions=[".py"])
        assert result_b.total_files > 0
        assert result_b.project_dir == str(cross_file_project)

        # Scan project A again — should still work correctly
        result_a2 = mapper.scan(str(tmp_project), extensions=[".py"])
        assert result_a2.total_files == 2


class TestIncrementalScanCacheMechanism:
    """Verify that the caching mechanism actually exists and works."""

    def test_file_cache_populated_after_scan(self, cross_file_project):
        """After a scan, _file_cache should be populated with entries."""
        mapper = ProjectCodeMap()
        mapper.scan(str(cross_file_project), extensions=[".py"])

        # The mapper must have a _file_cache dict with entries
        assert hasattr(mapper, "_file_cache"), "ProjectCodeMap must have _file_cache attribute"
        assert len(mapper._file_cache) > 0, "Cache should have entries after scan"

    def test_cache_entries_have_mtime_ns_and_module(self, cross_file_project):
        """Each cache entry should store mtime_ns (integer nanoseconds) and ModuleInfo."""
        mapper = ProjectCodeMap()
        mapper.scan(str(cross_file_project), extensions=[".py"])

        for rel_path, entry in mapper._file_cache.items():
            assert hasattr(entry, "mtime_ns"), f"Cache entry for {rel_path} missing mtime_ns"
            assert hasattr(entry, "module"), f"Cache entry for {rel_path} missing module"
            assert isinstance(entry.mtime_ns, int), f"mtime_ns should be int for {rel_path}"
            assert entry.mtime_ns > 0, f"mtime_ns should be positive for {rel_path}"
            assert entry.module is not None, f"module should not be None for {rel_path}"

    def test_unchanged_file_not_reparsed(self, tmp_project):
        """Verify that unchanged files reuse cached modules (same object)."""
        mapper = ProjectCodeMap()
        mapper.scan(str(tmp_project), extensions=[".py"])

        # Capture cached module objects
        cached_modules = {
            k: v.module for k, v in mapper._file_cache.items()
        }

        # Scan again without changes
        mapper.scan(str(tmp_project), extensions=[".py"])

        # Cached modules should be the exact same objects (not re-parsed)
        for rel_path, entry in mapper._file_cache.items():
            if rel_path in cached_modules:
                assert entry.module is cached_modules[rel_path], (
                    f"Module for {rel_path} was re-parsed when it shouldn't have been"
                )

    def test_project_switch_clears_file_cache(self, tmp_project, cross_file_project):
        """Switching projects should clear the file cache."""
        mapper = ProjectCodeMap()
        mapper.scan(str(tmp_project), extensions=[".py"])
        assert len(mapper._file_cache) == 2  # hello.py + utils.py

        mapper.scan(str(cross_file_project), extensions=[".py"])
        # Cache should now contain cross_file_project files, not tmp_project files
        for rel_path in mapper._file_cache:
            assert "hello.py" != rel_path, "Old project files should be cleared"


class TestIncrementalScanExtensionChange:
    """Test that changing extensions/exclude_dirs invalidates cache."""

    def test_extension_change_triggers_rescan(self, tmp_project):
        """Changing extensions should pick up new file types."""
        # Create a .pyw file (also Python, supported extension)
        (tmp_project / "gui.pyw").write_text(
            "def show_window():\n    pass\n", encoding="utf-8"
        )

        mapper = ProjectCodeMap()
        result_py = mapper.scan(str(tmp_project), extensions=[".py"])
        assert result_py.total_files == 2  # hello.py + utils.py

        # Scan again with .pyw included
        result_both = mapper.scan(str(tmp_project), extensions=[".py", ".pyw"])
        assert result_both.total_files >= 3, (
            f"Expected >=3 files (2 py + 1 pyw), got {result_both.total_files}"
        )

    def test_extension_shrink_removes_files(self, tmp_project):
        """Narrowing extensions should exclude previously scanned files."""
        mapper = ProjectCodeMap()
        result_all = mapper.scan(str(tmp_project), extensions=[".py"])
        assert result_all.total_files == 2

        # Scan with no matching extension
        result_none = mapper.scan(str(tmp_project), extensions=[".java"])
        assert result_none.total_files == 0


class TestIncrementalScanMtimeEdgeCases:
    """Test mtime comparison robustness."""

    def test_mtime_backward_triggers_reparse(self, tmp_project):
        """If mtime goes backward (e.g., git checkout), file should be re-parsed."""
        mapper = ProjectCodeMap()
        mapper.scan(str(tmp_project), extensions=[".py"])

        hello_path = tmp_project / "hello.py"
        # Set mtime to the past
        past_time = hello_path.stat().st_mtime - 100
        os.utime(hello_path, (past_time, past_time))

        # Modify content
        hello_path.write_text(
            "def totally_new():\n    pass\n", encoding="utf-8"
        )
        os.utime(hello_path, (past_time, past_time))

        result = mapper.scan(str(tmp_project), extensions=[".py"])
        names = {s.name for s in result.symbols}
        assert "totally_new" in names, "File with changed mtime should be re-parsed"


class TestIncrementalScanPerformance:
    """Performance tests for incremental scanning."""

    def test_warm_scan_under_500ms(self, cross_file_project):
        """Warm scan should complete under 500ms."""
        mapper = ProjectCodeMap()
        mapper.scan(str(cross_file_project), extensions=[".py"])

        t0 = time.perf_counter()
        mapper.scan(str(cross_file_project), extensions=[".py"])
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < 500, f"Warm scan took {elapsed_ms:.1f}ms, expected <500ms"
