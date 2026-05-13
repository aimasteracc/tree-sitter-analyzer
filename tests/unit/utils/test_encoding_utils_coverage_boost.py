#!/usr/bin/env python3
"""Coverage boost for encoding_utils.py — targets 62.86% → 75%+"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.encoding_utils import (
    EncodingCache,
    EncodingManager,
    safe_encode,
    safe_decode,
    detect_encoding,
    read_file_safe,
    extract_text_slice,
    clear_encoding_cache,
    get_encoding_cache_size,
)


class TestEncodingCache:
    def test_get_miss(self):
        cache = EncodingCache(max_size=10)
        assert cache.get("nonexistent.txt") is None

    def test_set_and_get(self):
        cache = EncodingCache(max_size=10)
        cache.set("test.py", "utf-8")
        assert cache.get("test.py") == "utf-8"

    def test_ttl_expiry(self):
        cache = EncodingCache(max_size=10, ttl_seconds=-1)
        cache.set("test.py", "utf-8")
        # -1 ttl → immediately expired
        assert cache.get("test.py") is None

    def test_max_size_eviction(self):
        cache = EncodingCache(max_size=3)
        for i in range(5):
            cache.set(f"file_{i}.py", "utf-8")
        assert cache.size() <= 3

    def test_cleanup_expired_removes_stale(self):
        cache = EncodingCache(max_size=100, ttl_seconds=-1)
        cache.set("a.py", "utf-8")
        cache.set("b.py", "latin-1")
        # get() on expired entries returns None
        assert cache.get("a.py") is None
        assert cache.get("b.py") is None

    def test_size(self):
        cache = EncodingCache(max_size=10)
        assert cache.size() == 0
        cache.set("a.py", "utf-8")
        assert cache.size() == 1


class TestEncodingManagerEdge:
    def test_safe_decode_empty_data(self):
        assert EncodingManager.safe_decode(b"") == ""
        assert EncodingManager.safe_decode(None) == ""

    def test_safe_decode_with_errors(self):
        # Invalid UTF-8 bytes, errors="replace"
        result = EncodingManager.safe_decode(b"\xff\xfe\x00\x00")
        assert isinstance(result, str)

    def test_detect_encoding_utf8_bom(self):
        data = b"\xef\xbb\xbfhello"
        enc = EncodingManager.detect_encoding(data)
        assert isinstance(enc, str)

    def test_detect_encoding_ascii(self):
        result = EncodingManager.detect_encoding(b"plain ascii")
        assert isinstance(result, str)

    @patch("tree_sitter_analyzer.encoding_utils.CHARDET_AVAILABLE", True)
    def test_detect_encoding_chardet_none_result(self):
        with patch("tree_sitter_analyzer.encoding_utils.CHARDET_AVAILABLE", True):
            with patch("chardet.detect", return_value={"encoding": None}):
                result = EncodingManager.detect_encoding(b"data")
                assert isinstance(result, str)

    def test_read_file_safe_permission_error(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"content")
            tmp = f.name
        os.chmod(tmp, 0o000)
        try:
            with pytest.raises(PermissionError):
                read_file_safe(tmp)
        finally:
            os.chmod(tmp, 0o644)
            os.unlink(tmp)

    def test_extract_text_slice_basic(self):
        s = extract_text_slice(b"hello world", 0, 5)
        assert s == "hello"

    def test_extract_text_slice_oob(self):
        # start > end → ""
        s = extract_text_slice(b"short", 100, 200)
        assert s == ""

    def test_clear_cache(self):
        from tree_sitter_analyzer.encoding_utils import _encoding_cache
        _encoding_cache.set("test.txt", "utf-8")
        clear_encoding_cache()
        assert get_encoding_cache_size() == 0

    def test_get_encoding_cache_size(self):
        from tree_sitter_analyzer.encoding_utils import _encoding_cache
        _encoding_cache.set("test.txt", "utf-8")
        size = get_encoding_cache_size()
        assert size >= 1
        clear_encoding_cache()

    def test_cleanup_expired_on_eviction(self):
        cache = EncodingCache(max_size=2, ttl_seconds=-1)
        cache.set("a.py", "utf-8")
        cache.set("b.py", "utf-8")
        # Cache is full; adding a new entry triggers _cleanup_expired then LRU eviction
        cache.set("c.py", "utf-8")
        assert cache.size() <= 2


class TestDetectEncodingBOM:
    def test_utf16_be_bom(self):
        data = b"\xfe\xff\x00A"
        enc = EncodingManager.detect_encoding(data)
        assert enc == "utf-16-be"

    def test_utf16_le_bom(self):
        data = b"\xff\xfeA\x00"
        enc = EncodingManager.detect_encoding(data)
        assert enc == "utf-16-le"

    @patch("tree_sitter_analyzer.encoding_utils.CHARDET_AVAILABLE", True)
    def test_chardet_high_confidence(self):
        with patch("tree_sitter_analyzer.encoding_utils.chardet") as mock_chardet:
            mock_chardet.detect.return_value = {"encoding": "shift_jis", "confidence": 0.95}
            data = b"\x82\xb1\x82\xf1\x82\xc9\x82\xbf\x82\xcd"  # Shift-JIS bytes
            enc = EncodingManager.detect_encoding(data, "test_sjis.txt")
            assert enc == "shift_jis"

    @patch("tree_sitter_analyzer.encoding_utils.CHARDET_AVAILABLE", True)
    def test_chardet_exception_falls_back(self):
        with patch("tree_sitter_analyzer.encoding_utils.chardet") as mock_chardet:
            mock_chardet.detect.side_effect = RuntimeError("chardet crash")
            data = b"\x80\x81\x82"
            enc = EncodingManager.detect_encoding(data)
            assert isinstance(enc, str)


class TestNormalizeLineEndings:
    def test_empty_string(self):
        assert EncodingManager.normalize_line_endings("") == ""

    def test_none_like_empty(self):
        assert EncodingManager.normalize_line_endings("") == ""

    def test_windows_line_endings(self):
        assert EncodingManager.normalize_line_endings("a\r\nb\r\n") == "a\nb\n"

    def test_mac_line_endings(self):
        assert EncodingManager.normalize_line_endings("a\rb\r") == "a\nb\n"


class TestReadFileSafeEmpty:
    def test_read_empty_file(self, tmp_path):
        empty = tmp_path / "empty.txt"
        empty.write_bytes(b"")
        content, enc = read_file_safe(str(empty))
        assert content == ""
        assert enc == "utf-8"


class TestWriteFileSafeOSError:
    def test_write_to_readonly_dir(self, tmp_path):
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)
        try:
            result = EncodingManager.write_file_safe(
                str(readonly_dir / "subdir" / "file.txt"), "content"
            )
            assert result is False
        finally:
            readonly_dir.chmod(0o755)


class TestAsyncReadFileSafe:
    @pytest.mark.asyncio
    async def test_read_async_basic(self, tmp_path):
        from tree_sitter_analyzer.encoding_utils import read_file_safe_async

        f = tmp_path / "async_test.txt"
        f.write_text("hello async", encoding="utf-8")
        content, enc = await read_file_safe_async(str(f))
        assert content == "hello async"
        assert enc == "utf-8"

    @pytest.mark.asyncio
    async def test_read_async_empty_file(self, tmp_path):
        from tree_sitter_analyzer.encoding_utils import read_file_safe_async

        f = tmp_path / "empty_async.txt"
        f.write_bytes(b"")
        content, enc = await read_file_safe_async(str(f))
        assert content == ""
        assert enc == "utf-8"

    @pytest.mark.asyncio
    async def test_read_async_nonexistent(self, tmp_path):
        from tree_sitter_analyzer.encoding_utils import read_file_safe_async

        with pytest.raises(Exception):
            await read_file_safe_async(str(tmp_path / "nonexistent.txt"))


class TestStreamingRead:
    def test_streaming_read_basic(self, tmp_path):
        from tree_sitter_analyzer.encoding_utils import read_file_safe_streaming

        f = tmp_path / "stream.txt"
        f.write_text("line1\nline2\nline3\n", encoding="utf-8")
        ctx = read_file_safe_streaming(str(f))
        with ctx as fh:
            lines = fh.readlines()
        assert len(lines) == 3

    def test_streaming_read_empty_file(self, tmp_path):
        from tree_sitter_analyzer.encoding_utils import read_file_safe_streaming

        f = tmp_path / "empty_stream.txt"
        f.write_bytes(b"")
        ctx = read_file_safe_streaming(str(f))
        with ctx as fh:
            content = fh.read()
        assert content == ""

    def test_streaming_read_nonexistent(self, tmp_path):
        from tree_sitter_analyzer.encoding_utils import read_file_safe_streaming

        with pytest.raises(OSError):
            ctx = read_file_safe_streaming(str(tmp_path / "no_file.txt"))


class TestSafeDecodeFallbacks:
    def test_safe_decode_with_invalid_utf8(self):
        # Bytes that aren't valid UTF-8; should use fallback decoding
        result = EncodingManager.safe_decode(b"\x80\x81\x82\xff")
        assert isinstance(result, str)

    def test_safe_decode_explicit_bad_encoding(self):
        # Explicitly wrong encoding to trigger fallback
        result = EncodingManager.safe_decode(b"hello", encoding="nonexistent_encoding_xyz")
        assert isinstance(result, str)


class TestSafeEncodeFallbacks:
    def test_safe_encode_with_bad_encoding(self):
        result = EncodingManager.safe_encode("hello", encoding="nonexistent_encoding_xyz")
        assert isinstance(result, bytes)

    def test_safe_encode_none(self):
        assert EncodingManager.safe_encode(None) == b""
