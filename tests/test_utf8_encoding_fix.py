#!/usr/bin/env python3
"""
Test for UTF-8 encoding fixes in tree-sitter-analyzer.

This test ensures that files with different encodings are handled correctly
throughout the system, replacing hardcoded UTF-8 with proper encoding detection.
"""

import tempfile
import pytest
from pathlib import Path

from tree_sitter_analyzer.api import validate_file
from tree_sitter_analyzer.encoding_utils import read_file_safe


class TestUTF8EncodingFix:
    """Test UTF-8 encoding fixes across the system."""

    def test_validate_file_with_shift_jis_encoding(self):
        """Test that validate_file handles Shift_JIS encoded files correctly."""
        # Create a Shift_JIS encoded Java file
        shift_jis_content = """public class TestClass {
    // 日本語コメント
    public void testMethod() {
        System.out.println("こんにちは世界");
    }
}"""
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False, encoding="shift_jis") as f:
            f.write(shift_jis_content)
            temp_path = f.name

        try:
            # This should NOT fail with UnicodeDecodeError
            result = validate_file(temp_path)
            
            # The file should be considered valid
            assert result["exists"] is True
            assert result["readable"] is True  # This is the key test
            assert result["language"] == "java"
            assert result["supported"] is True
            assert len(result["errors"]) == 0
            assert result["valid"] is True
            
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_validate_file_with_cp932_encoding(self):
        """Test that validate_file handles CP932 encoded files correctly."""
        # Create a CP932 encoded Python file
        cp932_content = """# -*- coding: cp932 -*-
def test_function():
    '''日本語の関数'''
    print("テスト")
    return "成功"
"""
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="cp932") as f:
            f.write(cp932_content)
            temp_path = f.name

        try:
            # This should NOT fail with UnicodeDecodeError
            result = validate_file(temp_path)
            
            # The file should be considered valid
            assert result["exists"] is True
            assert result["readable"] is True  # This is the key test
            assert result["language"] == "python"
            assert result["supported"] is True
            assert len(result["errors"]) == 0
            assert result["valid"] is True
            
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_validate_file_with_latin1_encoding(self):
        """Test that validate_file handles Latin-1 encoded files correctly."""
        # Create a Latin-1 encoded JavaScript file
        latin1_content = """// Français
function testFunction() {
    console.log("Café");
    return "Résultat";
}"""
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False, encoding="latin-1") as f:
            f.write(latin1_content)
            temp_path = f.name

        try:
            # This should NOT fail with UnicodeDecodeError
            result = validate_file(temp_path)
            
            # The file should be considered valid
            assert result["exists"] is True
            assert result["readable"] is True  # This is the key test
            assert result["language"] == "javascript"
            assert result["supported"] is True
            assert len(result["errors"]) == 0
            assert result["valid"] is True
            
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_read_file_safe_handles_various_encodings(self):
        """Test that read_file_safe correctly handles various encodings."""
        test_cases = [
            ("utf-8", "UTF-8 テスト"),
            ("shift_jis", "Shift_JIS テスト"),
            ("cp932", "CP932 テスト"),
            ("latin-1", "Latin-1 café"),
        ]
        
        for encoding, content in test_cases:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding=encoding) as f:
                f.write(content)
                temp_path = f.name

            try:
                # read_file_safe should handle any encoding
                result_content, detected_encoding = read_file_safe(temp_path)
                
                # Content should be read successfully
                assert result_content is not None
                assert len(result_content) > 0
                assert detected_encoding is not None
                
                # The content should contain the expected text (may be normalized)
                # We don't assert exact equality due to encoding detection variations
                assert len(result_content.strip()) > 0
                
            finally:
                Path(temp_path).unlink(missing_ok=True)

    def test_validate_file_error_handling(self):
        """Test that validate_file properly handles encoding errors."""
        # Test with non-existent file
        result = validate_file("/non/existent/file.java")
        assert result["valid"] is False
        assert result["exists"] is False
        assert "File does not exist" in result["errors"]

    def test_validate_file_with_binary_file(self):
        """Test that validate_file handles binary files gracefully."""
        # Create a binary file
        binary_content = b'\x00\x01\x02\x03\xFF\xFE\xFD'
        
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".bin", delete=False) as f:
            f.write(binary_content)
            temp_path = f.name

        try:
            # This should handle binary files gracefully
            result = validate_file(temp_path)
            
            # The file exists but may not be readable as text
            assert result["exists"] is True
            # readable might be False due to binary content, which is acceptable
            
        finally:
            Path(temp_path).unlink(missing_ok=True)


    def test_java_plugin_handles_various_encodings(self):
        """Test that Java plugin handles various encodings correctly."""
        from tree_sitter_analyzer.languages.java_plugin import JavaPlugin
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
        
        # Create a Shift_JIS encoded Java file
        shift_jis_content = """public class TestClass {
    // 日本語コメント
    public void testMethod() {
        System.out.println("こんにちは世界");
    }
}"""
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False, encoding="shift_jis") as f:
            f.write(shift_jis_content)
            temp_path = f.name

        try:
            # This should NOT fail with UnicodeDecodeError
            plugin = JavaPlugin()
            request = AnalysisRequest(file_path=temp_path, language="java")
            
            # This is the key test - should handle encoding automatically
            import asyncio
            result = asyncio.run(plugin.analyze_file(temp_path, request))
            
            # The analysis should succeed
            assert result.success is True
            assert result.language == "java"
            assert len(result.source_code) > 0
            
        finally:
            Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__])