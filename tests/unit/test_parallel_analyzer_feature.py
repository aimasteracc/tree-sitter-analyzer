"""
Tests for features/parallel_analyzer.py module.

TDD: Testing parallel analysis functionality.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer_v2.features.parallel_analyzer import (
    AnalysisResult,
    ParallelAnalyzer,
    analyze_project,
)


class TestAnalysisResult:
    """Test AnalysisResult dataclass."""

    def test_default_values(self) -> None:
        """Should have correct default values."""
        result = AnalysisResult()
        
        assert result.total_files == 0
        assert result.success_files == 0
        assert result.failed_files == 0
        assert result.results == []
        assert result.errors == []


class TestParallelAnalyzer:
    """Test ParallelAnalyzer class."""

    def test_init_default_workers(self) -> None:
        """Should initialize with default workers."""
        analyzer = ParallelAnalyzer()
        assert analyzer.max_workers > 0

    def test_init_custom_workers(self) -> None:
        """Should accept custom worker count."""
        analyzer = ParallelAnalyzer(max_workers=4)
        assert analyzer.max_workers == 4

    def test_analyze_nonexistent_directory(self) -> None:
        """Should handle non-existent directory."""
        analyzer = ParallelAnalyzer()
        result = analyzer.analyze_directory(Path("/nonexistent"))
        
        assert result.total_files == 0

    def test_analyze_empty_directory(self) -> None:
        """Should handle empty directory."""
        analyzer = ParallelAnalyzer()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = analyzer.analyze_directory(Path(tmpdir))
            
            assert result.total_files == 0

    def test_analyze_single_file_serial(self) -> None:
        """Should analyze single file in serial mode."""
        analyzer = ParallelAnalyzer(max_workers=1)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("def hello():\n    pass\n")
            
            result = analyzer.analyze_directory(Path(tmpdir))
            
            assert result.total_files == 1
            assert result.success_files == 1

    def test_analyze_multiple_files_parallel(self) -> None:
        """Should analyze multiple files in parallel."""
        analyzer = ParallelAnalyzer(max_workers=2)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(5):
                (Path(tmpdir) / f"file{i}.py").write_text(f"x = {i}\n")
            
            result = analyzer.analyze_directory(Path(tmpdir))
            
            assert result.total_files == 5
            assert result.success_files == 5

    def test_progress_callback(self) -> None:
        """Should call progress callback."""
        analyzer = ParallelAnalyzer(max_workers=1)
        callback = MagicMock()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("x = 1\n")
            
            analyzer.analyze_directory(Path(tmpdir), progress_callback=callback)
            
            callback.assert_called()

    def test_duration_tracked(self) -> None:
        """Should track analysis duration."""
        analyzer = ParallelAnalyzer(max_workers=1)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("x = 1\n")
            
            result = analyzer.analyze_directory(Path(tmpdir))
            
            assert result.duration >= 0

    def test_analyze_file_content(self) -> None:
        """Should extract correct metrics from file."""
        analyzer = ParallelAnalyzer(max_workers=1)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            code = """
def func1():
    pass

class MyClass:
    pass

def func2():
    pass
"""
            (Path(tmpdir) / "test.py").write_text(code)
            
            result = analyzer.analyze_directory(Path(tmpdir))
            
            assert result.success_files == 1
            file_result = result.results[0]
            assert file_result["functions"] == 2
            assert file_result["classes"] == 1

    def test_handle_unreadable_file(self) -> None:
        """Should handle unreadable files gracefully."""
        analyzer = ParallelAnalyzer(max_workers=1)
        
        # _analyze_single_file with non-existent file
        result = analyzer._analyze_single_file(Path("/nonexistent.py"))
        
        assert result["success"] is False
        assert "error" in result


class TestAnalyzeProject:
    """Test analyze_project convenience function."""

    def test_analyze_project(self) -> None:
        """Should analyze project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "main.py").write_text("print('hello')\n")
            
            result = analyze_project(Path(tmpdir))
            
            assert result.total_files >= 1
            assert result.success_files >= 1
