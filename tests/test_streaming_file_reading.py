"""
Test streaming file reading functionality

This module tests the read_file_safe_streaming function that provides
memory-efficient line-by-line file reading with automatic encoding detection.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.encoding_utils import read_file_safe_streaming


class TestStreamingFileReading:
    """Test cases for streaming file reading"""

    def test_streaming_basic_reading(self):
        """Test basic streaming file reading"""
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False, suffix=".txt"
        ) as f:
            f.write("Line 1\n")
            f.write("Line 2\n")
            f.write("Line 3\n")
            temp_file = f.name

        try:
            with read_file_safe_streaming(temp_file) as file_handle:
                lines = list(file_handle)
                assert len(lines) == 3
                assert lines[0] == "Line 1\n"
                assert lines[1] == "Line 2\n"
                assert lines[2] == "Line 3\n"
        finally:
            Path(temp_file).unlink()

    def test_streaming_line_by_line(self):
        """Test streaming with line-by-line iteration"""
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False, suffix=".txt"
        ) as f:
            for i in range(10):
                f.write(f"Line {i}\n")
            temp_file = f.name

        try:
            with read_file_safe_streaming(temp_file) as file_handle:
                line_count = 0
                for line in file_handle:
                    line_count += 1
                    assert line.startswith("Line ")
                assert line_count == 10
        finally:
            Path(temp_file).unlink()

    def test_streaming_with_start_line(self):
        """Test streaming starting from specific line"""
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False, suffix=".txt"
        ) as f:
            for i in range(10):
                f.write(f"Line {i}\n")
            temp_file = f.name

        try:
            with read_file_safe_streaming(temp_file) as file_handle:
                # Skip first 5 lines
                for i, line in enumerate(file_handle, 1):
                    if i >= 6:
                        # Process lines 6-10
                        assert line.startswith("Line ")
        finally:
            Path(temp_file).unlink()

    def test_streaming_empty_file(self):
        """Test streaming with empty file"""
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False, suffix=".txt"
        ) as f:
            temp_file = f.name

        try:
            with read_file_safe_streaming(temp_file) as file_handle:
                lines = list(file_handle)
                assert len(lines) == 0
        finally:
            Path(temp_file).unlink()

    def test_streaming_unicode_content(self):
        """Test streaming with Unicode content"""
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False, suffix=".txt"
        ) as f:
            f.write("日本語テキスト\n")
            f.write("中文文本\n")
            f.write("한국어 텍스트\n")
            temp_file = f.name

        try:
            with read_file_safe_streaming(temp_file) as file_handle:
                lines = list(file_handle)
                assert len(lines) == 3
                assert "日本語" in lines[0]
                assert "中文" in lines[1]
                assert "한국어" in lines[2]
        finally:
            Path(temp_file).unlink()

    def test_streaming_large_file_memory_efficiency(self):
        """Test that streaming doesn't load entire file into memory"""
        # Create a file with many lines
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False, suffix=".txt"
        ) as f:
            for i in range(1000):
                f.write(f"Line {i} with some content\n")
            temp_file = f.name

        try:
            # Read only first 10 lines - should be fast
            with read_file_safe_streaming(temp_file) as file_handle:
                count = 0
                for line in file_handle:
                    count += 1
                    if count >= 10:
                        break
                assert count == 10
        finally:
            Path(temp_file).unlink()

    def test_streaming_nonexistent_file(self):
        """Test streaming with nonexistent file"""
        with pytest.raises(OSError):
            with read_file_safe_streaming("/nonexistent/file.txt"):
                pass

    def test_streaming_encoding_detection(self):
        """Test automatic encoding detection in streaming mode"""
        # Create UTF-8 file
        with tempfile.NamedTemporaryFile(
            mode="wb", delete=False, suffix=".txt"
        ) as f:
            f.write("UTF-8 content: 日本語\n".encode("utf-8"))
            temp_file = f.name

        try:
            with read_file_safe_streaming(temp_file) as file_handle:
                content = file_handle.read()
                assert "日本語" in content
                assert "UTF-8 content" in content
        finally:
            Path(temp_file).unlink()

    def test_streaming_different_line_endings(self):
        """Test streaming with different line ending styles"""
        # Test Windows-style (CRLF)
        with tempfile.NamedTemporaryFile(
            mode="wb", delete=False, suffix=".txt"
        ) as f:
            f.write(b"Line 1\r\nLine 2\r\nLine 3\r\n")
            temp_file = f.name

        try:
            with read_file_safe_streaming(temp_file) as file_handle:
                lines = list(file_handle)
                assert len(lines) == 3
                # Lines should preserve line endings
                assert lines[0].rstrip("\r\n") == "Line 1"
        finally:
            Path(temp_file).unlink()

    def test_streaming_pathlib_path(self):
        """Test streaming accepts pathlib.Path"""
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False, suffix=".txt"
        ) as f:
            f.write("Test content\n")
            temp_file = f.name

        try:
            path_obj = Path(temp_file)
            with read_file_safe_streaming(path_obj) as file_handle:
                content = file_handle.read()
                assert "Test content" in content
        finally:
            Path(temp_file).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
