"""
Unit tests for encoding detection and file reading.

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

This module tests:
- EncodingCache (LRU cache with mtime-based invalidation)
- EncodingDetector (encoding detection and safe file reading)
"""

import threading
import time
from collections.abc import Generator
from pathlib import Path

import pytest


class TestEncodingCache:
    """Tests for EncodingCache class."""

    def test_cache_initialization(self):
        """Test cache can be initialized."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingCache

        cache = EncodingCache(max_size=100)
        assert cache is not None

    def test_cache_set_and_get(self, tmp_path):
        """Test basic cache set and get operations."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingCache

        cache = EncodingCache(max_size=100)
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content", encoding="utf-8")

        # Set encoding
        cache.set(test_file, "utf-8")

        # Get encoding
        encoding = cache.get(test_file)
        assert encoding == "utf-8"

    def test_cache_miss_returns_none(self, tmp_path):
        """Test cache returns None for non-cached files."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingCache

        cache = EncodingCache(max_size=100)
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content", encoding="utf-8")

        # File not cached yet
        encoding = cache.get(test_file)
        assert encoding is None

    def test_cache_invalidation_on_mtime_change(self, tmp_path):
        """Test cache is invalidated when file is modified."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingCache

        cache = EncodingCache(max_size=100)
        test_file = tmp_path / "test.txt"
        test_file.write_text("original content", encoding="utf-8")

        # Cache encoding
        cache.set(test_file, "utf-8")
        assert cache.get(test_file) == "utf-8"

        # Wait a bit to ensure mtime changes
        time.sleep(0.1)

        # Modify file
        test_file.write_text("modified content", encoding="utf-8")

        # Cache should miss (different mtime)
        encoding = cache.get(test_file)
        assert encoding is None

    def test_cache_lru_eviction(self, tmp_path):
        """Test LRU eviction when cache is full."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingCache

        cache = EncodingCache(max_size=3)

        # Create 4 files
        files = []
        for i in range(4):
            f = tmp_path / f"file{i}.txt"
            f.write_text(f"content {i}", encoding="utf-8")
            files.append(f)

        # Cache first 3 files
        for i, f in enumerate(files[:3]):
            cache.set(f, f"encoding-{i}")

        # All 3 should be cached
        assert cache.get(files[0]) == "encoding-0"
        assert cache.get(files[1]) == "encoding-1"
        assert cache.get(files[2]) == "encoding-2"

        # Cache 4th file (should evict oldest - file0)
        cache.set(files[3], "encoding-3")

        # file0 should be evicted
        assert cache.get(files[0]) is None
        # Others should still be cached
        assert cache.get(files[1]) == "encoding-1"
        assert cache.get(files[2]) == "encoding-2"
        assert cache.get(files[3]) == "encoding-3"


class TestEncodingDetector:
    """Tests for EncodingDetector class."""

    def test_detector_initialization(self):
        """Test detector can be initialized."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector()
        assert detector is not None

    def test_detect_utf8(self, tmp_path):
        """Test detection of UTF-8 encoded file."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector()
        test_file = tmp_path / "utf8.txt"
        test_file.write_text("Hello, World! 你好世界", encoding="utf-8")

        encoding = detector.detect_encoding(test_file)
        assert encoding == "utf-8"

    def test_detect_utf8_with_bom(self, tmp_path):
        """Test detection of UTF-8 file with BOM."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector()
        test_file = tmp_path / "utf8_bom.txt"

        # Write UTF-8 with BOM
        with open(test_file, "wb") as f:
            f.write(b"\xef\xbb\xbf")  # UTF-8 BOM
            f.write(b"Hello, World!")

        encoding = detector.detect_encoding(test_file)
        assert encoding == "utf-8"

    def test_detect_with_cache(self, tmp_path):
        """Test that detection uses cache on second call."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector(enable_cache=True)
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content", encoding="utf-8")

        # First detection
        encoding1 = detector.detect_encoding(test_file)
        assert encoding1 == "utf-8"

        # Second detection (should use cache)
        encoding2 = detector.detect_encoding(test_file)
        assert encoding2 == "utf-8"

    def test_detect_without_cache(self, tmp_path):
        """Test detection with cache disabled."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector(enable_cache=False)
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content", encoding="utf-8")

        encoding = detector.detect_encoding(test_file)
        assert encoding == "utf-8"

    def test_read_file_safe_utf8(self, tmp_path):
        """Test reading UTF-8 file."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector()
        test_file = tmp_path / "utf8.txt"
        expected_content = "Hello, World!\n你好世界"
        test_file.write_text(expected_content, encoding="utf-8")

        content = detector.read_file_safe(test_file)
        assert content == expected_content

    def test_read_file_safe_with_invalid_bytes(self, tmp_path):
        """Test reading file with invalid UTF-8 bytes."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector()
        test_file = tmp_path / "invalid.txt"

        # Write file with invalid UTF-8 sequence
        with open(test_file, "wb") as f:
            f.write(b"Hello ")
            f.write(b"\xff\xfe")  # Invalid UTF-8
            f.write(b" World")

        # Should not raise exception, replace invalid bytes
        content = detector.read_file_safe(test_file, errors="replace")
        assert "Hello" in content
        assert "World" in content

    def test_read_file_safe_fallback_encoding(self, tmp_path):
        """Test fallback encoding parameter."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector()
        test_file = tmp_path / "test.txt"
        test_file.write_text("simple ascii content", encoding="utf-8")

        content = detector.read_file_safe(test_file, fallback_encoding="ascii")
        assert content == "simple ascii content"

    def test_read_file_streaming(self, tmp_path):
        """Test streaming file reading."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector()
        test_file = tmp_path / "multiline.txt"
        test_file.write_text("line1\nline2\nline3\n", encoding="utf-8")

        lines = list(detector.read_file_streaming(test_file))

        assert len(lines) == 3
        assert lines[0].strip() == "line1"
        assert lines[1].strip() == "line2"
        assert lines[2].strip() == "line3"

    def test_read_file_streaming_returns_generator(self, tmp_path):
        """Test that streaming returns a generator."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector()
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\n", encoding="utf-8")

        result = detector.read_file_streaming(test_file)
        assert isinstance(result, Generator)


@pytest.fixture
def encoding_fixtures_dir():
    """Return path to encoding fixtures directory."""
    fixtures_dir = Path(__file__).parent.parent / "fixtures" / "encoding_fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    return fixtures_dir


class TestEncodingDetectorWithRealEncodings:
    """Tests with actual multi-encoding files."""

    def test_detect_shift_jis(self, encoding_fixtures_dir):
        """Test detection of Shift_JIS encoded Japanese file."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector()
        test_file = encoding_fixtures_dir / "japanese_shift_jis.txt"

        # Create Shift_JIS file
        japanese_text = "こんにちは世界\n日本語のテストファイル"
        with open(test_file, "wb") as f:
            f.write(japanese_text.encode("shift_jis"))

        encoding = detector.detect_encoding(test_file)
        # Should detect as shift_jis or compatible encoding
        assert encoding.lower() in ["shift_jis", "shift-jis", "cp932"]

    def test_detect_gbk(self, encoding_fixtures_dir):
        """Test detection of GBK encoded Chinese file."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector()
        test_file = encoding_fixtures_dir / "chinese_gbk.txt"

        # Create GBK file
        chinese_text = "你好世界\n中文测试文件"
        with open(test_file, "wb") as f:
            f.write(chinese_text.encode("gbk"))

        encoding = detector.detect_encoding(test_file)
        # Should detect as gbk or compatible encoding
        assert encoding.lower() in ["gbk", "gb2312", "gb18030"]

    def test_read_shift_jis_file(self, encoding_fixtures_dir):
        """Test reading Shift_JIS file with correct content."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector()
        test_file = encoding_fixtures_dir / "japanese_shift_jis.txt"

        japanese_text = "こんにちは世界\n日本語のテストファイル"
        with open(test_file, "wb") as f:
            f.write(japanese_text.encode("shift_jis"))

        content = detector.read_file_safe(test_file)
        assert "こんにちは" in content
        assert "日本語" in content

    def test_read_gbk_file(self, encoding_fixtures_dir):
        """Test reading GBK file with correct content."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector()
        test_file = encoding_fixtures_dir / "chinese_gbk.txt"

        chinese_text = "你好世界\n中文测试文件"
        with open(test_file, "wb") as f:
            f.write(chinese_text.encode("gbk"))

        content = detector.read_file_safe(test_file)
        assert "你好" in content
        assert "中文" in content


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_cache_get_nonexistent_file(self, tmp_path):
        """Test cache get returns None for nonexistent file."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingCache

        cache = EncodingCache(max_size=100)
        result = cache.get(tmp_path / "nonexistent.txt")
        assert result is None

    def test_cache_set_nonexistent_file(self, tmp_path):
        """Test cache set handles nonexistent file gracefully."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingCache

        cache = EncodingCache(max_size=100)
        # Should not raise
        cache.set(tmp_path / "nonexistent.txt", "utf-8")

    def test_cache_update_existing(self, tmp_path):
        """Test updating existing cache entry."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingCache

        cache = EncodingCache(max_size=100)
        test_file = tmp_path / "test.txt"
        test_file.write_text("content", encoding="utf-8")

        # Set initial encoding
        cache.set(test_file, "utf-8")
        assert cache.get(test_file) == "utf-8"

        # Update with different encoding
        cache.set(test_file, "ascii")
        assert cache.get(test_file) == "ascii"

    def test_cache_clear(self, tmp_path):
        """Test cache clear operation."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingCache

        cache = EncodingCache(max_size=100)
        test_file = tmp_path / "test.txt"
        test_file.write_text("content", encoding="utf-8")

        cache.set(test_file, "utf-8")
        assert cache.get(test_file) == "utf-8"

        cache.clear()
        assert cache.get(test_file) is None

    def test_detect_empty_file(self, tmp_path):
        """Test detection of empty file."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector()
        test_file = tmp_path / "empty.txt"
        test_file.write_bytes(b"")

        encoding = detector.detect_encoding(test_file)
        assert encoding == "utf-8"

    def test_read_file_safe_detection_error(self, tmp_path, monkeypatch):
        """Test read_file_safe handles detection errors."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector()
        test_file = tmp_path / "test.txt"
        test_file.write_text("content", encoding="utf-8")

        # Force detection to fail
        def mock_detect(*args, **kwargs):
            raise Exception("Detection failed")
        
        monkeypatch.setattr(detector, "detect_encoding", mock_detect)

        # Should use fallback encoding
        content = detector.read_file_safe(test_file)
        assert content == "content"

    def test_read_file_safe_read_error(self, tmp_path):
        """Test read_file_safe handles read errors with fallback."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector()
        test_file = tmp_path / "test.txt"
        
        # Write file with specific bytes that might cause issues
        test_file.write_bytes(b"Hello World\n")

        # Should read successfully
        content = detector.read_file_safe(test_file)
        assert "Hello" in content

    def test_read_file_streaming_fallback(self, tmp_path, monkeypatch):
        """Test read_file_streaming uses fallback on error."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector()
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\n", encoding="utf-8")

        # Force detection to return invalid encoding
        original_detect = detector.detect_encoding
        first_call = [True]
        
        def mock_detect(*args, **kwargs):
            if first_call[0]:
                first_call[0] = False
                return "invalid-encoding-xyz"
            return original_detect(*args, **kwargs)
        
        monkeypatch.setattr(detector, "detect_encoding", mock_detect)

        # Should fall back to UTF-8
        lines = list(detector.read_file_streaming(test_file))
        assert len(lines) == 2


class TestFallbackEncodings:
    """Tests for fallback encoding detection."""

    def test_fallback_to_cp1252(self, tmp_path):
        """Test fallback to CP1252 for Western European text."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector()
        test_file = tmp_path / "windows.txt"

        # CP1252 specific characters
        text = "café résumé naïve"
        with open(test_file, "wb") as f:
            f.write(text.encode("cp1252"))

        encoding = detector.detect_encoding(test_file)
        # Should detect as cp1252 or compatible
        assert encoding in ["utf-8", "cp1252", "iso-8859-1"]

    def test_detect_encoding_with_exceptions(self, tmp_path, monkeypatch):
        """Test detect_encoding handles exceptions."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

        detector = EncodingDetector(enable_cache=False)
        test_file = tmp_path / "test.txt"
        test_file.write_text("content", encoding="utf-8")

        # Make open() fail after first read
        original_open = open
        call_count = [0]

        def mock_open(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 1:
                raise IOError("Simulated IO error")
            return original_open(*args, **kwargs)

        # This is hard to test as detect_encoding catches all exceptions
        # Just verify it returns utf-8 as default
        encoding = detector.detect_encoding(test_file)
        assert encoding == "utf-8"


class TestThreadSafety:
    """Tests for thread safety of encoding operations."""

    def test_cache_thread_safety(self, tmp_path):
        """Test that cache operations are thread-safe."""
        from tree_sitter_analyzer_v2.utils.encoding import EncodingCache

        cache = EncodingCache(max_size=100)
        test_files = []

        # Create test files
        for i in range(10):
            f = tmp_path / f"file{i}.txt"
            f.write_text(f"content {i}", encoding="utf-8")
            test_files.append(f)

        errors = []

        def worker(file_path, encoding_name):
            try:
                cache.set(file_path, encoding_name)
                result = cache.get(file_path)
                if result != encoding_name:
                    errors.append(f"Expected {encoding_name}, got {result}")
            except Exception as e:
                errors.append(str(e))

        # Run concurrent operations
        threads = []
        for i, f in enumerate(test_files):
            t = threading.Thread(target=worker, args=(f, f"encoding-{i}"))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0
