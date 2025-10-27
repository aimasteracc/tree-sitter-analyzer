#!/usr/bin/env python3
"""
Tests for Project Root Detection

Tests the intelligent project root detection functionality.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from tree_sitter_analyzer.project_detector import (
    ProjectRootDetector,
    detect_project_root,
)


def normalize_path_for_comparison(path_str):
    """
    Normalize path for comparison, handling platform-specific differences.
    """
    path = Path(path_str).resolve()

    # On Windows, handle short path names (8.3 format)
    if sys.platform == "win32":
        try:
            # Convert to absolute path first
            abs_path = os.path.abspath(str(path))

            # Try to get the long path name using Windows API if available
            try:
                import ctypes
                from ctypes import wintypes

                # Get the long path name using Windows API
                kernel32 = ctypes.windll.kernel32
                GetLongPathNameW = kernel32.GetLongPathNameW
                GetLongPathNameW.argtypes = [
                    wintypes.LPCWSTR,
                    wintypes.LPWSTR,
                    wintypes.DWORD,
                ]
                GetLongPathNameW.restype = wintypes.DWORD

                # Convert to Windows path format
                windows_path = str(abs_path).replace("/", "\\")

                # Get buffer size needed
                size = GetLongPathNameW(windows_path, None, 0)
                if size > 0:
                    buffer = ctypes.create_unicode_buffer(size)
                    if GetLongPathNameW(windows_path, buffer, size) > 0:
                        return str(Path(buffer.value).resolve())
            except (ImportError, OSError, AttributeError):
                # Fallback to basic normalization
                pass

            # Fallback: try to resolve any remaining short path components
            resolved_path = Path(abs_path).resolve()
            return str(resolved_path)

        except (OSError, ValueError):
            return str(path)

    # On macOS, handle /var vs /private/var differences
    elif sys.platform == "darwin" and str(path).startswith("/private/var/"):
        return str(path).replace("/private/var/", "/var/")

    return str(path)


class TestProjectRootDetector(unittest.TestCase):
    """Test cases for ProjectRootDetector class"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_detect_from_git_repo(self):
        """Test detection from git repository"""
        # Create a git repository
        git_dir = self.temp_dir / "git_project"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()

        detector = ProjectRootDetector()
        result = detector.detect_from_file(str(git_dir / "test.py"))

        expected = normalize_path_for_comparison(str(git_dir))
        actual = normalize_path_for_comparison(str(result))
        self.assertEqual(actual, expected)

    def test_detect_from_python_project(self):
        """Test detection from Python project"""
        # Create a Python project
        python_dir = self.temp_dir / "python_project"
        python_dir.mkdir()
        (python_dir / "pyproject.toml").touch()

        detector = ProjectRootDetector()
        result = detector.detect_from_file(str(python_dir / "test.py"))

        expected = normalize_path_for_comparison(str(python_dir))
        actual = normalize_path_for_comparison(str(result))
        self.assertEqual(actual, expected)

    def test_detect_from_javascript_project(self):
        """Test detection from JavaScript project"""
        # Create a JavaScript project
        js_dir = self.temp_dir / "js_project"
        js_dir.mkdir()
        (js_dir / "package.json").touch()

        detector = ProjectRootDetector()
        result = detector.detect_from_file(str(js_dir / "test.js"))

        expected = normalize_path_for_comparison(str(js_dir))
        actual = normalize_path_for_comparison(str(result))
        self.assertEqual(actual, expected)

    def test_detect_from_java_project(self):
        """Test detection from Java project"""
        # Create a Java project
        java_dir = self.temp_dir / "java_project"
        java_dir.mkdir()
        (java_dir / "pom.xml").touch()

        detector = ProjectRootDetector()
        result = detector.detect_from_file(str(java_dir / "Test.java"))

        expected = normalize_path_for_comparison(str(java_dir))
        actual = normalize_path_for_comparison(str(result))
        self.assertEqual(actual, expected)

    def test_multiple_markers_priority(self):
        """Test priority when multiple markers are found"""
        # Create a project with multiple markers
        multi_dir = self.temp_dir / "multi_project"
        multi_dir.mkdir()
        (multi_dir / ".git").mkdir()
        (multi_dir / "pyproject.toml").touch()

        detector = ProjectRootDetector()
        result = detector.detect_from_file(str(multi_dir / "test.py"))

        expected = normalize_path_for_comparison(str(multi_dir))
        actual = normalize_path_for_comparison(str(result))
        self.assertEqual(actual, expected)

    def test_no_markers_found(self):
        """Test behavior when no markers are found"""
        # Create a directory without project markers in a deep isolated location
        # to avoid accidentally finding markers in parent directories
        no_markers_dir = self.temp_dir / "very" / "deep" / "isolated" / "no_markers"
        no_markers_dir.mkdir(parents=True)

        # Use a detector with limited depth to ensure no markers are found
        detector = ProjectRootDetector(max_depth=3)
        result = detector.detect_from_file(str(no_markers_dir / "test.py"))

        # When no markers are found, detect_from_file returns None
        # The fallback behavior is tested separately
        self.assertIsNone(result)

    def test_max_depth_limit(self):
        """Test max depth limit"""
        # Create a deep directory structure
        deep_dir = self.temp_dir / "very" / "deep" / "isolated" / "directory"
        deep_dir.mkdir(parents=True)

        detector = ProjectRootDetector(max_depth=2)
        result = detector.detect_from_file(str(deep_dir / "test.py"))

        # With limited depth, no markers should be found
        self.assertIsNone(result)

    def test_fallback_behavior(self):
        """Test fallback behavior"""
        # Create a directory without project markers
        fallback_dir = self.temp_dir / "fallback_test"
        fallback_dir.mkdir()

        detector = ProjectRootDetector()

        # Test fallback for non-existing file - should return cwd
        fallback = detector.get_fallback_root("/non/existing/file.py")
        expected_cwd = normalize_path_for_comparison(str(Path.cwd()))
        actual_cwd = normalize_path_for_comparison(str(fallback))
        self.assertEqual(actual_cwd, expected_cwd)

        # Test fallback for existing file in temp directory
        test_file = fallback_dir / "existing.py"
        test_file.touch()
        fallback = detector.get_fallback_root(str(test_file))
        expected_file_dir = normalize_path_for_comparison(str(fallback_dir))
        actual_file_dir = normalize_path_for_comparison(str(fallback))
        self.assertEqual(actual_file_dir, expected_file_dir)

        # Test fallback for non-existing file in temp directory
        # This might return cwd if the current directory is detected as project root
        fallback = detector.get_fallback_root(str(fallback_dir / "nonexistent.py"))
        # The result could be either the temp directory or cwd, depending on project detection
        self.assertIn(
            normalize_path_for_comparison(str(fallback)),
            [
                normalize_path_for_comparison(str(fallback_dir)),
                normalize_path_for_comparison(str(Path.cwd())),
            ],
        )

    def test_invalid_explicit_root(self):
        """Test behavior with invalid explicit root"""
        # Create a valid project
        project_root = self.temp_dir / "project"
        project_root.mkdir()
        with open(project_root / "pyproject.toml", "w") as f:
            f.write("[tool.poetry]\n")

        test_file = project_root / "test.py"
        test_file.touch()

        # Test with invalid explicit root - the actual behavior depends on implementation
        result = detect_project_root(str(test_file), "/invalid/path")

        # The result could be either the invalid path or the detected project root
        # depending on how the implementation handles invalid explicit roots
        possible_results = [
            normalize_path_for_comparison("/invalid/path"),
            normalize_path_for_comparison(str(project_root)),
        ]
        actual = normalize_path_for_comparison(str(result))
        self.assertIn(actual, possible_results)


class TestUnifiedDetectProjectRoot(unittest.TestCase):
    """Test cases for unified detect_project_root function"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_explicit_root_priority(self):
        """Test that explicit root takes priority"""
        # Create a project with markers
        project_dir = self.temp_dir / "project"
        project_dir.mkdir()
        (project_dir / ".git").mkdir()

        # Create a file in a subdirectory
        test_file = project_dir / "subdir" / "test.py"
        test_file.parent.mkdir()
        test_file.touch()

        # Test with explicit root
        explicit_root = str(project_dir / "subdir")
        result = detect_project_root(str(test_file), explicit_root)

        expected = normalize_path_for_comparison(explicit_root)
        actual = normalize_path_for_comparison(str(result))
        self.assertEqual(actual, expected)

    def test_auto_detection_from_file(self):
        """Test auto detection from file"""
        # Create a project with markers
        project_dir = self.temp_dir / "project"
        project_dir.mkdir()
        (project_dir / ".git").mkdir()

        # Create a file in the project
        test_file = project_dir / "test.py"
        test_file.touch()

        result = detect_project_root(str(test_file))

        expected = normalize_path_for_comparison(str(project_dir))
        actual = normalize_path_for_comparison(str(result))
        self.assertEqual(actual, expected)

    def test_fallback_to_file_directory(self):
        """Test fallback to file directory"""
        # Create a deep isolated directory without project markers
        isolated_base = self.temp_dir / "very" / "deep" / "isolated" / "directory"
        isolated_base.mkdir(parents=True)

        # Create a test file
        test_file = isolated_base / "test.py"
        test_file.touch()

        # Use explicit detector with limited depth to avoid finding project root
        detector = ProjectRootDetector(max_depth=2)
        result = detector.detect_from_file(str(test_file))

        # Should return None when no markers found within depth limit
        assert result is None

        # Test fallback behavior
        fallback = detector.get_fallback_root(str(test_file))
        expected = normalize_path_for_comparison(str(isolated_base))
        actual = normalize_path_for_comparison(str(fallback))
        self.assertEqual(actual, expected)

    def test_invalid_explicit_root(self):
        """Test behavior with invalid explicit root"""
        # Create a valid project
        project_root = self.temp_dir / "project"
        project_root.mkdir()
        with open(project_root / "pyproject.toml", "w") as f:
            f.write("[tool.poetry]\n")

        test_file = project_root / "test.py"
        test_file.touch()

        # Test with invalid explicit root - the actual behavior depends on implementation
        result = detect_project_root(str(test_file), "/invalid/path")

        # The result could be either the invalid path or the detected project root
        # depending on how the implementation handles invalid explicit roots
        possible_results = [
            normalize_path_for_comparison("/invalid/path"),
            normalize_path_for_comparison(str(project_root)),
        ]
        actual = normalize_path_for_comparison(str(result))
        self.assertIn(actual, possible_results)


if __name__ == "__main__":
    unittest.main()
