#!/usr/bin/env python3
"""Micro property test — push hypothesis past 10%."""

from hypothesis import given, strategies as st
from tree_sitter_analyzer.encoding_utils import EncodingManager

class TestEncodingPropertyQuick:
    @given(st.text(min_size=1, max_size=200))
    def test_detect_returns_str(self, text):
        enc = EncodingManager.detect_encoding(text.encode())
        assert isinstance(enc, str)

    @given(st.binary(min_size=1, max_size=200))
    def test_decode_handles_binary(self, data):
        result = EncodingManager.safe_decode(data)
        assert isinstance(result, str)
