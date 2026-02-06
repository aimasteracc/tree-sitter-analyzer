"""
Tests for features/incremental.py module.

TDD: Testing incremental analysis with caching.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.features.incremental import (
    FileAnalysisCache,
    IncrementalAnalyzer,
    create_analyzer,
)


class TestFileAnalysisCache:
    """Test FileAnalysisCache dataclass."""

    def test_creation(self) -> None:
        """Should create cache entry."""
        cache = FileAnalysisCache(
            content_hash="abc123",
            analysis_result={"lines": 10},
            timestamp=1234567890.0
        )
        
        assert cache.content_hash == "abc123"
        assert cache.hit_count == 0


class TestIncrementalAnalyzer:
    """Test IncrementalAnalyzer class."""

    def test_init(self) -> None:
        """Should initialize with cache size."""
        analyzer = IncrementalAnalyzer(cache_size=100)
        
        assert analyzer.cache_size == 100
        assert len(analyzer.cache) == 0

    def test_analyze_file(self) -> None:
        """Should analyze file content."""
        analyzer = IncrementalAnalyzer()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("def hello():\n    pass\n")
            f.flush()
            path = Path(f.name)
        
        try:
            result = analyzer.analyze_file(path)
            
            assert result["success"] is True
            assert result["functions"] == 1
            assert "latency_ms" in result
        finally:
            path.unlink()

    def test_analyze_file_with_content(self) -> None:
        """Should analyze provided content."""
        analyzer = IncrementalAnalyzer()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("")
            f.flush()
            path = Path(f.name)
        
        try:
            result = analyzer.analyze_file(path, content="class MyClass:\n    pass\n")
            
            assert result["success"] is True
            assert result["classes"] == 1
        finally:
            path.unlink()

    def test_cache_hit(self) -> None:
        """Should return cached result on cache hit."""
        analyzer = IncrementalAnalyzer()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x = 1\n")
            f.flush()
            path = Path(f.name)
        
        try:
            # First call - cache miss
            result1 = analyzer.analyze_file(path)
            assert result1["from_cache"] is False
            
            # Second call - cache hit
            result2 = analyzer.analyze_file(path)
            assert result2["from_cache"] is True
            
            # Check stats
            stats = analyzer.get_stats()
            assert stats["cache_hits"] >= 1
        finally:
            path.unlink()

    def test_cache_miss_on_content_change(self) -> None:
        """Should miss cache when content changes."""
        analyzer = IncrementalAnalyzer()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x = 1\n")
            f.flush()
            path = Path(f.name)
        
        try:
            # First call
            analyzer.analyze_file(path)
            
            # Modify file
            path.write_text("x = 2\ny = 3\n")
            
            # Second call - cache miss due to content change
            result = analyzer.analyze_file(path)
            assert result["from_cache"] is False
        finally:
            path.unlink()

    def test_analyze_nonexistent_file(self) -> None:
        """Should handle non-existent file."""
        analyzer = IncrementalAnalyzer()
        
        result = analyzer.analyze_file(Path("/nonexistent.py"))
        
        assert result["success"] is False
        assert "error" in result

    def test_cache_eviction(self) -> None:
        """Should evict least used entries when cache is full."""
        analyzer = IncrementalAnalyzer(cache_size=2)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create 3 files
            files = []
            for i in range(3):
                f = Path(tmpdir) / f"file{i}.py"
                f.write_text(f"x = {i}\n")
                files.append(f)
            
            # Analyze first 2 files (fills cache)
            analyzer.analyze_file(files[0])
            analyzer.analyze_file(files[1])
            assert len(analyzer.cache) == 2
            
            # Hit cache on file 0 to increase hit count
            analyzer.analyze_file(files[0])
            
            # Analyze third file (should evict file 1, not file 0)
            analyzer.analyze_file(files[2])
            
            assert len(analyzer.cache) == 2

    def test_complexity_calculation(self) -> None:
        """Should calculate complexity."""
        analyzer = IncrementalAnalyzer()
        
        code = """
def complex():
    if x:
        for i in range(10):
            while y:
                pass
"""
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()
            path = Path(f.name)
        
        try:
            result = analyzer.analyze_file(path)
            
            assert result["complexity"] > 1
        finally:
            path.unlink()

    def test_issues_long_file(self) -> None:
        """Should warn about long files."""
        analyzer = IncrementalAnalyzer()
        
        # Create file with 600 lines
        lines = ["x = 1\n"] * 600
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.writelines(lines)
            f.flush()
            path = Path(f.name)
        
        try:
            result = analyzer.analyze_file(path)
            
            has_warning = any("too long" in i["message"].lower() for i in result["issues"])
            assert has_warning
        finally:
            path.unlink()

    def test_get_stats(self) -> None:
        """Should return statistics."""
        analyzer = IncrementalAnalyzer()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x = 1\n")
            f.flush()
            path = Path(f.name)
        
        try:
            analyzer.analyze_file(path)
            analyzer.analyze_file(path)  # Cache hit
            
            stats = analyzer.get_stats()
            
            assert stats["total_requests"] == 2
            assert stats["cache_hits"] == 1
            assert stats["cache_misses"] == 1
            assert stats["cache_hit_rate"] == 0.5
        finally:
            path.unlink()

    def test_clear_cache(self) -> None:
        """Should clear cache and stats."""
        analyzer = IncrementalAnalyzer()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x = 1\n")
            f.flush()
            path = Path(f.name)
        
        try:
            analyzer.analyze_file(path)
            assert len(analyzer.cache) > 0
            
            analyzer.clear_cache()
            
            assert len(analyzer.cache) == 0
            assert analyzer.stats["total_requests"] == 0
        finally:
            path.unlink()


class TestCreateAnalyzer:
    """Test create_analyzer convenience function."""

    def test_create_analyzer(self) -> None:
        """Should create analyzer with specified cache size."""
        analyzer = create_analyzer(cache_size=500)
        
        assert analyzer.cache_size == 500
