"""Coverage boost tests for encoding_utils — cache, BOM detection, edge cases."""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.encoding_utils import (
    EncodingCache,
    EncodingManager,
    detect_encoding,
    read_file_safe,
    write_file_safe,
)


class TestEncodingCache:
    """Tests for EncodingCache TTL and eviction."""

    def test_get_returns_none_for_missing_key(self) -> None:
        cache = EncodingCache()
        assert cache.get("nonexistent.py") is None

    def test_set_and_get(self) -> None:
        cache = EncodingCache()
        cache.set("test.py", "utf-8")
        assert cache.get("test.py") == "utf-8"

    def test_expired_entry_returns_none(self) -> None:
        cache = EncodingCache(ttl_seconds=0)
        cache.set("old.py", "utf-8")
        time.sleep(0.01)
        assert cache.get("old.py") is None

    def test_eviction_on_full_cache(self) -> None:
        cache = EncodingCache(max_size=2)
        cache.set("a.py", "utf-8")
        cache.set("b.py", "utf-8")
        cache.set("c.py", "utf-8")  # should evict oldest
        assert cache.size() <= 2

    def test_cleanup_expired(self) -> None:
        cache = EncodingCache(ttl_seconds=0)
        cache.set("expired.py", "utf-8")
        time.sleep(0.01)
        # Access triggers cleanup via set when full
        cache._cleanup_expired()
        assert cache.get("expired.py") is None

    def test_clear(self) -> None:
        cache = EncodingCache()
        cache.set("a.py", "utf-8")
        cache.clear()
        assert cache.size() == 0


class TestEncodingManagerSafeEncode:
    """Tests for safe_encode fallback paths."""

    def test_encode_none(self) -> None:
        result = EncodingManager.safe_encode(None)
        assert result == b""

    def test_encode_with_fallback(self) -> None:
        result = EncodingManager.safe_encode("hello", encoding="utf-8")
        assert result == b"hello"

    def test_encode_problematic_chars(self) -> None:
        text = "\ufffd test"
        result = EncodingManager.safe_encode(text, encoding="ascii")
        assert isinstance(result, bytes)


class TestEncodingManagerSafeDecode:
    """Tests for safe_decode fallback paths."""

    def test_decode_empty(self) -> None:
        result = EncodingManager.safe_decode(b"")
        assert result == ""

    def test_decode_with_fallback(self) -> None:
        data = "hello".encode("utf-8")
        result = EncodingManager.safe_decode(data, encoding="utf-8")
        assert result == "hello"

    def test_decode_problematic_bytes(self) -> None:
        data = b"\xff\xfe invalid"
        result = EncodingManager.safe_decode(data, encoding="ascii")
        assert isinstance(result, str)


class TestDetectEncodingBOM:
    """Tests for BOM-based encoding detection."""

    def test_utf8_bom(self) -> None:
        data = b"\xef\xbb\xbfhello"
        enc = detect_encoding(data)
        assert "utf-8" in enc

    def test_utf16_le_bom(self) -> None:
        data = b"\xff\xfe\x00\x00"
        enc = detect_encoding(data)
        assert "utf-16" in enc

    def test_utf16_be_bom(self) -> None:
        data = b"\xfe\xff\x00\x00"
        enc = detect_encoding(data)
        assert "utf-16" in enc

    def test_no_bom_returns_default(self) -> None:
        data = b"plain text"
        enc = detect_encoding(data)
        assert isinstance(enc, str)


class TestWriteFileSafe:
    """Tests for write_file_safe edge cases."""

    def test_write_success(self, tmp_path) -> None:
        f = tmp_path / "out.txt"
        result = write_file_safe(str(f), "hello world")
        assert result is True
        assert f.read_text() == "hello world"

    def test_write_to_nonexistent_directory_fails(self) -> None:
        result = write_file_safe("/nonexistent/dir/file.txt", "test")
        assert result is False


class TestReadFileSafe:
    """Tests for read_file_safe streaming and encoding."""

    def test_read_nonexistent_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            read_file_safe("/nonexistent/file.txt")

    def test_read_existing_file(self, tmp_path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        result = read_file_safe(str(f))
        assert isinstance(result, tuple)
        assert "hello world" in result[0]
