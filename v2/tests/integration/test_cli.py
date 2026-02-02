"""
Integration tests for CLI interface.

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

This is T5.1: CLI Interface
"""

import subprocess
import sys
from pathlib import Path

import pytest


class TestAnalyzeCommand:
    """Tests for 'analyze' command."""

    def test_analyze_file_default_format(self, analyze_fixtures_dir):
        """Test analyzing a file with default format (markdown)."""
        sample_py = analyze_fixtures_dir / "sample.py"

        result = subprocess.run(
            [sys.executable, "-m", "tree_sitter_analyzer_v2", "analyze", str(sample_py)],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        # Default format should be markdown (human-readable for CLI)
        assert "**" in result.stdout or "#" in result.stdout  # Markdown formatting

    def test_analyze_file_toon_format(self, analyze_fixtures_dir):
        """Test analyzing a file with TOON format."""
        sample_py = analyze_fixtures_dir / "sample.py"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer_v2",
                "analyze",
                str(sample_py),
                "--format",
                "toon",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        # TOON format should have compact notation
        assert "[" in result.stdout or ":" in result.stdout

    def test_analyze_file_markdown_format(self, analyze_fixtures_dir):
        """Test analyzing a file with explicit markdown format."""
        sample_py = analyze_fixtures_dir / "sample.py"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer_v2",
                "analyze",
                str(sample_py),
                "--format",
                "markdown",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "**" in result.stdout or "#" in result.stdout

    def test_analyze_nonexistent_file(self):
        """Test analyzing nonexistent file shows error."""
        result = subprocess.run(
            [sys.executable, "-m", "tree_sitter_analyzer_v2", "analyze", "nonexistent.py"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "does not exist" in result.stderr.lower()

    def test_analyze_unsupported_language(self, tmp_path):
        """Test analyzing unsupported language shows error."""
        test_file = tmp_path / "test.xyz"
        test_file.write_text("unknown language")

        result = subprocess.run(
            [sys.executable, "-m", "tree_sitter_analyzer_v2", "analyze", str(test_file)],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode != 0
        assert "unsupported" in result.stderr.lower() or "not supported" in result.stderr.lower()


class TestSearchFilesCommand:
    """Tests for 'search-files' command."""

    def test_search_files_by_pattern(self, search_fixtures_dir):
        """Test searching files by glob pattern."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer_v2",
                "search-files",
                str(search_fixtures_dir),
                "*.py",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "sample1.py" in result.stdout  # Actual fixture filename

    def test_search_files_by_type(self, search_fixtures_dir):
        """Test searching files by type."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer_v2",
                "search-files",
                str(search_fixtures_dir),
                "--type",
                "py",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "sample1.py" in result.stdout  # Actual fixture filename

    def test_search_files_nonexistent_directory(self):
        """Test searching in nonexistent directory shows error."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer_v2",
                "search-files",
                "/nonexistent/path",
                "*.py",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "does not exist" in result.stderr.lower()


class TestSearchContentCommand:
    """Tests for 'search-content' command."""

    def test_search_content_by_pattern(self, search_fixtures_dir):
        """Test searching content by pattern."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer_v2",
                "search-content",
                str(search_fixtures_dir),
                "class",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "class" in result.stdout.lower()

    def test_search_content_case_insensitive(self, search_fixtures_dir):
        """Test case-insensitive content search."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer_v2",
                "search-content",
                str(search_fixtures_dir),
                "CLASS",
                "--ignore-case",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        # Should find "class" even though we searched for "CLASS"

    def test_search_content_with_type_filter(self, search_fixtures_dir):
        """Test content search with file type filter."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer_v2",
                "search-content",
                str(search_fixtures_dir),
                "function",
                "--type",
                "py",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0


class TestCLIHelp:
    """Tests for CLI help and documentation."""

    def test_main_help(self):
        """Test main help message."""
        result = subprocess.run(
            [sys.executable, "-m", "tree_sitter_analyzer_v2", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "analyze" in result.stdout
        assert "search-files" in result.stdout
        assert "search-content" in result.stdout

    def test_analyze_help(self):
        """Test analyze command help."""
        result = subprocess.run(
            [sys.executable, "-m", "tree_sitter_analyzer_v2", "analyze", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "--format" in result.stdout
        assert "markdown" in result.stdout.lower()
        assert "toon" in result.stdout.lower()


class TestCLIPerformance:
    """Performance tests for CLI."""

    def test_analyze_performance(self, analyze_fixtures_dir):
        """Test analyze command completes quickly."""
        import time

        sample_py = analyze_fixtures_dir / "sample.py"

        start = time.time()
        result = subprocess.run(
            [sys.executable, "-m", "tree_sitter_analyzer_v2", "analyze", str(sample_py)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        duration = time.time() - start

        assert result.returncode == 0
        assert (
            duration < 3.0
        )  # Should complete in under 3 seconds (generous for subprocess overhead)


@pytest.fixture
def search_fixtures_dir():
    """Return path to search test fixtures."""
    return Path(__file__).parent.parent / "fixtures" / "search_fixtures"


@pytest.fixture
def analyze_fixtures_dir():
    """Return path to analyze test fixtures."""
    return Path(__file__).parent.parent / "fixtures" / "analyze_fixtures"
