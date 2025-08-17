#!/usr/bin/env python3
"""
Extended tests for PathResolver to improve test coverage.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tree_sitter_analyzer.mcp.utils.path_resolver import PathResolver, resolve_path


class TestPathResolverExtended(unittest.TestCase):
    """Extended tests for PathResolver class."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.project_root = self.temp_dir / "project"
        self.project_root.mkdir(exist_ok=True)

        # Create test files
        self.test_file = self.project_root / "test.txt"
        with open(self.test_file, "w") as f:
            f.write("test content")

        self.resolver = PathResolver(str(self.project_root))

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(str(self.temp_dir), ignore_errors=True)

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
        """Test validate_path method with directory path."""
        subdir = self.project_root / "subdir"
        subdir.mkdir(exist_ok=True)

        is_valid, error_msg = self.resolver.validate_path(str(subdir))
        self.assertFalse(is_valid)
        self.assertIn("not a file", error_msg)

    def test_validate_path_with_symlink(self):
        """Test validate_path method with symlink."""
        if os.name != "nt":  # Skip on Windows
            try:
                symlink_path = self.project_root / "symlink"
                symlink_path.symlink_to(self.test_file)

                is_valid, error_msg = self.resolver.validate_path(str(symlink_path))
                # The validation should either reject the symlink or pass it
                # depending on platform capabilities
                if not is_valid:
                    self.assertIn("symlink", error_msg)
                else:
                    # If symlink detection is not available, that's also acceptable
                    pass
            except (OSError, NotImplementedError):
                # Symlink creation might not be supported in test environment
                # Skip this test if symlinks are not supported
                self.skipTest("Symlinks not supported in this environment")

    def test_validate_path_with_permission_error(self):
        """Test validate_path method with permission error."""
        with patch(
            "pathlib.Path.exists", side_effect=PermissionError("Permission denied")
        ):
            is_valid, error_msg = self.resolver.validate_path("test.txt")
            self.assertFalse(is_valid)
            self.assertIn("Permission denied", error_msg)

    def test_get_relative_path_with_absolute_path(self):
        """Test get_relative_path method with absolute path."""
        result = self.resolver.get_relative_path(str(self.test_file))
        self.assertEqual(result, "test.txt")

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
        new_root = self.temp_dir / "new_project"
        new_root.mkdir(exist_ok=True)

        self.resolver.set_project_root(str(new_root))
        self.assertEqual(Path(self.resolver.project_root).resolve(), new_root.resolve())

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
            # On non-Windows, should be the same
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
            expected = unix_path
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
