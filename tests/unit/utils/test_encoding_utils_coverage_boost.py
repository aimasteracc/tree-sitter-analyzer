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
