#!/usr/bin/env python3
"""
Unit tests for FileLoader

Tests file loading with encoding detection and error handling.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.core.file_loader import FileLoader, FileLoadError


class TestFileLoader:
    """Test suite for FileLoader"""

    @pytest.fixture
    def loader(self):
        """Create FileLoader instance"""
        return FileLoader()

    @pytest.fixture
    def temp_file(self):
        """Create temporary file for testing"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
            f.write("Hello, World!\n")
            temp_path = f.name

        yield temp_path

        # Cleanup
        Path(temp_path).unlink(missing_ok=True)

    def test_load_utf8_file(self, loader, temp_file):
        """Test loading UTF-8 encoded file"""
        content = loader.load(temp_file)

        assert content == "Hello, World!\n"

    def test_load_with_specific_encoding(self, loader):
        """Test loading file with specific encoding"""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, encoding="latin-1"
        ) as f:
            f.write("Héllo, Wörld!\n")
            temp_path = f.name

        try:
            content = loader.load_with_encoding(temp_path, "latin-1")
            assert "Héllo" in content
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_load_nonexistent_file(self, loader):
        """Test that loading nonexistent file raises FileLoadError"""
        with pytest.raises(FileLoadError, match="File not found"):
            loader.load("/nonexistent/file.txt")

    def test_load_directory(self, loader):
        """Test that loading directory raises FileLoadError"""
        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(FileLoadError, match="Not a file"):
                loader.load(temp_dir)

    def test_exists_true(self, loader, temp_file):
        """Test exists() returns True for existing file"""
        assert loader.exists(temp_file) is True

    def test_exists_false(self, loader):
        """Test exists() returns False for nonexistent file"""
        assert loader.exists("/nonexistent/file.txt") is False

    def test_get_file_size(self, loader, temp_file):
        """Test getting file size"""
        size = loader.get_file_size(temp_file)

        # Get actual file size from the temp file
        actual_size = Path(temp_file).stat().st_size

        assert size > 0
        assert size == actual_size

    def test_get_file_size_nonexistent(self, loader):
        """Test that getting size of nonexistent file raises FileLoadError"""
        with pytest.raises(FileLoadError, match="File not found"):
            loader.get_file_size("/nonexistent/file.txt")

    def test_load_utf8_with_bom(self, loader):
        """Test loading UTF-8 file with BOM"""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, encoding="utf-8-sig"
        ) as f:
            f.write("Hello, World!\n")
            temp_path = f.name

        try:
            content = loader.load(temp_path)
            # BOM should be handled automatically
            assert content == "Hello, World!\n"
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_load_with_path_object(self, loader, temp_file):
        """Test loading file using Path object"""
        content = loader.load(Path(temp_file))

        assert content == "Hello, World!\n"

    def test_load_empty_file(self, loader):
        """Test loading empty file"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
            temp_path = f.name

        try:
            content = loader.load(temp_path)
            assert content == ""
        finally:
            Path(temp_path).unlink(missing_ok=True)
