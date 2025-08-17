#!/usr/bin/env python3
"""
Tests for PathResolver utility class

This module tests the PathResolver class to ensure it correctly handles
path resolution across different operating systems and scenarios.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

from tree_sitter_analyzer.mcp.utils.path_resolver import PathResolver, resolve_path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestPathResolver(unittest.TestCase):
    """Test cases for PathResolver class"""

    def setUp(self):
        """Set up test fixtures"""
        # Create a temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "test_file.txt")

        # Create a test file
        with open(self.test_file, "w") as f:
            f.write("test content")

        # Test project root
        self.project_root = self.temp_dir
        self.resolver = PathResolver(self.project_root)

    def tearDown(self):
        """Clean up test fixtures"""
        # Remove test file and directory
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    def test_init_with_project_root(self):
        """Test PathResolver initialization with project root"""
        resolver = PathResolver(self.project_root)
        self.assertEqual(resolver.project_root, os.path.normpath(self.project_root))

    def test_init_without_project_root(self):
        """Test PathResolver initialization without project root"""
        resolver = PathResolver()
        self.assertIsNone(resolver.project_root)

    def test_resolve_absolute_path(self):
        """Test resolving absolute paths"""
        absolute_path = os.path.abspath(self.test_file)
        resolved = self.resolver.resolve(absolute_path)
        self.assertEqual(resolved, os.path.normpath(absolute_path))

    def test_resolve_relative_path_with_project_root(self):
        """Test resolving relative paths with project root"""
        relative_path = "test_file.txt"
        resolved = self.resolver.resolve(relative_path)
        expected = os.path.join(self.project_root, relative_path)
        self.assertEqual(resolved, os.path.normpath(expected))

    def test_resolve_relative_path_without_project_root(self):
        """Test resolving relative paths without project root"""
        resolver = PathResolver()
        relative_path = "test_file.txt"
        resolved = resolver.resolve(relative_path)
        expected = os.path.abspath(relative_path)
        self.assertEqual(resolved, os.path.normpath(expected))

    def test_resolve_nested_relative_path(self):
        """Test resolving nested relative paths"""
        nested_path = "subdir/test_file.txt"
        resolved = self.resolver.resolve(nested_path)
        expected = os.path.join(self.project_root, nested_path)
        self.assertEqual(resolved, os.path.normpath(expected))

    def test_resolve_empty_path(self):
        """Test resolving empty path raises ValueError"""
        with self.assertRaises(ValueError):
            self.resolver.resolve("")

    def test_resolve_none_path(self):
        """Test resolving None path raises error"""
        with self.assertRaises((TypeError, ValueError)):
            self.resolver.resolve(None)

    def test_is_relative(self):
        """Test is_relative method"""
        self.assertTrue(self.resolver.is_relative("test_file.txt"))
        self.assertFalse(self.resolver.is_relative(os.path.abspath(self.test_file)))

    def test_get_relative_path(self):
        """Test get_relative_path method"""
        absolute_path = os.path.abspath(self.test_file)
        relative_path = self.resolver.get_relative_path(absolute_path)
        self.assertEqual(relative_path, "test_file.txt")

    def test_get_relative_path_no_project_root(self):
        """Test get_relative_path without project root"""
        resolver = PathResolver()
        absolute_path = os.path.abspath(self.test_file)
        relative_path = resolver.get_relative_path(absolute_path)
        self.assertEqual(relative_path, absolute_path)

    def test_validate_path_valid(self):
        """Test validate_path with valid path"""
        is_valid, error_msg = self.resolver.validate_path("test_file.txt")
        self.assertTrue(is_valid)
        self.assertIsNone(error_msg)

    def test_validate_path_invalid(self):
        """Test validate_path with invalid path"""
        is_valid, error_msg = self.resolver.validate_path("nonexistent_file.txt")
        self.assertFalse(is_valid)
        self.assertIsNotNone(error_msg)

    def test_validate_path_outside_project_root(self):
        """Test validate_path with path outside project root"""
        # Create a path outside the project root
        outside_path = os.path.join(os.path.dirname(self.temp_dir), "outside_file.txt")
        is_valid, error_msg = self.resolver.validate_path(outside_path)
        self.assertFalse(is_valid)
        self.assertIsNotNone(error_msg)

    def test_set_project_root(self):
        """Test set_project_root method"""
        new_root = "/new/project/root"
        self.resolver.set_project_root(new_root)
        # On Windows, paths are normalized to use backslashes
        expected = os.path.normpath(new_root)
        self.assertEqual(self.resolver.project_root, expected)

    def test_set_project_root_none(self):
        """Test set_project_root with None"""
        self.resolver.set_project_root(None)
        self.assertIsNone(self.resolver.project_root)

    def test_cross_platform_path_separators(self):
        """Test handling of different path separators"""
        # Test Windows-style path
        windows_path = "dir\\subdir\\file.txt"
        resolved = self.resolver.resolve(windows_path)
        expected = os.path.join(self.project_root, "dir", "subdir", "file.txt")
        # Both should normalize to the same path
        self.assertEqual(os.path.normpath(resolved), os.path.normpath(expected))

        # Test Unix-style path
        unix_path = "dir/subdir/file.txt"
        resolved = self.resolver.resolve(unix_path)
        expected = os.path.join(self.project_root, "dir", "subdir", "file.txt")
        # Both should normalize to the same path
        self.assertEqual(os.path.normpath(resolved), os.path.normpath(expected))

    def test_path_normalization(self):
        """Test path normalization"""
        # Test path with multiple separators
        messy_path = "dir//subdir\\\\file.txt"
        resolved = self.resolver.resolve(messy_path)
        expected = os.path.join(self.project_root, "dir", "subdir", "file.txt")
        # Both should normalize to the same path
        self.assertEqual(os.path.normpath(resolved), os.path.normpath(expected))

        # Test path with dots
        dot_path = "./dir/../dir/file.txt"
        resolved = self.resolver.resolve(dot_path)
        expected = os.path.join(self.project_root, "dir", "file.txt")
        # Both should normalize to the same path
        self.assertEqual(os.path.normpath(resolved), os.path.normpath(expected))


class TestResolvePathFunction(unittest.TestCase):
    """Test cases for resolve_path convenience function"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "test_file.txt")

        with open(self.test_file, "w") as f:
            f.write("test content")

    def tearDown(self):
        """Clean up test fixtures"""
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    def test_resolve_path_with_project_root(self):
        """Test resolve_path function with project root"""
        relative_path = "test_file.txt"
        resolved = resolve_path(relative_path, self.temp_dir)
        expected = os.path.join(self.temp_dir, relative_path)
        self.assertEqual(resolved, os.path.normpath(expected))

    def test_resolve_path_without_project_root(self):
        """Test resolve_path function without project root"""
        relative_path = "test_file.txt"
        resolved = resolve_path(relative_path)
        expected = os.path.abspath(relative_path)
        self.assertEqual(resolved, os.path.normpath(expected))

    def test_resolve_path_absolute(self):
        """Test resolve_path function with absolute path"""
        absolute_path = os.path.abspath(self.test_file)
        resolved = resolve_path(absolute_path, self.temp_dir)
        self.assertEqual(resolved, os.path.normpath(absolute_path))


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
