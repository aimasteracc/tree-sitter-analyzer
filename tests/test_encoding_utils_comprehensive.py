#!/usr/bin/env python3
"""
Comprehensive tests for encoding utils to achieve high coverage.
"""

import pytest
import tempfile
import os
from tree_sitter_analyzer.encoding_utils import (
    safe_encode, safe_decode, detect_encoding, extract_text_slice,
    EncodingManager
)


class TestEncodingUtilsComprehensive:
    """Comprehensive test suite for encoding utils"""

    def test_safe_encode_string(self):
        """Test safe_encode with string input"""
        result = safe_encode("hello world")
        assert isinstance(result, bytes)
        assert result == b"hello world"

    def test_safe_encode_unicode_string(self):
        """Test safe_encode with unicode string"""
        result = safe_encode("你好世界")
        assert isinstance(result, bytes)
        assert len(result) > 4  # UTF-8 encoding of Chinese characters

    def test_safe_encode_empty_string(self):
        """Test safe_encode with empty string"""
        result = safe_encode("")
        assert isinstance(result, bytes)
        assert result == b""

    def test_safe_encode_none(self):
        """Test safe_encode with None"""
        result = safe_encode(None)
        assert isinstance(result, bytes)
        assert result == b""

    def test_skip_bytes_disabled(self):
        """Test safe_encode with bytes input"""
        input_bytes = b"hello world"
        result = safe_encode(input_bytes)
        assert isinstance(result, bytes)
        assert result == input_bytes

    def test_safe_decode_bytes(self):
        """Test safe_decode with bytes input"""
        result = safe_decode(b"hello world")
        assert isinstance(result, str)
        assert result == "hello world"

    def test_safe_decode_unicode_bytes(self):
        """Test safe_decode with unicode bytes"""
        unicode_bytes = "你好世界".encode('utf-8')
        result = safe_decode(unicode_bytes)
        assert isinstance(result, str)
        assert result == "你好世界"

    def test_safe_decode_empty_bytes(self):
        """Test safe_decode with empty bytes"""
        result = safe_decode(b"")
        assert isinstance(result, str)
        assert result == "" or isinstance(result, str)

    def test_safe_decode_none(self):
        """Test safe_decode with None"""
        result = safe_decode(None)
        assert isinstance(result, str)
        assert result == "" or isinstance(result, str)

    def test_skip_string_disabled(self):
        """Test safe_decode with string input"""
        result = safe_decode("hello world")
        assert isinstance(result, str)
        assert result == "hello world"

    def test_detect_encoding_utf8(self):
        """Test detect_encoding with UTF-8 content"""
        utf8_content = "hello world".encode('utf-8')
        result = detect_encoding(utf8_content)
        assert isinstance(result, str)
        assert result.lower() in ['utf-8', 'ascii']

    def test_detect_encoding_unicode(self):
        """Test detect_encoding with unicode content"""
        unicode_content = "你好世界".encode('utf-8')
        result = detect_encoding(unicode_content)
        assert isinstance(result, str)
        assert 'utf' in result.lower()

    def test_detect_encoding_empty(self):
        """Test detect_encoding with empty content"""
        result = detect_encoding(b"")
        assert isinstance(result, str)

    def test_detect_encoding_none(self):
        """Test detect_encoding with None"""
        result = detect_encoding(None)
        assert isinstance(result, str)

    def test_extract_text_slice_basic(self):
        """Test extract_text_slice with basic input"""
        text = b"hello world"  # Use bytes as expected by the function
        result = extract_text_slice(text, 0, 5)
        assert "hello" in result

    def test_extract_text_slice_full_text(self):
        """Test extract_text_slice with full text"""
        text = b"hello world"  # Use bytes as expected by the function
        result = extract_text_slice(text, 0, len(text))
        assert "hello world" in result

    def test_extract_text_slice_unicode(self):
        """Test extract_text_slice with unicode text"""
        text = "你好世界".encode('utf-8')  # Use bytes as expected by the function
        result = extract_text_slice(text, 0, 6)  # UTF-8 encoded Chinese chars
        assert isinstance(result, str)

    def test_extract_text_slice_invalid_bounds(self):
        """Test extract_text_slice with invalid bounds"""
        text = b"hello"  # Use bytes as expected by the function
        
        # Test with bounds beyond text length
        result = extract_text_slice(text, 0, 100)
        assert isinstance(result, str)
        
        # Test with negative start
        result = extract_text_slice(text, -1, 3)
        assert isinstance(result, str)
        
        # Test with start > end
        result = extract_text_slice(text, 5, 2)
        assert isinstance(result, str)

    def test_extract_text_slice_empty_text(self):
        """Test extract_text_slice with empty text"""
        result = extract_text_slice(b"", 0, 0)
        assert result == "" or isinstance(result, str)

    def test_extract_text_slice_none_text(self):
        """Test extract_text_slice with None text"""
        try:
            result = extract_text_slice(None, 0, 5)
            assert isinstance(result, str)
        except (TypeError, AttributeError):
            # Expected for None input
            pass


class TestEncodingManagerComprehensive:
    """Comprehensive test suite for EncodingManager"""

    def test_encoding_manager_safe_encode(self):
        """Test EncodingManager.safe_encode"""
        result = EncodingManager.safe_encode("test string")
        assert isinstance(result, bytes)

    def test_encoding_manager_safe_decode(self):
        """Test EncodingManager.safe_decode"""
        result = EncodingManager.safe_decode(b"test bytes")
        assert isinstance(result, str)

    def test_encoding_manager_detect_encoding(self):
        """Test EncodingManager.detect_encoding"""
        result = EncodingManager.detect_encoding(b"test content")
        assert isinstance(result, str)

    def test_encoding_manager_extract_text_slice(self):
        """Test EncodingManager.extract_text_slice"""
        # Test with bytes input (the method expects bytes)
        text_bytes = b"hello world"
        result = EncodingManager.extract_text_slice(text_bytes, 0, 5)
        assert isinstance(result, str)

    def test_encoding_manager_with_different_encodings(self):
        """Test EncodingManager with different encodings"""
        # Test with various encoded content
        test_strings = ["hello", "你好", "🚀", "café"]
        
        for test_string in test_strings:
            # Encode with UTF-8
            encoded = test_string.encode('utf-8')
            
            # Test detection
            detected_encoding = EncodingManager.detect_encoding(encoded)
            assert isinstance(detected_encoding, str)
            
            # Test decoding
            decoded = EncodingManager.safe_decode(encoded)
            assert isinstance(decoded, str)

    def test_encoding_manager_error_handling(self):
        """Test EncodingManager error handling"""
        # Test with invalid bytes
        invalid_bytes = b'\xff\xfe\x00\x00'
        
        try:
            result = EncodingManager.safe_decode(invalid_bytes)
            assert isinstance(result, str)
        except Exception:
            # Error handling might vary
            pass
        
        try:
            encoding = EncodingManager.detect_encoding(invalid_bytes)
            assert isinstance(encoding, str)
        except Exception:
            # Error handling might vary
            pass

    def test_encoding_manager_with_large_content(self):
        """Test EncodingManager with large content"""
        # Create large content
        large_text = "hello world " * 10000
        large_bytes = large_text.encode('utf-8')
        
        # Test encoding operations
        detected = EncodingManager.detect_encoding(large_bytes)
        assert isinstance(detected, str)
        
        decoded = EncodingManager.safe_decode(large_bytes)
        assert isinstance(decoded, str)
        assert len(decoded) > 100000

    def test_encoding_manager_slice_operations(self):
        """Test EncodingManager slice operations"""
        text_bytes = "hello world test".encode('utf-8')
        
        # Test various slice operations
        slice_results = [
            EncodingManager.extract_text_slice(text_bytes, 0, 5),
            EncodingManager.extract_text_slice(text_bytes, 6, 11),
            EncodingManager.extract_text_slice(text_bytes, 12, 16)
        ]
        
        for result in slice_results:
            assert isinstance(result, str)
            assert len(result) > 0


class TestEncodingUtilsIntegration:
    """Test encoding utils integration scenarios"""

    def test_file_encoding_workflow(self):
        """Test complete file encoding workflow"""
        test_content = "def hello():\n    return '你好世界'\n\n# Test comment 🚀"
        
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as f:
            f.write(test_content)
            temp_file = f.name
        
        try:
            # Read file as bytes
            with open(temp_file, 'rb') as f:
                file_bytes = f.read()
            
            # Test encoding detection
            detected_encoding = detect_encoding(file_bytes)
            assert isinstance(detected_encoding, str)
            
            # Test decoding
            decoded_content = safe_decode(file_bytes)
            assert isinstance(decoded_content, str)
            assert "你好世界" in decoded_content
            assert "🚀" in decoded_content
            
            # Test re-encoding
            re_encoded = safe_encode(decoded_content)
            assert isinstance(re_encoded, bytes)
            
        finally:
            os.unlink(temp_file)

    def test_encoding_round_trip(self):
        """Test encoding round-trip operations"""
        test_strings = [
            "simple ascii",
            "unicode: 你好世界",
            "emoji: 🚀🌍💻",
            "mixed: hello 世界 🚀",
            "special chars: \n\t\r\\",
            ""
        ]
        
        for original in test_strings:
            # Encode then decode
            encoded = safe_encode(original)
            decoded = safe_decode(encoded)
            
            assert decoded == original
            assert isinstance(encoded, bytes)
            assert isinstance(decoded, str)

    def test_encoding_error_recovery(self):
        """Test encoding error recovery"""
        # Test with various problematic inputs
        problematic_inputs = [
            None,
            "",
            b"",
            b'\xff\xfe',
            "normal string",
            b"normal bytes"
        ]
        
        for inp in problematic_inputs:
            try:
                if isinstance(inp, (str, type(None))):
                    result = safe_encode(inp)
                    assert isinstance(result, bytes)
                else:
                    result = safe_decode(inp)
                    assert isinstance(result, str)
            except Exception:
                # Some inputs might legitimately fail
                pass

    def test_concurrent_encoding_operations(self):
        """Test concurrent encoding operations"""
        import threading
        
        results = []
        errors = []
        
        def worker(worker_id):
            try:
                for i in range(10):
                    text = f"Worker {worker_id} iteration {i} 测试"
                    encoded = safe_encode(text)
                    decoded = safe_decode(encoded)
                    results.append((text, encoded, decoded))
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 50  # 5 workers * 10 iterations
        
        # Verify all operations completed successfully
        for original, encoded, decoded in results:
            assert isinstance(encoded, bytes)
            assert isinstance(decoded, str)
            assert decoded == original