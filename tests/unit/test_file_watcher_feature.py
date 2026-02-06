"""
Tests for features/file_watcher.py module.

TDD: Testing file watching functionality.
"""

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer_v2.features.file_watcher import (
    FileWatcher,
    watch_directory,
)


class TestFileWatcher:
    """Test FileWatcher class."""

    def test_init(self) -> None:
        """Should initialize with directory and pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = FileWatcher(Path(tmpdir), "*.py")
            
            assert watcher.directory == Path(tmpdir)
            assert watcher.pattern == "*.py"
            assert watcher.running is False

    def test_scan_files(self) -> None:
        """Should scan files and record mtimes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("x = 1\n")
            
            watcher = FileWatcher(Path(tmpdir))
            watcher._scan_files()
            
            assert len(watcher.file_mtimes) >= 1

    def test_scan_files_nonexistent_dir(self) -> None:
        """Should handle non-existent directory."""
        watcher = FileWatcher(Path("/nonexistent"))
        watcher._scan_files()  # Should not raise
        
        assert len(watcher.file_mtimes) == 0

    def test_check_changes_new_file(self) -> None:
        """Should detect new files."""
        callback = MagicMock()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = FileWatcher(Path(tmpdir), callback=callback)
            watcher._scan_files()
            
            # Create new file
            (Path(tmpdir) / "new.py").write_text("x = 1\n")
            
            watcher._check_changes()
            
            callback.assert_called()

    def test_check_changes_modified_file(self) -> None:
        """Should detect modified files."""
        callback = MagicMock()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.py"
            file_path.write_text("x = 1\n")
            
            watcher = FileWatcher(Path(tmpdir), callback=callback)
            watcher._scan_files()
            
            # Modify file
            time.sleep(0.1)
            file_path.write_text("x = 2\n")
            
            watcher._check_changes()
            
            callback.assert_called()

    def test_check_changes_deleted_file(self) -> None:
        """Should detect deleted files."""
        callback = MagicMock()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.py"
            file_path.write_text("x = 1\n")
            
            watcher = FileWatcher(Path(tmpdir), callback=callback)
            watcher._scan_files()
            
            # Delete file
            file_path.unlink()
            
            watcher._check_changes()
            
            callback.assert_called()

    def test_start_stop(self) -> None:
        """Should start and stop watching."""
        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = FileWatcher(Path(tmpdir))
            
            watcher.start(interval=0.1)
            assert watcher.running is True
            
            time.sleep(0.2)
            
            watcher.stop()
            assert watcher.running is False

    def test_start_already_running(self) -> None:
        """Should not start if already running."""
        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = FileWatcher(Path(tmpdir))
            
            watcher.start(interval=0.5)
            thread1 = watcher.thread
            
            watcher.start(interval=0.5)  # Should be ignored
            thread2 = watcher.thread
            
            assert thread1 is thread2
            
            watcher.stop()

    def test_trigger_callback_handles_exception(self) -> None:
        """Should handle callback exceptions."""
        def bad_callback(path):
            raise Exception("Error")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = FileWatcher(Path(tmpdir), callback=bad_callback)
            
            # Should not raise
            watcher._trigger_callback(Path(tmpdir) / "test.py", "modified")


class TestWatchDirectory:
    """Test watch_directory convenience function."""

    def test_watch_directory(self) -> None:
        """Should create and start watcher."""
        callback = MagicMock()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = watch_directory(
                Path(tmpdir),
                callback,
                pattern="*.py",
                interval=0.5
            )
            
            try:
                assert watcher.running is True
                assert watcher.directory == Path(tmpdir)
            finally:
                watcher.stop()
