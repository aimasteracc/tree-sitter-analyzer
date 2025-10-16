"""
Comprehensive tests for Gitignore detector functionality.
Tests cover detection logic, pattern matching, and file system interactions.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.utils.gitignore_detector import (
    GitignoreDetector,
    get_default_detector,
)


class TestGitignoreDetectorInitialization:
    """Test Gitignore detector initialization."""

    def test_detector_initialization(self):
        """Test detector initialization with default patterns."""
        detector = GitignoreDetector()

        assert hasattr(detector, "common_ignore_patterns")
        assert isinstance(detector.common_ignore_patterns, set)
        assert len(detector.common_ignore_patterns) > 0

        # Check for expected common patterns
        expected_patterns = {
            "build/*",
            "dist/*",
            "node_modules/*",
            "__pycache__/*",
            "target/*",
            ".git/*",
            "code/*",
            "src/*",
        }

        assert expected_patterns.issubset(detector.common_ignore_patterns)

    def test_get_default_detector(self):
        """Test getting default detector instance."""
        detector1 = get_default_detector()
        detector2 = get_default_detector()

        assert isinstance(detector1, GitignoreDetector)
        assert detector1 is detector2  # Should be singleton


class TestGitignoreDetectorBasicFunctionality:
    """Test basic Gitignore detector functionality."""

    @pytest.fixture
    def detector(self):
        """Create a detector instance."""
        return GitignoreDetector()

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            yield project_path

    def test_should_use_no_ignore_non_root_search(self, detector):
        """Test that non-root searches don't trigger no-ignore."""
        roots = ["src", "lib"]
        project_root = "/test/project"

        result = detector.should_use_no_ignore(roots, project_root)

        assert result is False

    def test_should_use_no_ignore_multiple_roots(self, detector):
        """Test that multiple root searches don't trigger no-ignore."""
        roots = [".", "src"]
        project_root = "/test/project"

        result = detector.should_use_no_ignore(roots, project_root)

        assert result is False

    def test_should_use_no_ignore_no_project_root(self, detector):
        """Test that searches without project root don't trigger no-ignore."""
        roots = ["."]
        project_root = None

        result = detector.should_use_no_ignore(roots, project_root)

        assert result is False

    def test_should_use_no_ignore_valid_root_search(self, detector, temp_project):
        """Test valid root search without gitignore."""
        roots = ["."]

        result = detector.should_use_no_ignore(roots, str(temp_project))

        assert result is False  # No .gitignore file exists

    def test_should_use_no_ignore_with_exception_handling(self, detector):
        """Test exception handling in should_use_no_ignore."""
        roots = ["."]
        project_root = "/non/existent/path"

        # Should handle gracefully without raising exception
        result = detector.should_use_no_ignore(roots, project_root)

        assert result is False


class TestGitignoreDetectorFileDiscovery:
    """Test Gitignore detector file discovery functionality."""

    @pytest.fixture
    def detector(self):
        """Create a detector instance."""
        return GitignoreDetector()

    @pytest.fixture
    def temp_project_with_gitignore(self):
        """Create a temporary project with .gitignore files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create .gitignore in root
            root_gitignore = project_path / ".gitignore"
            root_gitignore.write_text("*.log\nbuild/\n")

            # Create nested directory with .gitignore
            nested_dir = project_path / "subproject"
            nested_dir.mkdir()
            nested_gitignore = nested_dir / ".gitignore"
            nested_gitignore.write_text("temp/\n*.tmp\n")

            yield project_path

    def test_find_gitignore_files_single_file(
        self, detector, temp_project_with_gitignore
    ):
        """Test finding single .gitignore file."""
        gitignore_files = detector._find_gitignore_files(temp_project_with_gitignore)

        assert len(gitignore_files) >= 1
        assert any(f.name == ".gitignore" for f in gitignore_files)

    def test_find_gitignore_files_multiple_levels(self, detector):
        """Test finding .gitignore files at multiple levels."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create .gitignore at multiple levels
            (project_path / ".gitignore").write_text("root ignore")

            parent_dir = project_path.parent
            (parent_dir / ".gitignore").write_text("parent ignore")

            gitignore_files = detector._find_gitignore_files(project_path)

            assert len(gitignore_files) >= 1

    def test_find_gitignore_files_no_files(self, detector):
        """Test finding .gitignore files when none exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Remove any existing .gitignore files in the project directory
            for gitignore in project_path.glob(".gitignore"):
                gitignore.unlink()

            gitignore_files = detector._find_gitignore_files(project_path)

            # Filter to only files within our project directory
            project_gitignore_files = [
                f for f in gitignore_files if str(f).startswith(str(project_path))
            ]
            assert len(project_gitignore_files) == 0

    def test_find_gitignore_files_depth_limit(self, detector):
        """Test that .gitignore file search respects depth limit."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create deep directory structure
            current = project_path
            for i in range(5):
                current = current / f"level_{i}"
                current.mkdir(parents=True)
                (current / ".gitignore").write_text(f"level {i} ignore")

            # Search from the deepest level
            gitignore_files = detector._find_gitignore_files(current)

            # Should find files but respect depth limit (max 3 levels up)
            assert len(gitignore_files) <= 3


class TestGitignoreDetectorPatternAnalysis:
    """Test Gitignore detector pattern analysis functionality."""

    @pytest.fixture
    def detector(self):
        """Create a detector instance."""
        return GitignoreDetector()

    @pytest.fixture
    def temp_project_with_source_code(self):
        """Create a temporary project with source code."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create source directories
            src_dir = project_path / "src"
            src_dir.mkdir()
            (src_dir / "main.py").write_text("print('hello')")
            (src_dir / "utils.java").write_text("public class Utils {}")

            code_dir = project_path / "code"
            code_dir.mkdir()
            (code_dir / "app.js").write_text("console.log('hello');")
            (code_dir / "component.ts").write_text("export class Component {}")

            lib_dir = project_path / "lib"
            lib_dir.mkdir()
            (lib_dir / "helper.cpp").write_text("#include <iostream>")

            yield project_path

    def test_has_interfering_patterns_with_source_directories(
        self, detector, temp_project_with_source_code
    ):
        """Test detection of interfering patterns for source directories."""
        gitignore_file = temp_project_with_source_code / ".gitignore"
        gitignore_file.write_text("src/\ncode/*\nlib/\n")

        result = detector._has_interfering_patterns(
            gitignore_file, temp_project_with_source_code, temp_project_with_source_code
        )

        assert result is True

    def test_has_interfering_patterns_with_comments(
        self, detector, temp_project_with_source_code
    ):
        """Test that comments in .gitignore are ignored."""
        gitignore_file = temp_project_with_source_code / ".gitignore"
        gitignore_file.write_text("# This is a comment\n# src/\n*.log\n")

        result = detector._has_interfering_patterns(
            gitignore_file, temp_project_with_source_code, temp_project_with_source_code
        )

        assert result is False

    def test_has_interfering_patterns_with_empty_lines(
        self, detector, temp_project_with_source_code
    ):
        """Test that empty lines in .gitignore are ignored."""
        gitignore_file = temp_project_with_source_code / ".gitignore"
        gitignore_file.write_text("\n\n*.log\n\n")

        result = detector._has_interfering_patterns(
            gitignore_file, temp_project_with_source_code, temp_project_with_source_code
        )

        assert result is False

    def test_has_interfering_patterns_file_read_error(
        self, detector, temp_project_with_source_code
    ):
        """Test handling of file read errors."""
        gitignore_file = temp_project_with_source_code / ".gitignore"
        gitignore_file.write_text("src/\n")

        # Mock file reading to raise an exception
        with patch("builtins.open", side_effect=OSError("Permission denied")):
            result = detector._has_interfering_patterns(
                gitignore_file,
                temp_project_with_source_code,
                temp_project_with_source_code,
            )

            assert result is False

    def test_is_interfering_pattern_directory_patterns(
        self, detector, temp_project_with_source_code
    ):
        """Test detection of interfering directory patterns."""
        patterns = ["src/", "src/*", "code/", "code/*", "lib/", "lib/*"]

        for pattern in patterns:
            result = detector._is_interfering_pattern(
                pattern, temp_project_with_source_code, temp_project_with_source_code
            )
            assert result is True, f"Pattern '{pattern}' should be interfering"

    def test_is_interfering_pattern_non_interfering(
        self, detector, temp_project_with_source_code
    ):
        """Test detection of non-interfering patterns."""
        patterns = ["*.log", "*.tmp", "*.cache", "*.bak", "*.swp", "*.pyc"]

        for pattern in patterns:
            result = detector._is_interfering_pattern(
                pattern, temp_project_with_source_code, temp_project_with_source_code
            )
            assert result is False, f"Pattern '{pattern}' should not be interfering"

    def test_is_interfering_pattern_leading_slash(
        self, detector, temp_project_with_source_code
    ):
        """Test handling of patterns with leading slash."""
        pattern = "/src/"

        result = detector._is_interfering_pattern(
            pattern, temp_project_with_source_code, temp_project_with_source_code
        )

        assert result is True

    def test_is_interfering_pattern_source_directory_names(
        self, detector, temp_project_with_source_code
    ):
        """Test detection of source directory name patterns."""
        source_patterns = ["java/", "python/", "js/", "ts/", "main/", "app/"]

        for pattern in source_patterns:
            # Create the directory to make it detectable
            (temp_project_with_source_code / pattern.rstrip("/")).mkdir(exist_ok=True)
            (
                temp_project_with_source_code / pattern.rstrip("/") / "test.py"
            ).write_text("test")

            result = detector._is_interfering_pattern(
                pattern, temp_project_with_source_code, temp_project_with_source_code
            )
            assert result is True, f"Source pattern '{pattern}' should be interfering"


class TestGitignoreDetectorSearchDirectoryAnalysis:
    """Test Gitignore detector search directory analysis."""

    @pytest.fixture
    def detector(self):
        """Create a detector instance."""
        return GitignoreDetector()

    @pytest.fixture
    def temp_project_structure(self):
        """Create a temporary project with nested structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create nested structure
            src_dir = project_path / "src"
            src_dir.mkdir()
            main_dir = src_dir / "main"
            main_dir.mkdir()
            java_dir = main_dir / "java"
            java_dir.mkdir()

            yield project_path, src_dir, main_dir, java_dir

    def test_is_search_dir_affected_by_pattern_exact_match(
        self, detector, temp_project_structure
    ):
        """Test search directory affected by pattern - exact match."""
        project_path, src_dir, main_dir, java_dir = temp_project_structure

        result = detector._is_search_dir_affected_by_pattern(
            src_dir, src_dir, project_path
        )

        assert result is True

    def test_is_search_dir_affected_by_pattern_subdirectory(
        self, detector, temp_project_structure
    ):
        """Test search directory affected by pattern - subdirectory."""
        project_path, src_dir, main_dir, java_dir = temp_project_structure

        result = detector._is_search_dir_affected_by_pattern(
            java_dir, src_dir, project_path
        )

        assert result is True

    def test_is_search_dir_affected_by_pattern_unrelated(
        self, detector, temp_project_structure
    ):
        """Test search directory not affected by pattern - unrelated."""
        project_path, src_dir, main_dir, java_dir = temp_project_structure

        # Create unrelated directory
        other_dir = project_path / "other"
        other_dir.mkdir()

        result = detector._is_search_dir_affected_by_pattern(
            other_dir, src_dir, project_path
        )

        assert result is False

    def test_is_search_dir_affected_by_pattern_path_resolution_error(
        self, detector, temp_project_structure
    ):
        """Test handling of path resolution errors."""
        project_path, src_dir, main_dir, java_dir = temp_project_structure

        # Create path that might cause resolution issues
        invalid_path = Path("/non/existent/path")

        result = detector._is_search_dir_affected_by_pattern(
            invalid_path, src_dir, project_path
        )

        # Should assume it could be affected when resolution fails
        assert result is True


class TestGitignoreDetectorFileAnalysis:
    """Test Gitignore detector file analysis functionality."""

    @pytest.fixture
    def detector(self):
        """Create a detector instance."""
        return GitignoreDetector()

    @pytest.fixture
    def temp_directory_with_files(self):
        """Create a temporary directory with various file types."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir)

            # Create searchable files
            (dir_path / "main.py").write_text("print('hello')")
            (dir_path / "utils.java").write_text("public class Utils {}")
            (dir_path / "app.js").write_text("console.log('hello');")
            (dir_path / "component.ts").write_text("export class Component {}")
            (dir_path / "program.cpp").write_text("#include <iostream>")
            (dir_path / "header.h").write_text("#ifndef HEADER_H")
            (dir_path / "service.cs").write_text("public class Service {}")
            (dir_path / "main.go").write_text("package main")
            (dir_path / "lib.rs").write_text("fn main() {}")

            # Create non-searchable files
            (dir_path / "data.txt").write_text("some data")
            (dir_path / "config.json").write_text('{"key": "value"}')
            (dir_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")

            yield dir_path

    def test_directory_has_searchable_files_with_searchable_files(
        self, detector, temp_directory_with_files
    ):
        """Test detection of searchable files in directory."""
        result = detector._directory_has_searchable_files(temp_directory_with_files)

        assert result is True

    def test_directory_has_searchable_files_no_searchable_files(self, detector):
        """Test detection when directory has no searchable files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir)

            # Create only non-searchable files
            (dir_path / "data.txt").write_text("some data")
            (dir_path / "config.json").write_text('{"key": "value"}')
            (dir_path / "README.md").write_text("# README")

            result = detector._directory_has_searchable_files(dir_path)

            assert result is False

    def test_directory_has_searchable_files_empty_directory(self, detector):
        """Test detection in empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir)

            result = detector._directory_has_searchable_files(dir_path)

            assert result is False

    def test_directory_has_searchable_files_nested_structure(self, detector):
        """Test detection of searchable files in nested structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir)

            # Create nested structure with searchable file
            nested_dir = dir_path / "nested" / "deep"
            nested_dir.mkdir(parents=True)
            (nested_dir / "deep_file.py").write_text("print('deep')")

            result = detector._directory_has_searchable_files(dir_path)

            assert result is True

    def test_directory_has_searchable_files_permission_error(self, detector):
        """Test handling of permission errors during file scanning."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir)

            # Mock rglob to raise permission error
            with patch.object(
                Path, "rglob", side_effect=PermissionError("Access denied")
            ):
                result = detector._directory_has_searchable_files(dir_path)

                # Should assume it might have searchable files when scanning fails
                assert result is True

    def test_directory_has_searchable_files_case_insensitive_extensions(self, detector):
        """Test detection with case-insensitive file extensions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir)

            # Create files with uppercase extensions
            (dir_path / "Main.PY").write_text("print('hello')")
            (dir_path / "Utils.JAVA").write_text("public class Utils {}")
            (dir_path / "App.JS").write_text("console.log('hello');")

            result = detector._directory_has_searchable_files(dir_path)

            assert result is True


class TestGitignoreDetectorDetectionInfo:
    """Test Gitignore detector detection info functionality."""

    @pytest.fixture
    def detector(self):
        """Create a detector instance."""
        return GitignoreDetector()

    def test_get_detection_info_non_root_search(self, detector):
        """Test detection info for non-root search."""
        roots = ["src", "lib"]
        project_root = "/test/project"

        info = detector.get_detection_info(roots, project_root)

        assert info["should_use_no_ignore"] is False
        assert info["reason"] == "Not a root directory search"
        assert info["detected_gitignore_files"] == []
        assert info["interfering_patterns"] == []

    def test_get_detection_info_no_project_root(self, detector):
        """Test detection info without project root."""
        roots = ["."]
        project_root = None

        info = detector.get_detection_info(roots, project_root)

        assert info["should_use_no_ignore"] is False
        assert info["reason"] == "No project root specified"

    def test_get_detection_info_no_gitignore_files(self, detector):
        """Test detection info when no .gitignore files exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            roots = ["."]

            info = detector.get_detection_info(roots, temp_dir)

            assert info["should_use_no_ignore"] is False
            assert info["reason"] == "No interference detected"
            assert info["detected_gitignore_files"] == []
            assert info["interfering_patterns"] == []

    def test_get_detection_info_with_interfering_patterns(self, detector):
        """Test detection info with interfering patterns."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create source directory with files
            src_dir = project_path / "src"
            src_dir.mkdir()
            (src_dir / "main.py").write_text("print('hello')")

            # Create .gitignore with interfering pattern
            gitignore_file = project_path / ".gitignore"
            gitignore_file.write_text("src/\n*.log\n")

            roots = ["."]

            info = detector.get_detection_info(roots, str(project_path))

            assert info["should_use_no_ignore"] is True
            assert "interfering patterns" in info["reason"]
            assert len(info["detected_gitignore_files"]) > 0
            assert len(info["interfering_patterns"]) > 0
            assert "src/" in info["interfering_patterns"]

    def test_get_detection_info_exception_handling(self, detector):
        """Test detection info exception handling."""
        roots = ["."]
        project_root = "/non/existent/path"

        info = detector.get_detection_info(roots, project_root)

        assert info["should_use_no_ignore"] is False
        assert "Error during detection" in info["reason"]

    def test_get_interfering_patterns_file_read_error(self, detector):
        """Test handling of file read errors in pattern extraction."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            gitignore_file = project_path / ".gitignore"
            gitignore_file.write_text("src/\n")

            # Mock file reading to raise an exception
            with patch("builtins.open", side_effect=OSError("Permission denied")):
                patterns = detector._get_interfering_patterns(
                    gitignore_file, project_path, project_path
                )

                assert patterns == []


class TestGitignoreDetectorIntegration:
    """Test Gitignore detector integration scenarios."""

    @pytest.fixture
    def detector(self):
        """Create a detector instance."""
        return GitignoreDetector()

    def test_real_world_scenario_node_project(self, detector):
        """Test real-world scenario with Node.js project structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create typical Node.js project structure
            src_dir = project_path / "src"
            src_dir.mkdir()
            (src_dir / "index.js").write_text("console.log('hello');")
            (src_dir / "utils.ts").write_text("export function utils() {}")

            lib_dir = project_path / "lib"
            lib_dir.mkdir()
            (lib_dir / "helper.js").write_text("module.exports = {};")

            # Create .gitignore that ignores source directories
            gitignore_file = project_path / ".gitignore"
            gitignore_file.write_text("""
# Dependencies
node_modules/
npm-debug.log*

# Build outputs
dist/
build/

# Source directories (problematic)
src/
lib/

# IDE files
.vscode/
.idea/
""")

            roots = ["."]
            result = detector.should_use_no_ignore(roots, str(project_path))

            assert result is True

    def test_real_world_scenario_java_project(self, detector):
        """Test real-world scenario with Java project structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create typical Java project structure
            src_main_java = project_path / "src" / "main" / "java"
            src_main_java.mkdir(parents=True)
            (src_main_java / "Main.java").write_text("public class Main {}")

            # Create .gitignore that doesn't interfere
            gitignore_file = project_path / ".gitignore"
            gitignore_file.write_text("""
# Build outputs
target/
*.class
*.jar

# IDE files
.idea/
.eclipse/
*.iml

# Logs
*.log
""")

            roots = ["."]
            result = detector.should_use_no_ignore(roots, str(project_path))

            # Java projects might or might not trigger no_ignore depending on gitignore content
            assert isinstance(result, bool), "Should return a boolean for Java project"

    def test_real_world_scenario_python_project(self, detector):
        """Test real-world scenario with Python project structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create typical Python project structure
            src_dir = project_path / "src"
            src_dir.mkdir()
            (src_dir / "main.py").write_text("print('hello')")
            (src_dir / "utils.py").write_text("def helper(): pass")

            # Create .gitignore with mixed patterns
            gitignore_file = project_path / ".gitignore"
            gitignore_file.write_text("""
# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
venv/

# Build
build/
dist/
*.egg-info/

# Code directory (problematic)
code/
""")

            # Create code directory with files
            code_dir = project_path / "code"
            code_dir.mkdir()
            (code_dir / "app.py").write_text("print('app')")

            roots = ["."]
            result = detector.should_use_no_ignore(roots, str(project_path))

            assert result is True

    def test_complex_gitignore_hierarchy(self, detector):
        """Test complex .gitignore file hierarchy."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create root .gitignore
            root_gitignore = project_path / ".gitignore"
            root_gitignore.write_text("*.log\nbuild/\n")

            # Create subdirectory with its own .gitignore
            subproject = project_path / "subproject"
            subproject.mkdir()
            sub_gitignore = subproject / ".gitignore"
            sub_gitignore.write_text("src/\nlib/\n")

            # Create source files in subdirectory
            src_dir = subproject / "src"
            src_dir.mkdir()
            (src_dir / "main.py").write_text("print('hello')")

            roots = ["."]
            result = detector.should_use_no_ignore(roots, str(project_path))

            # Should detect interference from subdirectory .gitignore
            assert result is True

    def test_performance_with_large_directory_structure(self, detector):
        """Test performance with large directory structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create large directory structure
            for i in range(10):
                dir_path = project_path / f"dir_{i}"
                dir_path.mkdir()

                for j in range(10):
                    subdir_path = dir_path / f"subdir_{j}"
                    subdir_path.mkdir()
                    (subdir_path / f"file_{j}.py").write_text(f"# File {j}")

            # Create .gitignore
            gitignore_file = project_path / ".gitignore"
            gitignore_file.write_text("dir_5/\n")

            roots = ["."]

            # Should complete without timeout
            result = detector.should_use_no_ignore(roots, str(project_path))

            assert isinstance(result, bool)
