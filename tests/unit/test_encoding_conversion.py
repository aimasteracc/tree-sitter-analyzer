"""Tests for _encoding_conversion — encoding/decoding fallback paths."""

from tree_sitter_analyzer.encoding.conversion import (
    decode_with_fallbacks,
    encode_with_fallbacks,
    safe_decode_bytes,
    safe_encode_text,
)


class TestSafeEncodeText:
    def test_none_input_returns_empty_bytes(self):
        result = safe_encode_text(
            None,
            target_encoding="utf-8",
            default_encoding="utf-8",
            fallback_encodings=["latin-1"],
            log_debug=lambda _: None,
            log_warning=lambda _: None,
        )
        assert result == b""

    def test_utf8_encoding_succeeds(self):
        result = safe_encode_text(
            "hello",
            target_encoding="utf-8",
            default_encoding="utf-8",
            fallback_encodings=["latin-1"],
            log_debug=lambda _: None,
            log_warning=lambda _: None,
        )
        assert result == b"hello"

    def test_target_fails_uses_fallback(self):
        debug_msgs = []
        result = safe_encode_text(
            "☃",  # snowman — not encodable in latin-1
            target_encoding="latin-1",
            default_encoding="utf-8",
            fallback_encodings=["utf-8"],
            log_debug=debug_msgs.append,
            log_warning=lambda _: None,
        )
        assert result == "☃".encode()
        assert len(debug_msgs) == 1

    def test_all_encodings_fail_uses_replace(self):
        warning_msgs = []
        result = safe_encode_text(
            "☃",
            target_encoding="latin-1",
            default_encoding="ascii",
            fallback_encodings=["latin-1"],
            log_debug=lambda _: None,
            log_warning=warning_msgs.append,
        )
        assert b"?" in result
        assert len(warning_msgs) == 1


class TestEncodeWithFallbacks:
    def test_skips_target_encoding(self):
        result = encode_with_fallbacks("hello", "ascii", ["ascii", "utf-8"])
        assert result == b"hello"

    def test_returns_none_when_all_fail(self):
        result = encode_with_fallbacks("☃", "latin-1", ["latin-1"])
        assert result is None

    def test_uses_first_working_fallback(self):
        result = encode_with_fallbacks("café", "ascii", ["latin-1", "utf-8"])
        assert result == "café".encode("latin-1", errors="replace")


class TestSafeDecodeBytes:
    def test_none_returns_empty(self):
        result = safe_decode_bytes(
            None,
            encoding=None,
            default_encoding="utf-8",
            fallback_encodings=["latin-1"],
            detect_encoding=lambda _: "utf-8",
            log_debug=lambda _: None,
            log_warning=lambda _: None,
        )
        assert result == ""

    def test_empty_bytes_returns_empty(self):
        result = safe_decode_bytes(
            b"",
            encoding=None,
            default_encoding="utf-8",
            fallback_encodings=["latin-1"],
            detect_encoding=lambda _: "utf-8",
            log_debug=lambda _: None,
            log_warning=lambda _: None,
        )
        assert result == ""

    def test_utf8_decode_succeeds(self):
        result = safe_decode_bytes(
            b"hello",
            encoding="utf-8",
            default_encoding="utf-8",
            fallback_encodings=["latin-1"],
            detect_encoding=lambda _: "utf-8",
            log_debug=lambda _: None,
            log_warning=lambda _: None,
        )
        assert result == "hello"

    def test_uses_detect_encoding_when_none(self):
        result = safe_decode_bytes(
            b"hello",
            encoding=None,
            default_encoding="utf-8",
            fallback_encodings=["latin-1"],
            detect_encoding=lambda _: "utf-8",
            log_debug=lambda _: None,
            log_warning=lambda _: None,
        )
        assert result == "hello"

    def test_target_fails_uses_fallback(self):
        debug_msgs = []
        result = safe_decode_bytes(
            b"\xff\xfe",
            encoding="utf-8",
            default_encoding="utf-8",
            fallback_encodings=["utf-16"],
            detect_encoding=lambda _: "utf-8",
            log_debug=debug_msgs.append,
            log_warning=lambda _: None,
        )
        assert isinstance(result, str)
        assert len(debug_msgs) == 1

    def test_all_fail_uses_replace(self):
        warning_msgs = []
        result = safe_decode_bytes(
            b"\xff\xfe\xfd",
            encoding="ascii",
            default_encoding="utf-8",
            fallback_encodings=["ascii"],
            detect_encoding=lambda _: "ascii",
            log_debug=lambda _: None,
            log_warning=warning_msgs.append,
        )
        assert isinstance(result, str)
        assert len(warning_msgs) == 1


class TestDecodeWithFallbacks:
    def test_skips_target_encoding(self):
        data = b"hello"
        result = decode_with_fallbacks(data, "utf-8", ["utf-8", "ascii"])
        assert result == "hello"

    def test_returns_none_when_all_fail(self):
        result = decode_with_fallbacks(b"\xff\xfe\xfd", "ascii", ["ascii"])
        assert result is None

    def test_uses_working_fallback(self):
        data = b"hello"
        result = decode_with_fallbacks(data, "ascii", ["utf-8"])
        assert result == "hello"
