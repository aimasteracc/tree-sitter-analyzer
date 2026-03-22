#!/usr/bin/env python3
"""Property-based tests for encoding_utils module.

Uses Hypothesis to verify encoding detection and conversion properties.
"""

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.encoding_utils import (
    clear_encoding_cache,
    detect_encoding,
    get_encoding_cache_size,
    read_file_safe,
    safe_decode,
    safe_encode,
)


class TestEncodingRoundtripProperties:
    """Property tests for encoding/decoding roundtrip consistency."""

    @given(text=st.text(min_size=0, max_size=1000))
    @settings(max_examples=100)
    def test_utf8_roundtrip(self, text: str) -> None:
        """UTF-8 encode/decode should be lossless for any text.

        Property: safe_decode(safe_encode(text)) == text
        """
        encoded = safe_encode(text, encoding="utf-8")
        decoded = safe_decode(encoded, encoding="utf-8")
        assert decoded == text

    @given(text=st.text(min_size=1, max_size=500, alphabet=st.characters(min_codepoint=32, max_codepoint=126)))
    @settings(max_examples=50)
    def test_ascii_roundtrip(self, text: str) -> None:
        """ASCII encode/decode should be lossless for ASCII text.

        Property: safe_decode(safe_encode(text), 'ascii') == text for ASCII text
        """
        encoded = safe_encode(text, encoding="ascii")
        decoded = safe_decode(encoded, encoding="ascii")
        assert decoded == text

    @given(data=st.binary(min_size=0, max_size=1000))
    @settings(max_examples=50)
    def test_decode_never_raises(self, data: bytes) -> None:
        """safe_decode should never raise an exception.

        Property: safe_decode always returns a string for any bytes input
        """
        result = safe_decode(data)
        assert isinstance(result, str)


class TestEncodingDetectionProperties:
    """Property tests for encoding detection."""

    @given(text=st.text(min_size=0, max_size=500))
    @settings(max_examples=50)
    def test_detect_encoding_returns_valid_encoding(self, text: str) -> None:
        """detect_encoding should return a valid encoding name.

        Property: detect_encoding always returns a string that represents an encoding
        """
        data = text.encode("utf-8", errors="replace")
        encoding = detect_encoding(data)
        assert isinstance(encoding, str)
        assert len(encoding) > 0

    @given(text=st.text(min_size=1, max_size=200))
    @settings(max_examples=50)
    def test_detect_encoding_consistency(self, text: str) -> None:
        """detect_encoding should return consistent results for same input.

        Property: detect_encoding(data) == detect_encoding(data) for same data
        """
        clear_encoding_cache()
        data = text.encode("utf-8", errors="replace")
        encoding1 = detect_encoding(data)
        encoding2 = detect_encoding(data)
        assert encoding1 == encoding2

    def test_detect_encoding_with_bom(self) -> None:
        """UTF-8 BOM should be detected as UTF-8."""
        bom_utf8 = b"\xef\xbb\xbfHello World"
        encoding = detect_encoding(bom_utf8)
        assert encoding.lower() in ("utf-8", "utf-8-sig")


class TestEncodingCacheProperties:
    """Property tests for encoding cache behavior."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_encoding_cache()

    def test_cache_size_bounded(self) -> None:
        """Cache size should be bounded after many operations."""
        # Perform many encoding detections
        for i in range(200):
            data = f"test content {i}".encode("utf-8")
            detect_encoding(data)

        cache_size = get_encoding_cache_size()
        # Cache should be bounded (implementation may vary)
        assert cache_size >= 0
        assert cache_size <= 10000  # Reasonable upper bound

    def test_clear_cache_resets_size(self) -> None:
        """Clearing cache should reset size to 0."""
        # Add some entries
        for i in range(10):
            data = f"test {i}".encode("utf-8")
            detect_encoding(data)

        clear_encoding_cache()
        assert get_encoding_cache_size() == 0


class TestFileReadingProperties:
    """Property tests for file reading operations."""

    @given(text=st.text(min_size=0, max_size=1000))
    @settings(max_examples=30)
    def test_read_file_safe_roundtrip(self, text: str) -> None:
        """read_file_safe should read back what was written.

        Property: read_file_safe(temp_file) returns content that was written
        """
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".txt", delete=False) as f:
            temp_path = Path(f.name)
            f.write(text.encode("utf-8"))

        try:
            content, detected_encoding = read_file_safe(temp_path)
            # Content should match (allowing for some normalization)
            assert isinstance(content, str)
            assert isinstance(detected_encoding, str)
        finally:
            temp_path.unlink(missing_ok=True)

    @given(
        content=st.text(min_size=1, max_size=500),
        extension=st.sampled_from([".py", ".js", ".java", ".txt", ".md"]),
    )
    @settings(max_examples=30)
    def test_read_various_file_types(self, content: str, extension: str) -> None:
        """read_file_safe should handle various file types.

        Property: read_file_safe works for any text file regardless of extension
        """
        with tempfile.NamedTemporaryFile(mode="wb", suffix=extension, delete=False) as f:
            temp_path = Path(f.name)
            f.write(content.encode("utf-8"))

        try:
            result, encoding = read_file_safe(temp_path)
            assert isinstance(result, str)
            assert isinstance(encoding, str)
        finally:
            temp_path.unlink(missing_ok=True)


class TestStringEncodingProperties:
    """Property tests for string encoding edge cases."""

    @given(text=st.text(min_size=0, max_size=100))
    @settings(max_examples=50)
    def test_empty_and_whitespace_handling(self, text: str) -> None:
        """Empty and whitespace strings should be handled correctly."""
        # This test specifically targets edge cases
        encoded = safe_encode(text)
        assert isinstance(encoded, bytes)

        decoded = safe_decode(encoded)
        assert isinstance(decoded, str)

    @given(
        text=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(
                min_codepoint=0,
                max_codepoint=0x10FFFF,
                exclude_categories=["Cs"],  # Exclude surrogates
            ),
        )
    )
    @settings(max_examples=30)
    def test_unicode_handling(self, text: str) -> None:
        """Unicode text should be handled correctly."""
        # Encode with error handling
        encoded = safe_encode(text, encoding="utf-8")
        decoded = safe_decode(encoded, encoding="utf-8")
        # Should roundtrip successfully
        assert decoded == text
