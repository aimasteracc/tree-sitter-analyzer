#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Encoding Utilities Module

This module tests unified encoding/decoding functionality.
"""

import os
import tempfile
import pytest
import pytest_asyncio
from pathlib import Path

# Import the module under test
from tree_sitter_analyzer.encoding_utils import (
    EncodingManager,
    detect_encoding,
    extract_text_slice,
    read_file_safe,
    safe_decode,
    safe_encode,
    write_file_safe,
)


class TestEncodingManager:
    """Test cases for EncodingManager class"""

    def test_safe_encode_basic(self):
        """Test basic encoding functionality"""
        text = "Hello, World!"
        result = EncodingManager.safe_encode(text)
        assert isinstance(result, bytes)
        assert result == b"Hello, World!"

    def test_safe_encode_unicode(self):
        """Test encoding with unicode characters"""
        text = "Hello, 世界! 🌍"
        result = EncodingManager.safe_encode(text)
        assert isinstance(result, bytes)
        # Should handle unicode gracefully
        decoded_back = result.decode("utf-8")
        assert decoded_back == text

    def test_safe_encode_none(self):
        """Test encoding with None input"""
        result = EncodingManager.safe_encode(None)
        assert result == b""

    def test_safe_encode_empty_string(self):
        """Test encoding with empty string"""
        result = EncodingManager.safe_encode("")
        assert result == b""

    def test_safe_decode_basic(self):
        """Test basic decoding functionality"""
        data = b"Hello, World!"
        result = EncodingManager.safe_decode(data)
        assert isinstance(result, str)
        assert result == "Hello, World!"

    def test_safe_decode_unicode(self):
        """Test decoding with unicode bytes"""
        text = "Hello, 世界! 🌍"
        data = text.encode("utf-8")
        result = EncodingManager.safe_decode(data)
        assert result == text

    def test_safe_decode_none(self):
        """Test decoding with None input"""
        result = EncodingManager.safe_decode(None)
        assert result == ""

    def test_safe_decode_empty_bytes(self):
        """Test decoding with empty bytes"""
        result = EncodingManager.safe_decode(b"")
        assert result == ""

    def test_detect_encoding_utf8(self):
        """Test encoding detection for UTF-8"""
        text = "Hello, 世界!"
        data = text.encode("utf-8")
        detected = EncodingManager.detect_encoding(data)
        # Should detect UTF-8 or fall back to default
        assert isinstance(detected, str)
        assert len(detected) > 0

    def test_detect_encoding_empty(self):
        """Test encoding detection with empty data"""
        detected = EncodingManager.detect_encoding(b"")
        assert detected == EncodingManager.DEFAULT_ENCODING

    def test_normalize_line_endings(self):
        """Test line ending normalization"""
        # Windows line endings
        text_windows = "line1\r\nline2\r\nline3"
        result = EncodingManager.normalize_line_endings(text_windows)
        assert result == "line1\nline2\nline3"

        # Mac line endings
        text_mac = "line1\rline2\rline3"
        result = EncodingManager.normalize_line_endings(text_mac)
        assert result == "line1\nline2\nline3"

        # Unix line endings (should remain unchanged)
        text_unix = "line1\nline2\nline3"
        result = EncodingManager.normalize_line_endings(text_unix)
        assert result == "line1\nline2\nline3"

        # Mixed line endings
        text_mixed = "line1\r\nline2\rline3\nline4"
        result = EncodingManager.normalize_line_endings(text_mixed)
        assert result == "line1\nline2\nline3\nline4"

    def test_extract_text_slice(self):
        """Test text slice extraction"""
        text = "Hello, World! 世界"
        data = text.encode("utf-8")

        # Extract "World"
        start_pos = text.find("World")
        end_pos = start_pos + len("World")
        start_byte = text[:start_pos].encode("utf-8").__len__()
        end_byte = text[:end_pos].encode("utf-8").__len__()

        result = EncodingManager.extract_text_slice(data, start_byte, end_byte)
        assert result == "World"

    def test_extract_text_slice_unicode(self):
        """Test text slice extraction with unicode"""
        text = "こんにちは世界"
        data = text.encode("utf-8")

        # Extract "世界"
        start_pos = text.find("世界")
        end_pos = start_pos + len("世界")
        start_byte = text[:start_pos].encode("utf-8").__len__()
        end_byte = text[:end_pos].encode("utf-8").__len__()

        result = EncodingManager.extract_text_slice(data, start_byte, end_byte)
        assert result == "世界"

    def test_extract_text_slice_invalid_bounds(self):
        """Test text slice extraction with invalid bounds"""
        data = b"Hello, World!"

        # Start beyond end
        result = EncodingManager.extract_text_slice(data, 100, 200)
        assert result == ""

        # Start equals end
        result = EncodingManager.extract_text_slice(data, 5, 5)
        assert result == ""

        # Negative start
        result = EncodingManager.extract_text_slice(data, -5, 5)
        assert result == b"Hello"[0:5].decode("utf-8")


class TestFileOperations:
    """Test file reading/writing operations"""

    def test_read_file_safe_basic(self):
        """Test safe file reading"""
        content = "Hello, World!\nLine 2\nLine 3"

        with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
            f.write(content)
            temp_path = f.name

        try:
            result_content, detected_encoding = EncodingManager.read_file_safe(
                temp_path
            )
            assert result_content == content
            assert isinstance(detected_encoding, str)

        finally:
            try:
                os.unlink(temp_path)
            except (OSError, PermissionError):
                pass  # Ignore cleanup errors on Windows

    def test_read_file_safe_unicode(self):
        """Test safe file reading with unicode content"""
        content = "Hello, 世界!\n你好世界\n🌍🚀"

        with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
            f.write(content)
            temp_path = f.name

        try:
            result_content, detected_encoding = EncodingManager.read_file_safe(
                temp_path
            )
            assert result_content == content

        finally:
            try:
                os.unlink(temp_path)
            except (OSError, PermissionError):
                pass  # Ignore cleanup errors on Windows

    def test_read_file_safe_nonexistent(self):
        """Test safe file reading with nonexistent file"""
        with pytest.raises(FileNotFoundError):
            EncodingManager.read_file_safe("/nonexistent/file.txt")

    def test_write_file_safe_basic(self):
        """Test safe file writing"""
        content = "Hello, World!\nTest content"

        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            success = EncodingManager.write_file_safe(temp_path, content)
            assert success is True

            # Verify content was written correctly
            result_content, _ = EncodingManager.read_file_safe(temp_path)
            assert result_content == content

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_write_file_safe_unicode(self):
        """Test safe file writing with unicode"""
        content = "Hello, 世界!\n你好世界\n🌍🚀"

        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            success = EncodingManager.write_file_safe(temp_path, content)
            assert success is True

            # Verify content was written correctly
            result_content, _ = EncodingManager.read_file_safe(temp_path)
            assert result_content == content

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_read_write_roundtrip(self):
        """Test read-write roundtrip consistency"""
        original_content = """
package com.example;

import java.util.List;

/**
 * Test class with unicode: 世界 🌍
 */
public class TestClass {
    private String name = "Hello, 世界!";
    
    public void method() {
        System.out.println("Testing unicode: 你好");
    }
}
"""

        with tempfile.NamedTemporaryFile(delete=False, suffix=".java") as f:
            temp_path = f.name

        try:
            # Write content
            success = EncodingManager.write_file_safe(temp_path, original_content)
            assert success is True

            # Read content back
            read_content, detected_encoding = EncodingManager.read_file_safe(temp_path)

            # Should be identical
            assert read_content == original_content

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestConvenienceFunctions:
    """Test module-level convenience functions"""

    def test_safe_encode_function(self):
        """Test safe_encode convenience function"""
        text = "Hello, World!"
        result = safe_encode(text)
        assert result == b"Hello, World!"

    def test_safe_decode_function(self):
        """Test safe_decode convenience function"""
        data = b"Hello, World!"
        result = safe_decode(data)
        assert result == "Hello, World!"

    def test_detect_encoding_function(self):
        """Test detect_encoding convenience function"""
        data = "Hello, World!".encode("utf-8")
        result = detect_encoding(data)
        assert isinstance(result, str)

    def test_read_file_safe_function(self):
        """Test read_file_safe convenience function"""
        content = "Test content"

        with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
            f.write(content)
            temp_path = f.name

        try:
            result_content, detected_encoding = read_file_safe(temp_path)
            assert result_content == content

        finally:
            try:
                os.unlink(temp_path)
            except (OSError, PermissionError):
                pass  # Ignore cleanup errors on Windows

    def test_write_file_safe_function(self):
        """Test write_file_safe convenience function"""
        content = "Test content"

        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            success = write_file_safe(temp_path, content)
            assert success is True

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_extract_text_slice_function(self):
        """Test extract_text_slice convenience function"""
        text = "Hello, World!"
        data = text.encode("utf-8")
        result = extract_text_slice(data, 7, 12)  # "World"
        assert result == "World"


class TestErrorHandling:
    """Test error handling and edge cases"""

    @pytest.mark.parametrize("test_string", [
        "\x00\x01\x02",  # Control characters
        "�",  # Replacement character
        "\uffff",  # Non-character
    ])
    def test_encoding_with_invalid_characters(self, test_string):
        """Test encoding with potentially problematic characters"""
        # Should not raise exceptions
        encoded = safe_encode(test_string)
        assert isinstance(encoded, bytes)

        decoded = safe_decode(encoded)
        assert isinstance(decoded, str)

    def test_large_content_handling(self):
        """Test handling of large content"""
        # Create large content (1MB)
        large_content = "A" * (1024 * 1024)

        encoded = safe_encode(large_content)
        assert isinstance(encoded, bytes)
        assert len(encoded) == 1024 * 1024

        decoded = safe_decode(encoded)
        assert decoded == large_content

    def test_mixed_encoding_content(self):
        """Test content that might have mixed encoding issues"""
        # This simulates content that might have encoding issues
        problematic_bytes = (
            b"\xff\xfe\x00H\x00e\x00l\x00l\x00o"  # UTF-16 LE BOM + "Hello"
        )

        # Should handle gracefully
        result = safe_decode(problematic_bytes)
        assert isinstance(result, str)
        # Should not crash, exact result may vary based on detection


if __name__ == "__main__":
    pytest.main([__file__])
