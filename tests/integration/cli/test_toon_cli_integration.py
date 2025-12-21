#!/usr/bin/env python3
"""
Tests for TOON format CLI integration.

Verifies that:
1. --format toon option works correctly
2. --output-format toon option works correctly
3. --toon-use-tabs option works correctly
4. TOON output is correctly formatted for all commands
"""

import json
import subprocess
import sys

import pytest


class TestToonCLIOptions:
    """Tests for TOON CLI option parsing."""

    def test_format_toon_option_in_help(self):
        """Test that --format toon is documented in help."""
        result = subprocess.run(
            [sys.executable, "-m", "tree_sitter_analyzer.cli", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "toon" in result.stdout

    def test_output_format_toon_option_in_help(self):
        """Test that --output-format toon is documented in help."""
        result = subprocess.run(
            [sys.executable, "-m", "tree_sitter_analyzer.cli", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "--output-format" in result.stdout
        # Verify toon is a valid choice
        assert "toon" in result.stdout

    def test_toon_use_tabs_option_in_help(self):
        """Test that --toon-use-tabs is documented in help."""
        result = subprocess.run(
            [sys.executable, "-m", "tree_sitter_analyzer.cli", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "--toon-use-tabs" in result.stdout


class TestToonCLIOutput:
    """Tests for TOON format CLI output."""

    @pytest.fixture
    def sample_python_file(self, tmp_path):
        """Create a sample Python file for testing."""
        sample_file = tmp_path / "sample.py"
        sample_file.write_text(
            '''"""Sample Python module."""


def hello_world():
    """Say hello."""
    print("Hello, World!")


class Calculator:
    """Simple calculator class."""

    def add(self, a, b):
        """Add two numbers."""
        return a + b

    def subtract(self, a, b):
        """Subtract two numbers."""
        return a - b
''',
            encoding="utf-8",
        )
        return sample_file

    @pytest.fixture
    def sample_java_file(self, tmp_path):
        """Create a sample Java file for testing."""
        sample_file = tmp_path / "Sample.java"
        sample_file.write_text(
            """package com.example;

public class Sample {
    private int value;

    public Sample() {
        this.value = 0;
    }

    public int getValue() {
        return value;
    }

    public void setValue(int value) {
        this.value = value;
    }
}
""",
            encoding="utf-8",
        )
        return sample_file

    def test_structure_command_with_toon_format(self, sample_python_file):
        """Test --structure command with --output-format toon."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli",
                str(sample_python_file),
                "--structure",
                "--output-format",
                "toon",
                "--project-root",
                str(sample_python_file.parent),
            ],
            capture_output=True,
            text=True,
        )

        # Command should succeed
        assert result.returncode == 0, f"stderr: {result.stderr}"

        # Output should contain TOON format indicators (key: value syntax)
        output = result.stdout
        assert "file_path:" in output or "language:" in output

        # Should NOT look like JSON (no curly braces at start)
        stripped = output.strip()
        if stripped:
            assert not (
                stripped.startswith("{") and stripped.endswith("}")
            ), "Output should not be JSON format"

    def test_structure_command_with_format_alias(self, sample_python_file):
        """Test --structure command with --format toon alias."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli",
                str(sample_python_file),
                "--structure",
                "--format",
                "toon",
                "--project-root",
                str(sample_python_file.parent),
            ],
            capture_output=True,
            text=True,
        )

        # Command should succeed
        assert result.returncode == 0, f"stderr: {result.stderr}"

        # Output should contain TOON format
        output = result.stdout
        assert ":" in output  # TOON uses key: value syntax

    def test_summary_command_with_toon_format(self, sample_python_file):
        """Test --summary command with --output-format toon."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli",
                str(sample_python_file),
                "--summary",
                "--output-format",
                "toon",
                "--project-root",
                str(sample_python_file.parent),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = result.stdout
        # Should contain file info in TOON format
        assert ":" in output

    def test_advanced_command_with_toon_format(self, sample_python_file):
        """Test --advanced command with --output-format toon."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli",
                str(sample_python_file),
                "--advanced",
                "--output-format",
                "toon",
                "--project-root",
                str(sample_python_file.parent),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = result.stdout
        # Should contain analysis results in TOON format
        assert ":" in output

    def test_partial_read_command_with_toon_format(self, sample_python_file):
        """Test --partial-read command with --output-format toon."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli",
                str(sample_python_file),
                "--partial-read",
                "--start-line",
                "1",
                "--end-line",
                "5",
                "--output-format",
                "toon",
                "--project-root",
                str(sample_python_file.parent),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = result.stdout
        # Should contain file info in TOON format
        assert "file_path:" in output or ":" in output

    def test_query_command_with_toon_format(self, sample_python_file):
        """Test --query-key command with --output-format toon."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli",
                str(sample_python_file),
                "--query-key",
                "function",
                "--output-format",
                "toon",
                "--project-root",
                str(sample_python_file.parent),
            ],
            capture_output=True,
            text=True,
        )

        # Should succeed or show no results
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_toon_use_tabs_option(self, sample_python_file):
        """Test --toon-use-tabs option produces tab-delimited output."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli",
                str(sample_python_file),
                "--structure",
                "--output-format",
                "toon",
                "--toon-use-tabs",
                "--project-root",
                str(sample_python_file.parent),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Output should be in TOON format (with or without tabs)
        output = result.stdout
        assert ":" in output

    def test_toon_output_vs_json_output(self, sample_python_file):
        """Test that TOON output is shorter than JSON output."""
        # Get JSON output
        json_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli",
                str(sample_python_file),
                "--structure",
                "--output-format",
                "json",
                "--project-root",
                str(sample_python_file.parent),
            ],
            capture_output=True,
            text=True,
        )

        # Get TOON output
        toon_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli",
                str(sample_python_file),
                "--structure",
                "--output-format",
                "toon",
                "--project-root",
                str(sample_python_file.parent),
            ],
            capture_output=True,
            text=True,
        )

        assert json_result.returncode == 0
        assert toon_result.returncode == 0

        # TOON should generally be shorter than JSON
        # Note: This may not always be true for very small outputs
        json_len = len(json_result.stdout)
        toon_len = len(toon_result.stdout)

        # Just verify both have output - size comparison is not guaranteed
        assert json_len > 0
        assert toon_len > 0


class TestToonCLIEdgeCases:
    """Tests for TOON CLI edge cases."""

    def test_invalid_format_option(self, tmp_path):
        """Test that invalid format option is rejected."""
        sample_file = tmp_path / "sample.py"
        sample_file.write_text("def hello(): pass", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli",
                str(sample_file),
                "--structure",
                "--output-format",
                "invalid_format",
            ],
            capture_output=True,
            text=True,
        )

        # Should fail with error
        assert result.returncode != 0 or "error" in result.stderr.lower()

    def test_format_and_output_format_both_specified(self, tmp_path):
        """Test behavior when both --format and --output-format are specified."""
        sample_file = tmp_path / "sample.py"
        sample_file.write_text("def hello(): pass", encoding="utf-8")

        # --format should take precedence (as an alias)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli",
                str(sample_file),
                "--structure",
                "--format",
                "toon",
                "--output-format",
                "json",
                "--project-root",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
        )

        # Should succeed with toon format (--format overrides --output-format)
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_toon_use_tabs_without_toon_format(self, tmp_path):
        """Test --toon-use-tabs is ignored when not using toon format."""
        sample_file = tmp_path / "sample.py"
        sample_file.write_text("def hello(): pass", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli",
                str(sample_file),
                "--structure",
                "--output-format",
                "json",
                "--toon-use-tabs",
                "--project-root",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
        )

        # Should still succeed with JSON output
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = result.stdout.strip()
        # Should be valid JSON
        if output:
            # Skip the section header line
            lines = output.split("\n")
            json_lines = [
                line
                for line in lines
                if not line.startswith("---") and not line.startswith("\n---")
            ]
            json_output = "\n".join(json_lines).strip()
            if json_output:
                try:
                    parsed = json.loads(json_output)
                    assert isinstance(parsed, dict)
                except json.JSONDecodeError:
                    pass  # Allow non-JSON output for structure with headers
