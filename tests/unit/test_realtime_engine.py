"""
Tests for graph/realtime.py module.

TDD: Testing real-time file watching and graph updates.
"""

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer_v2.graph.realtime import (
    FileWatcher,
    RealtimeUpdateEngine,
)
from tree_sitter_analyzer_v2.graph.advanced_storage import CodeGraphStorage


class TestFileWatcher:
    """Test FileWatcher class."""

    def test_initial_scan_detects_files(self) -> None:
        """Should detect files on initial scan."""
        watcher = FileWatcher()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("x = 1\n")
            
            changes = watcher.scan(tmpdir)
            
            assert len(changes) >= 1
            assert changes[0]["type"] == "added"

    def test_detect_modified_files(self) -> None:
        """Should detect modified files."""
        watcher = FileWatcher()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.py"
            file_path.write_text("x = 1\n")
            
            # Initial scan
            watcher.scan(tmpdir)
            
            # Modify file
            time.sleep(0.1)
            file_path.write_text("x = 2\n")
            
            # Second scan
            changes = watcher.scan(tmpdir)
            
            modified = [c for c in changes if c["type"] == "modified"]
            assert len(modified) >= 1

    def test_detect_deleted_files(self) -> None:
        """Should detect deleted files."""
        watcher = FileWatcher()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.py"
            file_path.write_text("x = 1\n")
            
            # Initial scan
            watcher.scan(tmpdir)
            
            # Delete file
            file_path.unlink()
            
            # Second scan
            changes = watcher.scan(tmpdir)
            
            deleted = [c for c in changes if c["type"] == "deleted"]
            assert len(deleted) >= 1

    def test_register_callback(self) -> None:
        """Should call registered callbacks on changes."""
        watcher = FileWatcher()
        callback = MagicMock()
        watcher.register_callback(callback)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("x = 1\n")
            
            watcher.scan(tmpdir)
            
            callback.assert_called()

    def test_filter_by_extensions(self) -> None:
        """Should filter by file extensions."""
        watcher = FileWatcher()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("python\n")
            (Path(tmpdir) / "test.txt").write_text("text\n")
            
            # Only scan Python files
            changes = watcher.scan(tmpdir, extensions=[".py"])
            
            assert len(changes) == 1
            assert "test.py" in changes[0]["file"]

    def test_compute_hash(self) -> None:
        """Should compute file hash."""
        watcher = FileWatcher()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("content\n")
            f.flush()
            path = Path(f.name)
        
        try:
            hash1 = watcher._compute_hash(path)
            assert hash1 is not None
            assert len(hash1) == 32  # MD5 hex
            
            # Same content = same hash
            hash2 = watcher._compute_hash(path)
            assert hash1 == hash2
        finally:
            path.unlink()


class TestRealtimeUpdateEngine:
    """Test RealtimeUpdateEngine class."""

    def test_init(self) -> None:
        """Should initialize engine."""
        storage = CodeGraphStorage()
        engine = RealtimeUpdateEngine(storage)
        
        assert engine.storage == storage
        assert engine.watcher is not None

    def test_watch_directory(self) -> None:
        """Should start watching directory."""
        storage = CodeGraphStorage()
        engine = RealtimeUpdateEngine(storage)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("x = 1\n")
            
            # Should not raise
            engine.watch(tmpdir)

    def test_scan_for_changes(self) -> None:
        """Should scan for changes."""
        storage = CodeGraphStorage()
        engine = RealtimeUpdateEngine(storage)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("x = 1\n")
            
            changes = engine.scan_for_changes(tmpdir)
            
            assert len(changes) >= 1

    def test_subscribe(self) -> None:
        """Should subscribe to query."""
        storage = CodeGraphStorage()
        engine = RealtimeUpdateEngine(storage)
        
        callback = MagicMock()
        engine.subscribe("MATCH (n) RETURN n", callback)
        
        assert "MATCH (n) RETURN n" in engine.subscriptions
        assert callback in engine.subscriptions["MATCH (n) RETURN n"]

    def test_unsubscribe(self) -> None:
        """Should unsubscribe from query."""
        storage = CodeGraphStorage()
        engine = RealtimeUpdateEngine(storage)
        
        callback = MagicMock()
        engine.subscribe("query", callback)
        engine.unsubscribe("query", callback)
        
        assert "query" not in engine.subscriptions

    def test_on_file_changed_notifies_subscriptions(self) -> None:
        """Should notify subscriptions on file change."""
        storage = CodeGraphStorage()
        engine = RealtimeUpdateEngine(storage)
        
        callback = MagicMock()
        engine.subscribe("test_query", callback)
        
        # Simulate file change
        engine._on_file_changed({"type": "modified", "file": "test.py"})
        
        callback.assert_called()

    def test_handle_added_file(self) -> None:
        """Should handle added file event."""
        storage = CodeGraphStorage()
        engine = RealtimeUpdateEngine(storage)
        
        # Should not raise
        engine._on_file_changed({"type": "added", "file": "new.py"})

    def test_handle_deleted_file(self) -> None:
        """Should handle deleted file event."""
        storage = CodeGraphStorage()
        engine = RealtimeUpdateEngine(storage)
        
        # Should not raise
        engine._on_file_changed({"type": "deleted", "file": "old.py"})
