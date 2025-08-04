#!/usr/bin/env python3
"""
Tests for Project Root Detection

Tests the intelligent project root detection functionality.
"""

import os
import tempfile
import pytest
from pathlib import Path

from tree_sitter_analyzer.project_detector import (
    ProjectRootDetector,
    detect_project_root,
    PROJECT_MARKERS
)


class TestProjectRootDetector:
    """Test project root detection functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.detector = ProjectRootDetector()

    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_detect_from_git_repo(self):
        """Test detection from .git directory."""
        # Create a mock git repository structure
        project_root = os.path.join(self.temp_dir, "my_project")
        os.makedirs(project_root)
        os.makedirs(os.path.join(project_root, ".git"))
        
        # Create a nested file
        src_dir = os.path.join(project_root, "src")
        os.makedirs(src_dir)
        test_file = os.path.join(src_dir, "main.py")
        with open(test_file, "w") as f:
            f.write("print('hello')")
        
        # Test detection
        detected_root = self.detector.detect_from_file(test_file)
        assert detected_root == project_root

    def test_detect_from_python_project(self):
        """Test detection from Python project markers."""
        # Create a Python project structure
        project_root = os.path.join(self.temp_dir, "python_project")
        os.makedirs(project_root)
        
        # Create pyproject.toml
        with open(os.path.join(project_root, "pyproject.toml"), "w") as f:
            f.write("[tool.poetry]\nname = 'test'\n")
        
        # Create nested source file
        src_dir = os.path.join(project_root, "src", "mypackage")
        os.makedirs(src_dir)
        test_file = os.path.join(src_dir, "module.py")
        with open(test_file, "w") as f:
            f.write("def hello(): pass")
        
        # Test detection
        detected_root = self.detector.detect_from_file(test_file)
        assert detected_root == project_root

    def test_detect_from_javascript_project(self):
        """Test detection from JavaScript project markers."""
        # Create a JavaScript project structure
        project_root = os.path.join(self.temp_dir, "js_project")
        os.makedirs(project_root)
        
        # Create package.json
        with open(os.path.join(project_root, "package.json"), "w") as f:
            f.write('{"name": "test", "version": "1.0.0"}')
        
        # Create nested source file
        src_dir = os.path.join(project_root, "src")
        os.makedirs(src_dir)
        test_file = os.path.join(src_dir, "index.js")
        with open(test_file, "w") as f:
            f.write("console.log('hello');")
        
        # Test detection
        detected_root = self.detector.detect_from_file(test_file)
        assert detected_root == project_root

    def test_detect_from_java_project(self):
        """Test detection from Java project markers."""
        # Create a Java project structure
        project_root = os.path.join(self.temp_dir, "java_project")
        os.makedirs(project_root)
        
        # Create pom.xml
        with open(os.path.join(project_root, "pom.xml"), "w") as f:
            f.write('<?xml version="1.0"?><project></project>')
        
        # Create nested source file
        src_dir = os.path.join(project_root, "src", "main", "java")
        os.makedirs(src_dir)
        test_file = os.path.join(src_dir, "Main.java")
        with open(test_file, "w") as f:
            f.write("public class Main {}")
        
        # Test detection
        detected_root = self.detector.detect_from_file(test_file)
        assert detected_root == project_root

    def test_multiple_markers_priority(self):
        """Test that higher priority markers are preferred."""
        # Create a project with multiple markers
        project_root = os.path.join(self.temp_dir, "multi_project")
        os.makedirs(project_root)
        
        # Create both .git and README.md (git should have higher priority)
        os.makedirs(os.path.join(project_root, ".git"))
        with open(os.path.join(project_root, "README.md"), "w") as f:
            f.write("# Test Project")
        
        # Create a nested file
        test_file = os.path.join(project_root, "src", "test.py")
        os.makedirs(os.path.dirname(test_file))
        with open(test_file, "w") as f:
            f.write("pass")
        
        # Test detection - should find the project root with .git
        detected_root = self.detector.detect_from_file(test_file)
        assert detected_root == project_root

    def test_no_markers_found(self):
        """Test behavior when no project markers are found."""
        # Create a simple directory structure without markers
        test_dir = os.path.join(self.temp_dir, "no_markers")
        os.makedirs(test_dir)
        test_file = os.path.join(test_dir, "isolated.py")
        with open(test_file, "w") as f:
            f.write("pass")
        
        # Test detection - should return None
        detected_root = self.detector.detect_from_file(test_file)
        assert detected_root is None

    def test_max_depth_limit(self):
        """Test that detection respects max depth limit."""
        # Create a deep directory structure
        current_dir = self.temp_dir
        for i in range(15):  # Deeper than default max_depth
            current_dir = os.path.join(current_dir, f"level_{i}")
            os.makedirs(current_dir)
        
        # Create a marker at the top level
        with open(os.path.join(self.temp_dir, "pyproject.toml"), "w") as f:
            f.write("[tool.poetry]\n")
        
        # Create a test file at the deep level
        test_file = os.path.join(current_dir, "deep.py")
        with open(test_file, "w") as f:
            f.write("pass")
        
        # Test with default max_depth (should not find the marker)
        detected_root = self.detector.detect_from_file(test_file)
        assert detected_root is None
        
        # Test with increased max_depth (should find the marker)
        deep_detector = ProjectRootDetector(max_depth=20)
        detected_root = deep_detector.detect_from_file(test_file)
        assert detected_root == self.temp_dir

    def test_fallback_behavior(self):
        """Test fallback behavior when detection fails."""
        test_file = os.path.join(self.temp_dir, "test.py")
        with open(test_file, "w") as f:
            f.write("pass")
        
        # Test fallback for existing file
        fallback = self.detector.get_fallback_root(test_file)
        assert fallback == self.temp_dir
        
        # Test fallback for non-existing file
        fallback = self.detector.get_fallback_root("/non/existing/file.py")
        assert fallback == os.getcwd()


class TestUnifiedDetectProjectRoot:
    """Test the unified detect_project_root function."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_explicit_root_priority(self):
        """Test that explicit root has highest priority."""
        # Create a project structure
        project_root = os.path.join(self.temp_dir, "project")
        os.makedirs(project_root)
        os.makedirs(os.path.join(project_root, ".git"))
        
        test_file = os.path.join(project_root, "test.py")
        with open(test_file, "w") as f:
            f.write("pass")
        
        # Specify a different explicit root
        explicit_root = os.path.join(self.temp_dir, "explicit")
        os.makedirs(explicit_root)
        
        # Test that explicit root is used
        result = detect_project_root(test_file, explicit_root)
        assert result == os.path.abspath(explicit_root)

    def test_auto_detection_from_file(self):
        """Test auto-detection from file path."""
        # Create a project structure
        project_root = os.path.join(self.temp_dir, "project")
        os.makedirs(project_root)
        with open(os.path.join(project_root, "pyproject.toml"), "w") as f:
            f.write("[tool.poetry]\n")
        
        test_file = os.path.join(project_root, "src", "test.py")
        os.makedirs(os.path.dirname(test_file))
        with open(test_file, "w") as f:
            f.write("pass")
        
        # Test auto-detection
        result = detect_project_root(test_file)
        assert result == project_root

    def test_fallback_to_file_directory(self):
        """Test fallback to file directory when detection fails."""
        # Create a file without project markers in a deep isolated directory
        # to avoid detecting the actual project root
        isolated_base = os.path.join(self.temp_dir, "very", "deep", "isolated", "directory")
        os.makedirs(isolated_base)
        test_file = os.path.join(isolated_base, "test.py")
        with open(test_file, "w") as f:
            f.write("pass")

        # Use explicit detector with limited depth to avoid finding project root
        detector = ProjectRootDetector(max_depth=2)
        result = detector.detect_from_file(test_file)

        # Should return None when no markers found within depth limit
        assert result is None

        # Test fallback behavior
        fallback = detector.get_fallback_root(test_file)
        assert fallback == isolated_base

    def test_invalid_explicit_root(self):
        """Test behavior with invalid explicit root."""
        # Create a valid project
        project_root = os.path.join(self.temp_dir, "project")
        os.makedirs(project_root)
        with open(os.path.join(project_root, "pyproject.toml"), "w") as f:
            f.write("[tool.poetry]\n")
        
        test_file = os.path.join(project_root, "test.py")
        with open(test_file, "w") as f:
            f.write("pass")
        
        # Test with invalid explicit root - should fall back to auto-detection
        result = detect_project_root(test_file, "/non/existing/path")
        assert result == project_root


if __name__ == "__main__":
    pytest.main([__file__])
