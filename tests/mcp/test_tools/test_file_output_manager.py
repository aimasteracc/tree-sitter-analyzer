#!/usr/bin/env python3
"""
Test module for FileOutputManager

This module provides comprehensive tests for the FileOutputManager class,
covering content type detection, file extension selection, and file output functionality.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.utils.file_output_manager import FileOutputManager


class TestFileOutputManager:
    """Test cases for FileOutputManager class."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = FileOutputManager()

    def teardown_method(self):
        """Clean up test fixtures after each test method."""
        # Clean up temporary files
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_with_project_root(self):
        """Test FileOutputManager initialization with project root."""
        manager = FileOutputManager(self.temp_dir)
        assert manager.project_root == self.temp_dir
        assert manager.get_output_path() == self.temp_dir

    def test_init_with_env_variable(self, monkeypatch):
        """Test FileOutputManager initialization with environment variable."""
        monkeypatch.setenv("TREE_SITTER_OUTPUT_PATH", self.temp_dir)
        manager = FileOutputManager()
        assert manager.get_output_path() == self.temp_dir

    def test_detect_content_type_json(self):
        """Test content type detection for JSON content."""
        json_content = json.dumps({"key": "value", "array": [1, 2, 3]})
        content_type = self.manager.detect_content_type(json_content)
        assert content_type == "json"

        # Test with array
        array_content = json.dumps([{"item": 1}, {"item": 2}])
        content_type = self.manager.detect_content_type(array_content)
        assert content_type == "json"

    def test_detect_content_type_csv(self):
        """Test content type detection for CSV content."""
        csv_content = "Name,Age,City\nJohn,30,New York\nJane,25,Boston"
        content_type = self.manager.detect_content_type(csv_content)
        assert content_type == "csv"

    def test_detect_content_type_markdown(self):
        """Test content type detection for Markdown content."""
        # Test with headers
        markdown_content = "# Title\n## Subtitle\nSome content"
        content_type = self.manager.detect_content_type(markdown_content)
        assert content_type == "markdown"

        # Test with table
        table_content = (
            "| Column 1 | Column 2 |\n|----------|----------|\n| Value 1  | Value 2  |"
        )
        content_type = self.manager.detect_content_type(table_content)
        assert content_type == "markdown"

        # Test with list
        list_content = "* Item 1\n* Item 2\n* Item 3"
        content_type = self.manager.detect_content_type(list_content)
        assert content_type == "markdown"

    def test_detect_content_type_text(self):
        """Test content type detection for plain text content."""
        text_content = "This is just plain text without any special formatting."
        content_type = self.manager.detect_content_type(text_content)
        assert content_type == "text"

    def test_get_file_extension(self):
        """Test file extension mapping."""
        assert self.manager.get_file_extension("json") == ".json"
        assert self.manager.get_file_extension("csv") == ".csv"
        assert self.manager.get_file_extension("markdown") == ".md"
        assert self.manager.get_file_extension("text") == ".txt"
        assert self.manager.get_file_extension("unknown") == ".txt"

    def test_generate_output_filename(self):
        """Test output filename generation."""
        # Test with JSON content
        json_content = '{"key": "value"}'
        filename = self.manager.generate_output_filename("test", json_content)
        assert filename == "test.json"

        # Test with CSV content
        csv_content = "Name,Age\nJohn,30"
        filename = self.manager.generate_output_filename("data", csv_content)
        assert filename == "data.csv"

        # Test with Markdown content
        markdown_content = "# Title\nContent"
        filename = self.manager.generate_output_filename("doc", markdown_content)
        assert filename == "doc.md"

        # Test with existing extension
        filename = self.manager.generate_output_filename("test.old", json_content)
        assert filename == "test.json"

    def test_save_to_file_with_filename(self):
        """Test saving content to file with specific filename."""
        self.manager.set_output_path(self.temp_dir)
        content = "Test content"
        filename = "test_file.txt"

        saved_path = self.manager.save_to_file(content, filename=filename)

        expected_path = Path(self.temp_dir) / filename
        # Normalize paths for Windows compatibility (short vs long path format)
        assert Path(saved_path).resolve() == expected_path.resolve()
        assert expected_path.exists()

        with open(expected_path, encoding="utf-8") as f:
            assert f.read() == content

    def test_save_to_file_with_base_name(self):
        """Test saving content to file with base name (auto extension)."""
        self.manager.set_output_path(self.temp_dir)
        json_content = '{"key": "value"}'
        base_name = "test_data"

        saved_path = self.manager.save_to_file(json_content, base_name=base_name)

        expected_path = Path(self.temp_dir) / "test_data.json"
        # Normalize paths for Windows compatibility (short vs long path format)
        assert Path(saved_path).resolve() == expected_path.resolve()
        assert expected_path.exists()

        with open(expected_path, encoding="utf-8") as f:
            assert f.read() == json_content

    def test_save_to_file_missing_parameters(self):
        """Test saving content to file with missing parameters."""
        content = "Test content"

        with pytest.raises(
            ValueError, match="Either filename or base_name must be provided"
        ):
            self.manager.save_to_file(content)

    def test_save_to_file_creates_directory(self):
        """Test that save_to_file creates parent directories if needed."""
        self.manager.set_output_path(self.temp_dir)
        content = "Test content"
        filename = "subdir/test_file.txt"

        saved_path = self.manager.save_to_file(content, filename=filename)

        expected_path = Path(self.temp_dir) / filename
        # Normalize paths for Windows compatibility (short vs long path format)
        assert Path(saved_path).resolve() == expected_path.resolve()
        assert expected_path.exists()
        assert expected_path.parent.exists()

    def test_validate_output_path_valid(self):
        """Test output path validation with valid path."""
        test_file = Path(self.temp_dir) / "test.txt"
        is_valid, error_msg = self.manager.validate_output_path(str(test_file))

        assert is_valid is True
        assert error_msg is None

    def test_validate_output_path_no_write_permission(self, monkeypatch):
        """Test output path validation with no write permission."""
        # Mock os.access to return False for write permission
        monkeypatch.setattr(
            os, "access", lambda path, mode: False if mode == os.W_OK else True
        )

        test_file = Path(self.temp_dir) / "test.txt"
        is_valid, error_msg = self.manager.validate_output_path(str(test_file))

        assert is_valid is False
        assert "No write permission" in error_msg

    def test_set_output_path_valid(self):
        """Test setting valid output path."""
        self.manager.set_output_path(self.temp_dir)
        assert self.manager.get_output_path() == str(Path(self.temp_dir).resolve())

    def test_set_output_path_invalid(self):
        """Test setting invalid output path."""
        # Use a path that definitely doesn't exist on any OS
        invalid_path = str(Path(self.temp_dir) / "nonexistent_directory_xyz")

        with pytest.raises(ValueError, match="Output path does not exist"):
            self.manager.set_output_path(invalid_path)

    def test_set_output_path_not_directory(self):
        """Test setting output path to a file instead of directory."""
        test_file = Path(self.temp_dir) / "test.txt"
        test_file.write_text("content")

        with pytest.raises(ValueError, match="Output path is not a directory"):
            self.manager.set_output_path(str(test_file))

    def test_set_project_root_updates_output_path(self):
        """Test that setting project root updates output path when no env var is set."""
        manager = FileOutputManager()
        manager.get_output_path()

        manager.set_project_root(self.temp_dir)

        # Should update to new project root since no env var is set
        assert manager.get_output_path() == self.temp_dir

    def test_set_project_root_preserves_env_path(self, monkeypatch):
        """Test that setting project root preserves env var path."""
        env_path = self.temp_dir
        monkeypatch.setenv("TREE_SITTER_OUTPUT_PATH", env_path)

        manager = FileOutputManager()
        manager.get_output_path()

        # Create another temp dir for project root
        other_temp_dir = tempfile.mkdtemp()
        try:
            manager.set_project_root(other_temp_dir)

            # Should still use env var path
            assert manager.get_output_path() == env_path
        finally:
            import shutil

            shutil.rmtree(other_temp_dir, ignore_errors=True)

    def test_content_type_edge_cases(self):
        """Test content type detection edge cases."""
        # Empty content
        assert self.manager.detect_content_type("") == "text"

        # Whitespace only
        assert self.manager.detect_content_type("   \n  \t  ") == "text"

        # Invalid JSON that starts with {
        invalid_json = '{"invalid": json content}'
        assert self.manager.detect_content_type(invalid_json) == "text"

        # Single line with comma (not CSV)
        single_line = "This is a sentence, with commas, but not CSV"
        assert self.manager.detect_content_type(single_line) == "text"

    def test_filename_generation_edge_cases(self):
        """Test filename generation edge cases."""
        # Empty base name
        filename = self.manager.generate_output_filename("", "content")
        assert filename.endswith(".txt")

        # Base name with multiple dots
        filename = self.manager.generate_output_filename(
            "file.backup.old", '{"json": true}'
        )
        assert filename == "file.backup.json"

        # Base name with path separators (should be cleaned)
        filename = self.manager.generate_output_filename("path/to/file", "content")
        assert filename == "file.txt"


if __name__ == "__main__":
    pytest.main([__file__])
