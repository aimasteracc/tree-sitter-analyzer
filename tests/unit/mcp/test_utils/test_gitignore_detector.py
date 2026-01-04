#!/usr/bin/env python3
"""
Unit tests for GitignoreDetector module.

Tests for gitignore pattern detection and interference analysis.
"""

from pathlib import Path
from unittest.mock import patch

from tree_sitter_analyzer.mcp.utils.gitignore_detector import (
    GitignoreDetector,
    get_default_detector,
)


class TestGitignoreDetectorInit:
    """Tests for GitignoreDetector initialization."""

    def test_initialization(self):
        """Test that GitignoreDetector initializes correctly."""
        detector = GitignoreDetector()
        assert detector.common_ignore_patterns is not None
        assert isinstance(detector.common_ignore_patterns, set)
        assert "build/*" in detector.common_ignore_patterns
        assert "node_modules/*" in detector.common_ignore_patterns


class TestShouldUseNoIgnore:
    """Tests for should_use_no_ignore method."""

    def test_non_root_directory_search(self):
        """Test that non-root directory search returns False."""
        detector = GitignoreDetector()
        result = detector.should_use_no_ignore(["src/"], "/project")
        assert result is False

    def test_no_project_root(self):
        """Test that missing project root returns False."""
        detector = GitignoreDetector()
        result = detector.should_use_no_ignore(["."], None)
        assert result is False

    def test_root_search_no_gitignore(self, tmp_path):
        """Test root search without .gitignore returns False."""
        detector = GitignoreDetector()
        result = detector.should_use_no_ignore(["."], str(tmp_path))
        assert result is False

    def test_root_search_with_interfering_gitignore(self, tmp_path):
        """Test root search with interfering .gitignore returns True."""
        # Create .gitignore with interfering pattern
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("src/*\nnode_modules/*\n")

        # Create src directory
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        detector = GitignoreDetector()
        result = detector.should_use_no_ignore(["."], str(tmp_path))
        assert result is True

    def test_root_search_with_non_interfering_gitignore(self, tmp_path):
        """Test root search with non-interfering .gitignore returns False."""
        # Create .gitignore without interfering patterns
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\n*.tmp\n")

        detector = GitignoreDetector()
        result = detector.should_use_no_ignore(["."], str(tmp_path))
        assert result is False

    def test_exception_handling(self, tmp_path):
        """Test that exceptions are handled gracefully."""
        detector = GitignoreDetector()
        # Use a path that might cause issues
        result = detector.should_use_no_ignore(
            ["."], "/nonexistent/path/that/does/not/exist"
        )
        assert result is False


class TestFindGitignoreFiles:
    """Tests for _find_gitignore_files method."""

    def test_find_gitignore_in_current_dir(self, tmp_path):
        """Test finding .gitignore in current directory."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\n")

        detector = GitignoreDetector()
        files = detector._find_gitignore_files(tmp_path)
        assert len(files) == 1
        assert gitignore in files

    def test_find_multiple_gitignores(self, tmp_path):
        """Test finding multiple .gitignore files."""
        # Create nested directories
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        # Create .gitignore in both
        root_gitignore = tmp_path / ".gitignore"
        root_gitignore.write_text("*.log\n")

        sub_gitignore = subdir / ".gitignore"
        sub_gitignore.write_text("*.tmp\n")

        detector = GitignoreDetector()
        files = detector._find_gitignore_files(subdir)
        assert len(files) >= 1
        assert sub_gitignore in files

    def test_temp_directory_only_current(self, tmp_path):
        """Test that temp directories only check current directory."""
        # Create temp directory
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()

        # Create .gitignore in parent
        parent_gitignore = tmp_path / ".gitignore"
        parent_gitignore.write_text("*.log\n")

        detector = GitignoreDetector()
        files = detector._find_gitignore_files(temp_dir)
        # Should not find parent .gitignore
        assert parent_gitignore not in files


class TestHasInterferingPatterns:
    """Tests for _has_interfering_patterns method."""

    def test_no_interfering_patterns(self, tmp_path):
        """Test with non-interfering patterns."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\n*.tmp\n")

        detector = GitignoreDetector()
        result = detector._has_interfering_patterns(gitignore, tmp_path, tmp_path)
        assert result is False

    def test_with_interfering_directory_pattern(self, tmp_path):
        """Test with interfering directory pattern."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("src/*\n")

        # Create src directory
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        detector = GitignoreDetector()
        result = detector._has_interfering_patterns(gitignore, tmp_path, tmp_path)
        assert result is True

    def test_with_source_directory_pattern(self, tmp_path):
        """Test with source directory pattern."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("code/\n")

        detector = GitignoreDetector()
        result = detector._has_interfering_patterns(gitignore, tmp_path, tmp_path)
        assert result is True

    def test_with_comments_and_empty_lines(self, tmp_path):
        """Test that comments and empty lines are ignored."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("# Comment\n\n*.log\n\n# Another comment\n")

        detector = GitignoreDetector()
        result = detector._has_interfering_patterns(gitignore, tmp_path, tmp_path)
        assert result is False

    def test_exception_handling(self, tmp_path):
        """Test exception handling when reading gitignore."""
        gitignore = tmp_path / ".gitignore"
        # Create invalid file
        gitignore.write_text("")

        # Mock read_file_safe to raise exception
        with patch(
            "tree_sitter_analyzer.encoding_utils.read_file_safe",
            side_effect=Exception("Read error"),
        ):
            detector = GitignoreDetector()
            result = detector._has_interfering_patterns(gitignore, tmp_path, tmp_path)
            assert result is False


class TestIsInterferingPattern:
    """Tests for _is_interfering_pattern method."""

    def test_directory_pattern_with_slash(self, tmp_path):
        """Test directory pattern with slash."""
        detector = GitignoreDetector()
        result = detector._is_interfering_pattern("src/*", tmp_path, tmp_path)
        assert result is True

    def test_source_directory_pattern(self, tmp_path):
        """Test source directory patterns."""
        detector = GitignoreDetector()
        result = detector._is_interfering_pattern("code/", tmp_path, tmp_path)
        assert result is True

    def test_non_source_directory_pattern(self, tmp_path):
        """Test non-source directory pattern."""
        # Create logs directory to make it exist
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        detector = GitignoreDetector()
        result = detector._is_interfering_pattern("logs/", tmp_path, tmp_path)
        # logs/ is not in source_dirs, but pattern ends with / so it's considered interfering
        # The logic is: if pattern.endswith("/*") or pattern.endswith("/")
        assert result is True

    def test_absolute_path_pattern(self, tmp_path):
        """Test absolute path pattern."""
        detector = GitignoreDetector()
        result = detector._is_interfering_pattern("/absolute/path", tmp_path, tmp_path)
        assert result is True

    def test_pattern_with_slash_in_middle(self, tmp_path):
        """Test pattern with slash in middle."""
        detector = GitignoreDetector()
        result = detector._is_interfering_pattern("src/test", tmp_path, tmp_path)
        assert result is True


class TestIsSearchDirAffectedByPattern:
    """Tests for _is_search_dir_affected_by_pattern method."""

    def test_search_dir_same_as_pattern_dir(self, tmp_path):
        """Test when search dir is same as pattern dir."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        detector = GitignoreDetector()
        result = detector._is_search_dir_affected_by_pattern(src_dir, src_dir, tmp_path)
        assert result is True

    def test_search_dir_subdirectory_of_pattern(self, tmp_path):
        """Test when search dir is subdirectory of pattern."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        nested_dir = src_dir / "nested"

        detector = GitignoreDetector()
        result = detector._is_search_dir_affected_by_pattern(
            nested_dir, src_dir, tmp_path
        )
        assert result is True

    def test_search_dir_not_affected(self, tmp_path):
        """Test when search dir is not affected."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        other_dir = tmp_path / "other"
        other_dir.mkdir()

        detector = GitignoreDetector()
        result = detector._is_search_dir_affected_by_pattern(
            other_dir, src_dir, tmp_path
        )
        assert result is False

    def test_nonexistent_paths(self, tmp_path):
        """Test with nonexistent paths."""
        nonexistent = tmp_path / "nonexistent"

        detector = GitignoreDetector()
        result = detector._is_search_dir_affected_by_pattern(
            nonexistent, nonexistent, tmp_path
        )
        assert result is True


class TestDirectoryHasSearchableFiles:
    """Tests for _directory_has_searchable_files method."""

    def test_directory_with_searchable_files(self, tmp_path):
        """Test directory with searchable files."""
        # Create files with searchable extensions
        (tmp_path / "test.py").write_text("print('hello')")
        (tmp_path / "test.js").write_text("console.log('hello')")

        detector = GitignoreDetector()
        result = detector._directory_has_searchable_files(tmp_path)
        assert result is True

    def test_directory_without_searchable_files(self, tmp_path):
        """Test directory without searchable files."""
        # Create files with non-searchable extensions
        (tmp_path / "test.txt").write_text("hello")
        (tmp_path / "test.log").write_text("log")

        detector = GitignoreDetector()
        result = detector._directory_has_searchable_files(tmp_path)
        assert result is False

    def test_empty_directory(self, tmp_path):
        """Test empty directory."""
        detector = GitignoreDetector()
        result = detector._directory_has_searchable_files(tmp_path)
        assert result is False

    def test_exception_handling(self, tmp_path):
        """Test exception handling."""
        detector = GitignoreDetector()
        # Use a path that might cause issues
        result = detector._directory_has_searchable_files(Path("/nonexistent/path"))
        # Should return False on exception (can't scan nonexistent path)
        assert result is False


class TestGetDetectionInfo:
    """Tests for get_detection_info method."""

    def test_no_interference_detected(self, tmp_path):
        """Test when no interference is detected."""
        detector = GitignoreDetector()
        info = detector.get_detection_info(["."], str(tmp_path))

        assert info["should_use_no_ignore"] is False
        assert info["detected_gitignore_files"] == []
        assert info["interfering_patterns"] == []
        assert "No interference detected" in info["reason"]

    def test_interference_detected(self, tmp_path):
        """Test when interference is detected."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("src/*\n")

        src_dir = tmp_path / "src"
        src_dir.mkdir()

        detector = GitignoreDetector()
        info = detector.get_detection_info(["."], str(tmp_path))

        assert info["should_use_no_ignore"] is True
        assert len(info["detected_gitignore_files"]) > 0
        assert len(info["interfering_patterns"]) > 0
        assert "interfering patterns" in info["reason"].lower()

    def test_non_root_search(self, tmp_path):
        """Test with non-root search."""
        detector = GitignoreDetector()
        info = detector.get_detection_info(["src/"], str(tmp_path))

        assert info["should_use_no_ignore"] is False
        assert "Not a root directory search" in info["reason"]

    def test_no_project_root(self):
        """Test with no project root."""
        detector = GitignoreDetector()
        info = detector.get_detection_info(["."], None)

        assert info["should_use_no_ignore"] is False
        assert "No project root specified" in info["reason"]

    def test_nonexistent_project_root(self):
        """Test with nonexistent project root."""
        detector = GitignoreDetector()
        info = detector.get_detection_info(["."], "/nonexistent/path")

        assert "Error during detection" in info["reason"]


class TestGetInterferingPatterns:
    """Tests for _get_interfering_patterns method."""

    def test_no_interfering_patterns(self, tmp_path):
        """Test with no interfering patterns."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\n*.tmp\n")

        detector = GitignoreDetector()
        patterns = detector._get_interfering_patterns(gitignore, tmp_path, tmp_path)
        assert len(patterns) == 0

    def test_with_interfering_patterns(self, tmp_path):
        """Test with interfering patterns."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("src/*\ncode/\nbuild/*\n")

        detector = GitignoreDetector()
        patterns = detector._get_interfering_patterns(gitignore, tmp_path, tmp_path)
        assert len(patterns) > 0

    def test_filters_comments_and_empty_lines(self, tmp_path):
        """Test that comments and empty lines are filtered."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("# Comment\n\n*.log\n\n# Another\nsrc/*\n")

        detector = GitignoreDetector()
        patterns = detector._get_interfering_patterns(gitignore, tmp_path, tmp_path)
        # Should only include src/*, not *.log or comments
        assert "src/*" in patterns
        assert "*.log" not in patterns


class TestGetDefaultDetector:
    """Tests for get_default_detector function."""

    def test_returns_gitignore_detector_instance(self):
        """Test that function returns GitignoreDetector instance."""
        detector = get_default_detector()
        assert isinstance(detector, GitignoreDetector)

    def test_returns_same_instance(self):
        """Test that function returns singleton instance."""
        detector1 = get_default_detector()
        detector2 = get_default_detector()
        assert detector1 is detector2


class TestIntegration:
    """Integration tests for GitignoreDetector."""

    def test_full_detection_workflow(self, tmp_path):
        """Test complete detection workflow."""
        # Create project structure
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("""
# Build outputs
build/
dist/

# Dependencies
node_modules/

# Source directories
src/
lib/
""")

        # Create directories
        (tmp_path / "src").mkdir()
        (tmp_path / "lib").mkdir()

        detector = GitignoreDetector()

        # Test should_use_no_ignore
        should_ignore = detector.should_use_no_ignore(["."], str(tmp_path))
        assert should_ignore is True

        # Test get_detection_info
        info = detector.get_detection_info(["."], str(tmp_path))
        assert info["should_use_no_ignore"] is True
        assert len(info["detected_gitignore_files"]) > 0
        assert len(info["interfering_patterns"]) > 0

    def test_real_world_scenario(self, tmp_path):
        """Test real-world scenario with typical .gitignore."""
        # Create typical .gitignore
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("""
# Python
__pycache__/
*.py[cod]
*$py.class

# Node
node_modules/
npm-debug.log

# Build
dist/
build/
""")

        # Create some directories
        (tmp_path / "src").mkdir()
        (tmp_path / "dist").mkdir()

        detector = GitignoreDetector()
        result = detector.should_use_no_ignore(["."], str(tmp_path))

        # Should detect interference from src/ being ignored
        assert result is True
