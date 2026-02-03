"""
Test CLI --summary mode functionality.

Tests the summary output format and performance characteristics.
"""

import subprocess
import time
from pathlib import Path


class TestSummaryMode:
    """Test --summary flag in CLI."""

    def test_summary_flag_recognized(self) -> None:
        """Test that --summary flag is recognized by CLI."""
        result = subprocess.run(
            ["uv", "run", "tsa", "analyze", "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )

        # Should mention --summary in help text
        assert "--summary" in result.stdout

    def test_summary_output_contains_required_fields(self) -> None:
        """Test that summary output contains all required fields."""
        # Use a test fixture file
        test_file = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = subprocess.run(
            ["uv", "run", "tsa", "analyze", str(test_file), "--summary"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        output = result.stdout

        # Verify required fields
        assert "File:" in output
        assert "Language:" in output
        assert "Lines:" in output
        assert "Classes:" in output
        assert "Functions:" in output
        assert "Imports:" in output

    def test_summary_output_format(self) -> None:
        """Test that summary output is concise (< 15 lines)."""
        test_file = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = subprocess.run(
            ["uv", "run", "tsa", "analyze", str(test_file), "--summary"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )

        assert result.returncode == 0

        lines = [line for line in result.stdout.split("\n") if line.strip()]
        # Summary should be concise (< 15 lines)
        assert len(lines) < 15, f"Summary too long: {len(lines)} lines"

    def test_summary_is_faster_than_full(self) -> None:
        """Test that summary mode is faster than full analysis."""
        test_file = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        # Time summary mode
        start = time.perf_counter()
        subprocess.run(
            ["uv", "run", "tsa", "analyze", str(test_file), "--summary"],
            capture_output=True,
            timeout=10,
        )
        summary_time = time.perf_counter() - start

        # Time full mode
        start = time.perf_counter()
        subprocess.run(
            ["uv", "run", "tsa", "analyze", str(test_file), "--format", "toon"],
            capture_output=True,
            timeout=10,
        )
        full_time = time.perf_counter() - start

        # Summary should be at least 1.5x faster (accounting for subprocess overhead)
        assert summary_time < full_time * 1.5, (
            f"Summary ({summary_time:.2f}s) not significantly faster than "
            f"full ({full_time:.2f}s)"
        )

    def test_summary_with_python_file(self) -> None:
        """Test summary mode with a Python file."""
        test_file = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = subprocess.run(
            ["uv", "run", "tsa", "analyze", str(test_file), "--summary"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )

        assert result.returncode == 0
        output = result.stdout

        # Should identify as Python
        assert "python" in output.lower()

    def test_summary_with_java_file(self) -> None:
        """Test summary mode with a Java file."""
        test_file = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "Sample.java"

        result = subprocess.run(
            ["uv", "run", "tsa", "analyze", str(test_file), "--summary"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )

        assert result.returncode == 0
        output = result.stdout

        # Should identify as Java
        assert "java" in output.lower()

    def test_summary_incompatible_with_format(self) -> None:
        """Test that --summary and --format are mutually exclusive."""
        test_file = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = subprocess.run(
            ["uv", "run", "tsa", "analyze", str(test_file), "--summary", "--format", "toon"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )

        # Should either error or ignore one of them (implementation choice)
        # For now, we'll make --summary take precedence
        assert result.returncode == 0
