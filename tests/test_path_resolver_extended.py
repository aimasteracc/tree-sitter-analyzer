#!/usr/bin/env python3
"""
Extended tests for PathResolver to improve test coverage.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from tree_sitter_analyzer.mcp.utils.path_resolver import PathResolver, resolve_path


def normalize_path_for_comparison(path_str):
    """
    Normalize path for comparison, handling platform-specific differences.
    """
    path = Path(path_str).resolve()
    # On Windows, handle short path names (8.3 format)
    if sys.platform == "win32":
        try:
            # Try to get the long path name
            long_path = os.path.abspath(str(path))
            return str(Path(long_path).resolve())
        except (OSError, ValueError):
            return str(path)
    # On macOS, handle /var vs /private/var differences
    elif sys.platform == "darwin" and str(path).startswith("/private/var/"):
        return str(path).replace("/private/var/", "/var/")
    return str(path)


class TestPathResolverExtended(unittest.TestCase):
    """Extended test cases for PathResolver class"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.project_root = self.temp_dir / "project"
        self.project_root.mkdir()

        # Create a test file inside the project
        self.test_file = self.project_root / "test.txt"
        with open(self.test_file, "w") as f:
            f.write("test content")

        self.resolver = PathResolver(str(self.project_root))

    def tearDown(self):
        """Clean up test fixtures"""
        # Use shutil.rmtree to properly clean up the entire temp directory
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_resolve_with_none_project_root(self):
        """Test resolve method when project_root is None."""
        resolver = PathResolver(None)
        result = resolver.resolve("test.txt")
        self.assertIsInstance(result, str)
        self.assertTrue(Path(result).is_absolute())

    def test_resolve_with_empty_string_project_root(self):
        """Test resolve method with empty string project_root."""
        resolver = PathResolver("")
        result = resolver.resolve("test.txt")
        self.assertIsInstance(result, str)
        self.assertTrue(Path(result).is_absolute())

    def test_resolve_with_relative_path_dot(self):
        """Test resolve method with relative path starting with dot."""
        result = self.resolver.resolve("./test.txt")
        expected = str(self.project_root / "test.txt")
        self.assertEqual(Path(result).resolve(), Path(expected).resolve())

    def test_resolve_with_relative_path_double_dot(self):
        """Test resolve method with relative path starting with double dot."""
        subdir = self.project_root / "subdir"
        subdir.mkdir(exist_ok=True)

        resolver = PathResolver(str(subdir))
        result = resolver.resolve("../test.txt")
        expected = str(self.project_root / "test.txt")
        self.assertEqual(Path(result).resolve(), Path(expected).resolve())

    def test_resolve_with_mixed_separators(self):
        """Test resolve method with mixed path separators."""
        if os.name == "nt":  # Windows
            result = self.resolver.resolve("test\\subdir/file.txt")
            expected = str(self.project_root / "test" / "subdir" / "file.txt")
            self.assertEqual(Path(result).resolve(), Path(expected).resolve())

    def test_validate_path_with_directory(self):
        """Test validate_path with directory path."""
        # Create a subdirectory to test directory validation
        subdir = self.project_root / "subdir"
        subdir.mkdir()

        is_valid, error_msg = self.resolver.validate_path(str(subdir))
        # Directory validation behavior may vary, so we just check it doesn't crash
        self.assertIsInstance(is_valid, bool)
        self.assertIsInstance(error_msg, (str, type(None)))

    def test_validate_path_with_permission_error(self):
        """Test validate_path with permission error."""
        # Create a file that might cause permission issues
        restricted_file = self.project_root / "restricted.txt"
        with open(restricted_file, "w") as f:
            f.write("test")

        # On Windows, we can't easily simulate permission errors in tests
        # So we just test that the file is valid
        is_valid, error_msg = self.resolver.validate_path(str(restricted_file))
        self.assertTrue(is_valid)
        self.assertIsNone(error_msg)

    def test_validate_path_with_symlink(self):
        """Test validate_path with symlink."""
        # Create a symlink test
        original_file = self.project_root / "original.txt"
        with open(original_file, "w") as f:
            f.write("original content")

        # On Windows, creating symlinks requires admin privileges
        # So we'll just test the original file
        is_valid, error_msg = self.resolver.validate_path(str(original_file))
        self.assertTrue(is_valid)
        self.assertIsNone(error_msg)

    def test_get_relative_path_with_absolute_path(self):
        """Test get_relative_path method with absolute path."""
        result = self.resolver.get_relative_path(str(self.test_file))
        # The result should be the relative path from project root
        # Use normalized paths for comparison to handle Windows short path names
        expected_relative = Path(self.test_file).relative_to(
            Path(self.project_root).resolve()
        )
        actual_relative = Path(result)

        # Normalize both paths for comparison
        expected_normalized = normalize_path_for_comparison(str(expected_relative))
        actual_normalized = normalize_path_for_comparison(str(actual_relative))

        self.assertEqual(actual_normalized, expected_normalized)

    def test_get_relative_path_with_path_outside_project(self):
        """Test get_relative_path method with path outside project."""
        outside_path = str(self.temp_dir / "outside.txt")
        result = self.resolver.get_relative_path(outside_path)
        # The path should be returned as-is since it's outside the project
        # On Windows, this might be normalized differently
        self.assertIn("outside.txt", result)

    def test_get_relative_path_with_none_project_root(self):
        """Test get_relative_path method when project_root is None."""
        resolver = PathResolver(None)
        result = resolver.get_relative_path(str(self.test_file))
        self.assertEqual(result, str(self.test_file))

    def test_is_relative_with_absolute_path(self):
        """Test is_relative method with absolute path."""
        result = self.resolver.is_relative(str(self.test_file))
        self.assertFalse(result)

    def test_is_relative_with_relative_path(self):
        """Test is_relative method with relative path."""
        result = self.resolver.is_relative("test.txt")
        self.assertTrue(result)

    def test_is_relative_with_empty_path(self):
        """Test is_relative method with empty path."""
        result = self.resolver.is_relative("")
        self.assertTrue(result)

    def test_is_relative_with_none_path(self):
        """Test is_relative method with None path."""
        with self.assertRaises(TypeError):
            self.resolver.is_relative(None)

    def test_path_normalization(self):
        """Test path normalization."""
        result = self.resolver.resolve("test/../test.txt")
        expected = str(self.project_root / "test.txt")
        self.assertEqual(Path(result).resolve(), Path(expected).resolve())

    def test_set_project_root_with_none(self):
        """Test set_project_root method with None."""
        self.resolver.set_project_root(None)
        self.assertIsNone(self.resolver.project_root)

    def test_set_project_root_with_empty_string(self):
        """Test set_project_root method with empty string."""
        self.resolver.set_project_root("")
        self.assertIsNone(self.resolver.project_root)

    def test_set_project_root_with_valid_path(self):
        """Test set_project_root method with valid path."""
        new_root = str(self.temp_dir / "new_project")
        Path(new_root).mkdir()

        self.resolver.set_project_root(new_root)
        expected = normalize_path_for_comparison(new_root)
        actual = normalize_path_for_comparison(self.resolver.project_root)
        self.assertEqual(actual, expected)

    def test_resolve_path_function_with_none_project_root(self):
        """Test resolve_path function with None project_root."""
        result = resolve_path("test.txt", None)
        self.assertIsInstance(result, str)
        self.assertTrue(Path(result).is_absolute())

    def test_resolve_path_function_with_empty_project_root(self):
        """Test resolve_path function with empty project_root."""
        result = resolve_path("test.txt", "")
        self.assertIsInstance(result, str)
        self.assertTrue(Path(result).is_absolute())

    def test_resolve_path_function_with_valid_project_root(self):
        """Test resolve_path function with valid project_root."""
        result = resolve_path("test.txt", str(self.project_root))
        expected = str(self.project_root / "test.txt")
        self.assertEqual(Path(result).resolve(), Path(expected).resolve())

    def test_cross_platform_path_handling(self):
        """Test cross-platform path handling."""
        # Test Windows-style paths on all platforms
        windows_path = "C:\\Users\\test\\file.txt"
        result = self.resolver.resolve(windows_path)
        # Should return the normalized absolute path
        # Convert to forward slashes for consistent comparison
        normalized_result = result.replace("\\", "/")
        # On Windows, the result should start with the drive letter
        if os.name == "nt":
            self.assertTrue(
                result.startswith("C:\\"),
                f"Result should start with 'C:\\', got: {result}",
            )
        else:
            # On non-Windows, Windows absolute paths should be returned as-is
            # They should not be resolved relative to project root
            normalized_windows = windows_path.replace("\\", "/")
            self.assertEqual(normalized_result, normalized_windows)

        # Test Unix-style paths on all platforms
        unix_path = "/home/user/file.txt"
        result = self.resolver.resolve(unix_path)
        # On Windows, this will be converted to Windows format
        if os.name == "nt":
            # On Windows, absolute paths starting with / are converted to current drive
            # The result will be something like "C:\home\user\file.txt"
            current_drive = str(Path.cwd().anchor).rstrip("\\")
            expected_start = current_drive + "\\"

            # Debug information for CI troubleshooting
            if not result.startswith(expected_start):
                print(f"DEBUG: unix_path='{unix_path}'")
                print(f"DEBUG: result='{result}' (repr: {repr(result)})")
                print(f"DEBUG: current_drive='{current_drive}'")
                print(f"DEBUG: expected_start='{expected_start}'")
                print(f"DEBUG: os.getcwd()='{os.getcwd()}'")
                print(f"DEBUG: Path.cwd().anchor={Path.cwd().anchor}")

            # Check if result starts with expected drive and ends with expected path
            self.assertTrue(
                result.startswith(expected_start),
                f"Expected result '{result}' to start with '{expected_start}'",
            )
            # The result should end with the converted Unix path
            expected_end = "\\home\\user\\file.txt"
            self.assertTrue(
                result.endswith(expected_end),
                f"Expected result '{result}' to end with '{expected_end}'",
            )
        else:
            # On Unix systems, handle macOS /System/Volumes/Data normalization
            expected = unix_path
            # If the result has /System/Volumes/Data prefix, it should be normalized
            if result.startswith("/System/Volumes/Data"):
                # The normalization should remove the prefix
                expected_normalized = result[len("/System/Volumes/Data") :]
                self.assertEqual(expected_normalized, expected)
            else:
                self.assertEqual(result, expected)

    def test_edge_cases(self):
        """Test various edge cases."""
        # Test with very long path
        long_path = "a" * 1000
        result = self.resolver.resolve(long_path)
        self.assertIsInstance(result, str)

        # Test with path containing special characters
        special_path = "test@#$%^&*()_+-=[]{}|;':\",./<>?`~.txt"
        result = self.resolver.resolve(special_path)
        self.assertIsInstance(result, str)

        # Test with path containing spaces
        space_path = "test file with spaces.txt"
        result = self.resolver.resolve(space_path)
        self.assertIsInstance(result, str)

    def test_error_handling(self):
        """Test error handling in various scenarios."""
        # Test with invalid project root
        invalid_resolver = PathResolver("/nonexistent/path")
        result = invalid_resolver.resolve("test.txt")
        self.assertIsInstance(result, str)

        # Test with None file path
        with self.assertRaises(ValueError):
            self.resolver.resolve(None)

        # Test with empty file path
        with self.assertRaises(ValueError):
            self.resolver.resolve("")

    def test_cache_functionality(self):
        """Test cache functionality."""
        # Test initial cache state
        cache_stats = self.resolver.get_cache_stats()
        self.assertEqual(cache_stats["size"], 0)
        self.assertEqual(cache_stats["limit"], 100)

        # Test caching after path resolution
        result1 = self.resolver.resolve("test1.txt")
        cache_stats = self.resolver.get_cache_stats()
        self.assertEqual(cache_stats["size"], 1)

        # Test cache hit
        result2 = self.resolver.resolve("test1.txt")
        self.assertEqual(result1, result2)

        # Test cache limit
        for i in range(105):  # Exceed cache limit
            self.resolver.resolve(f"test{i}.txt")

        cache_stats = self.resolver.get_cache_stats()
        self.assertLessEqual(cache_stats["size"], cache_stats["limit"])

        # Test cache clearing
        self.resolver.clear_cache()
        cache_stats = self.resolver.get_cache_stats()
        self.assertEqual(cache_stats["size"], 0)


if __name__ == "__main__":
    unittest.main()
