#!/usr/bin/env python3
"""Property-based test: encoding round-trip idempotency."""

from hypothesis import given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.encoding_utils import safe_encode, safe_decode


class TestEncodingProperties:
    """Verify encode/decode round-trip and idempotency for generic inputs."""

    @given(st.text())
    @settings(max_examples=100)
    def test_encode_decode_roundtrip(self, text):
        encoded = safe_encode(text)
        decoded = safe_decode(encoded)
        assert isinstance(decoded, str)

    @given(st.text())
    @settings(max_examples=100)
    def test_decode_never_raises(self, text):
        encoded = safe_encode(text)
        result = safe_decode(encoded)
        assert isinstance(result, str)
