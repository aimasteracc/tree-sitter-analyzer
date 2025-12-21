#!/usr/bin/env python3
"""
Test cases for encoding cache functionality
"""

import shutil
import tempfile
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.encoding_utils import (
    EncodingCache,
    clear_encoding_cache,
    detect_encoding,
    get_encoding_cache_size,
)


@pytest.fixture
def encoding_cache():
    """Fixture for EncodingCache instance"""
    cache = EncodingCache(max_size=10, ttl_seconds=1)
    clear_encoding_cache()  # Clear global cache
    yield cache
    clear_encoding_cache()


@pytest.fixture
def temp_files():
    """Fixture for temporary test files"""
    clear_encoding_cache()

    # Create temporary test files
    temp_dir = tempfile.mkdtemp()
    utf8_file = Path(temp_dir) / "test_utf8.java"
    cp1252_file = Path(temp_dir) / "test_cp1252.java"

    # Write UTF-8 content
    with open(utf8_file, "wb") as f:
        f.write("public class Test { /* 日本語 */ }".encode())

    # Write CP1252 content
    with open(cp1252_file, "wb") as f:
        f.write("public class Test { /* café */ }".encode("cp1252"))

    yield {"temp_dir": temp_dir, "utf8_file": utf8_file, "cp1252_file": cp1252_file}

    # Clean up test files
    shutil.rmtree(temp_dir, ignore_errors=True)
    clear_encoding_cache()


@pytest.fixture
def performance_test_file():
    """Fixture for performance test file"""
    clear_encoding_cache()

    # Create a test file
    temp_dir = tempfile.mkdtemp()
    test_file = Path(temp_dir) / "performance_test.java"

    # Write test content
    test_content = """
public class PerformanceTest {
    public void method1() {
        System.out.println("Test method 1");
    }

    public void method2() {
        System.out.println("Test method 2");
    }
}
""".strip()

    with open(test_file, "w", encoding="utf-8") as f:
        f.write(test_content)

    yield {"temp_dir": temp_dir, "test_file": test_file}

    # Clean up test files
    shutil.rmtree(temp_dir, ignore_errors=True)
    clear_encoding_cache()


def test_cache_basic_operations(encoding_cache):
    """Test basic cache operations"""
    # Test empty cache
    assert encoding_cache.get("test.java") is None
    assert encoding_cache.size() == 0

    # Test set and get
    encoding_cache.set("test.java", "utf-8")
    assert encoding_cache.get("test.java") == "utf-8"
    assert encoding_cache.size() == 1

    # Test overwrite
    encoding_cache.set("test.java", "cp1252")
    assert encoding_cache.get("test.java") == "cp1252"
    assert encoding_cache.size() == 1


def test_cache_expiration(encoding_cache):
    """Test cache entry expiration"""
    # Set entry with short TTL
    encoding_cache.set("test.java", "utf-8")
    assert encoding_cache.get("test.java") == "utf-8"

    # Wait for expiration
    time.sleep(1.1)

    # Entry should be expired
    assert encoding_cache.get("test.java") is None
    assert encoding_cache.size() == 0


def test_cache_size_limit(encoding_cache):
    """Test cache size limit enforcement"""
    # Fill cache to capacity
    for i in range(10):
        encoding_cache.set(f"test{i}.java", "utf-8")

    assert encoding_cache.size() == 10

    # Add one more entry (should evict oldest)
    encoding_cache.set("test10.java", "utf-8")
    assert encoding_cache.size() == 10

    # First entry should be evicted
    assert encoding_cache.get("test0.java") is None
    assert encoding_cache.get("test10.java") == "utf-8"


def test_cache_clear(encoding_cache):
    """Test cache clearing"""
    # Add some entries
    encoding_cache.set("test1.java", "utf-8")
    encoding_cache.set("test2.java", "cp1252")
    assert encoding_cache.size() == 2

    # Clear cache
    encoding_cache.clear()
    assert encoding_cache.size() == 0
    assert encoding_cache.get("test1.java") is None
    assert encoding_cache.get("test2.java") is None


def test_encoding_detection_with_caching(temp_files):
    """Test encoding detection with file path caching"""
    utf8_file = temp_files["utf8_file"]

    # First detection should cache the result
    with open(utf8_file, "rb") as f:
        data = f.read()

    encoding1 = detect_encoding(data, str(utf8_file))
    assert encoding1 == "utf-8"
    assert get_encoding_cache_size() == 1

    # Second detection should use cache
    encoding2 = detect_encoding(data, str(utf8_file))
    assert encoding2 == "utf-8"
    assert get_encoding_cache_size() == 1


def test_encoding_detection_without_caching(temp_files):
    """Test encoding detection without file path (no caching)"""
    utf8_file = temp_files["utf8_file"]

    with open(utf8_file, "rb") as f:
        data = f.read()

    # Detection without file path should not cache
    encoding1 = detect_encoding(data)
    assert encoding1 == "utf-8"
    assert get_encoding_cache_size() == 0

    encoding2 = detect_encoding(data)
    assert encoding2 == "utf-8"
    assert get_encoding_cache_size() == 0


def test_multiple_files_caching(temp_files):
    """Test caching with multiple files"""
    utf8_file = temp_files["utf8_file"]
    cp1252_file = temp_files["cp1252_file"]

    # Detect encoding for UTF-8 file
    with open(utf8_file, "rb") as f:
        utf8_data = f.read()
    encoding1 = detect_encoding(utf8_data, str(utf8_file))

    # Detect encoding for CP1252 file
    with open(cp1252_file, "rb") as f:
        cp1252_data = f.read()
    encoding2 = detect_encoding(cp1252_data, str(cp1252_file))

    # Both should be cached
    assert get_encoding_cache_size() == 2

    # Verify cached results
    cached_encoding1 = detect_encoding(utf8_data, str(utf8_file))
    cached_encoding2 = detect_encoding(cp1252_data, str(cp1252_file))

    assert cached_encoding1 == encoding1
    assert cached_encoding2 == encoding2
    assert get_encoding_cache_size() == 2


def test_repeated_detection_performance(performance_test_file):
    """Test that repeated detections use cache"""
    test_file = performance_test_file["test_file"]

    with open(test_file, "rb") as f:
        data = f.read()

    # First detection should populate cache
    encoding1 = detect_encoding(data, str(test_file))
    assert get_encoding_cache_size() == 1

    # Second detection should use cache
    encoding2 = detect_encoding(data, str(test_file))

    # Results should be the same
    assert encoding1 == encoding2

    # Cache should still contain one entry
    assert get_encoding_cache_size() == 1

    # Test multiple repeated detections to verify cache usage
    for _ in range(5):
        encoding_repeated = detect_encoding(data, str(test_file))
        assert encoding_repeated == encoding1

    # Cache size should remain the same
    assert get_encoding_cache_size() == 1
