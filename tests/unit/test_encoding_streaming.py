"""Unit tests for _encoding_streaming — streaming file reads with encoding detection."""

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.encoding.streaming import (
    detect_streaming_encoding,
    open_streaming_context,
    read_encoding_sample,
    read_file_safe_streaming_context,
)


class TestReadEncodingSample:
    """Tests for read_encoding_sample."""

    def test_reads_first_8192_bytes(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"x" * 10000)
        sample = read_encoding_sample(f)
        assert len(sample) == 8192

    def test_small_file_returns_all(self, tmp_path):
        f = tmp_path / "small.txt"
        f.write_bytes(b"hello")
        sample = read_encoding_sample(f)
        assert sample == b"hello"

    def test_empty_file_returns_empty(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        sample = read_encoding_sample(f)
        assert sample == b""

    def test_nonexistent_file_raises(self, tmp_path):
        f = tmp_path / "nope.txt"
        with pytest.raises(FileNotFoundError):
            read_encoding_sample(f)


class TestDetectStreamingEncoding:
    """Tests for detect_streaming_encoding."""

    def test_empty_file_returns_default(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        detect_fn = MagicMock(return_value="utf-8")
        log_fn = MagicMock()
        encoding = detect_streaming_encoding(
            f, default_encoding="ascii", detect_encoding=detect_fn, log_warning=log_fn
        )
        assert encoding == "ascii"
        detect_fn.assert_not_called()

    def test_detects_encoding_from_sample(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello world")
        detect_fn = MagicMock(return_value="utf-8")
        log_fn = MagicMock()
        encoding = detect_streaming_encoding(
            f, default_encoding="ascii", detect_encoding=detect_fn, log_warning=log_fn
        )
        assert encoding == "utf-8"
        detect_fn.assert_called_once()

    def test_oserror_logs_and_reraises(self, tmp_path):
        f = tmp_path / "nope.txt"
        detect_fn = MagicMock()
        log_fn = MagicMock()
        with pytest.raises(OSError):
            detect_streaming_encoding(
                f,
                default_encoding="utf-8",
                detect_encoding=detect_fn,
                log_warning=log_fn,
            )
        log_fn.assert_called_once()
        assert "Failed to read" in log_fn.call_args[0][0]


class TestOpenStreamingContext:
    """Tests for open_streaming_context."""

    def test_reads_file_with_encoding(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        log_fn = MagicMock()
        with open_streaming_context(f, "utf-8", log_fn) as handle:
            content = handle.read()
        assert content == "hello world"

    def test_invalid_encoding_reraises(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        log_fn = MagicMock()
        with pytest.raises(LookupError):
            with open_streaming_context(f, "invalid-encoding-xyz", log_fn):
                pass
        log_fn.assert_called_once()

    def test_errors_replace_mode(self, tmp_path):
        f = tmp_path / "binary.bin"
        f.write_bytes(b"\xff\xfe invalid utf-8 \x80\x81")
        log_fn = MagicMock()
        with open_streaming_context(f, "utf-8", log_fn) as handle:
            content = handle.read()
        # Should not raise; replaced characters instead
        assert isinstance(content, str)


class TestReadFileSafeStreamingContext:
    """Tests for read_file_safe_streaming_context."""

    def test_end_to_end_streaming(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("line 1\nline 2\n", encoding="utf-8")
        detect_fn = MagicMock(return_value="utf-8")
        log_fn = MagicMock()
        ctx = read_file_safe_streaming_context(
            f, default_encoding="ascii", detect_encoding=detect_fn, log_warning=log_fn
        )
        with ctx as handle:
            lines = handle.readlines()
        assert len(lines) == 2

    def test_string_path_accepted(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("content")
        detect_fn = MagicMock(return_value="utf-8")
        log_fn = MagicMock()
        ctx = read_file_safe_streaming_context(
            str(f),
            default_encoding="utf-8",
            detect_encoding=detect_fn,
            log_warning=log_fn,
        )
        with ctx as handle:
            assert handle.read() == "content"
