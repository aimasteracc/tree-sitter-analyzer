#!/usr/bin/env python3
"""
Integration Tests for Grammar Coverage Validator

Tests the validator's ability to detect covered node types using real plugins.
Uses Python plugin as it's the most stable and well-tested.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.grammar_coverage.validator import (
    CoverageReport,
    _get_covered_node_types_from_plugin,
    _parse_corpus_file,
    check_coverage_threshold,
    generate_coverage_report,
    validate_plugin_coverage,
    validate_plugin_coverage_sync,
)


class TestPluginIntegration:
    """Tests for plugin integration with validator"""

    @pytest.mark.asyncio
    async def test_get_covered_node_types_from_plugin_python(self):
        """Test that covered node types are correctly detected from Python plugin"""
        # Create a temporary Python file with various constructs
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                """
import os
import sys

def hello():
    pass

class MyClass:
    def method(self):
        x = 42
        return x
"""
            )
            temp_path = Path(f.name)

        try:
            # Get covered types from plugin
            covered_types = await _get_covered_node_types_from_plugin(temp_path, "python")

            # Verify we got some covered types
            assert isinstance(covered_types, set)
            assert len(covered_types) > 0

            # Python plugin should detect these common node types
            # Note: Actual node types depend on plugin implementation
            # We just verify that SOME types are detected
            print(f"Detected covered types: {covered_types}")

        finally:
            temp_path.unlink()

    @pytest.mark.asyncio
    async def test_get_covered_node_types_unsupported_language(self):
        """Test behavior with unsupported language"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("some text")
            temp_path = Path(f.name)

        try:
            # Should return empty set for unsupported language
            covered_types = await _get_covered_node_types_from_plugin(
                temp_path, "nonexistent"
            )
            assert isinstance(covered_types, set)
            assert len(covered_types) == 0

        finally:
            temp_path.unlink()

    @pytest.mark.asyncio
    async def test_get_covered_node_types_empty_file(self):
        """Test with empty file"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("")
            temp_path = Path(f.name)

        try:
            # Should return empty set or minimal types for empty file
            covered_types = await _get_covered_node_types_from_plugin(temp_path, "python")
            assert isinstance(covered_types, set)
            # Empty file may have 0 or minimal types (like "module")

        finally:
            temp_path.unlink()


class TestValidatorWithRealCorpus:
    """Tests using real corpus files if available"""

    def test_parse_corpus_file_python(self):
        """Test parsing a real Python corpus file"""
        # Try to find the Python corpus file
        project_root = Path(__file__).parent.parent.parent.parent
        corpus_path = project_root / "tests" / "golden" / "corpus_python.py"

        if not corpus_path.exists():
            pytest.skip(f"Python corpus file not found at {corpus_path}")

        # Parse the corpus file
        node_types = _parse_corpus_file(corpus_path, "python")

        assert isinstance(node_types, dict)
        assert len(node_types) > 0

        # Python corpus should have common node types
        # The exact types depend on corpus content
        print(f"Found {len(node_types)} node types in Python corpus")

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_validate_plugin_coverage_python(self):
        """Test full validation pipeline with Python corpus"""
        # Try to find the Python corpus file
        project_root = Path(__file__).parent.parent.parent.parent
        corpus_path = project_root / "tests" / "golden" / "corpus_python.py"
        expected_path = project_root / "tests" / "golden" / "corpus_python_expected.json"

        if not corpus_path.exists() or not expected_path.exists():
            pytest.skip(
                f"Python corpus files not found at {corpus_path} or {expected_path}"
            )

        # Run validation
        report = await validate_plugin_coverage("python")

        # Verify report structure
        assert isinstance(report, CoverageReport)
        assert report.language == "python"
        assert report.total_node_types > 0
        assert report.covered_node_types >= 0
        assert 0.0 <= report.coverage_percentage <= 100.0
        assert isinstance(report.uncovered_types, list)
        assert report.corpus_file == str(corpus_path)

        # Print report for debugging
        print("\n" + generate_coverage_report(report))

    def test_validate_plugin_coverage_sync_python(self):
        """Test synchronous validation with Python corpus"""
        # Try to find the Python corpus file
        project_root = Path(__file__).parent.parent.parent.parent
        corpus_path = project_root / "tests" / "golden" / "corpus_python.py"
        expected_path = project_root / "tests" / "golden" / "corpus_python_expected.json"

        if not corpus_path.exists() or not expected_path.exists():
            pytest.skip(
                f"Python corpus files not found at {corpus_path} or {expected_path}"
            )

        # Run synchronous validation
        report = validate_plugin_coverage_sync("python")

        # Verify report structure
        assert isinstance(report, CoverageReport)
        assert report.language == "python"
        assert report.total_node_types > 0
        assert report.covered_node_types >= 0

    def test_generate_coverage_report_format(self):
        """Test coverage report generation format"""
        # Create a mock report
        report = CoverageReport(
            language="python",
            total_node_types=50,
            covered_node_types=45,
            coverage_percentage=90.0,
            uncovered_types=["type_a", "type_b", "type_c"],
            corpus_file="/path/to/corpus.py",
            expected_node_types={"type_x": 10, "type_y": 5},
            actual_node_types={"type_x": 10, "type_y": 5, "type_z": 3},
        )

        report_text = generate_coverage_report(report)

        # Verify report format
        assert "Python:" in report_text
        assert "90.0%" in report_text
        assert "45/50" in report_text
        assert "Uncovered node types (3):" in report_text
        assert "- type_a" in report_text
        assert "- type_b" in report_text
        assert "- type_c" in report_text
        assert "corpus.py" in report_text

    def test_check_coverage_threshold(self):
        """Test coverage threshold checking"""
        # Test passing threshold
        assert check_coverage_threshold(100.0, 100.0)
        assert check_coverage_threshold(95.0, 90.0)
        assert check_coverage_threshold(90.0, 90.0)

        # Test failing threshold
        assert not check_coverage_threshold(89.9, 90.0)
        assert not check_coverage_threshold(50.0, 100.0)
        assert not check_coverage_threshold(0.0, 100.0)


class TestErrorHandling:
    """Tests for error handling in validator"""

    def test_nonexistent_corpus_file(self):
        """Test with non-existent corpus file"""
        with pytest.raises(FileNotFoundError):
            _parse_corpus_file(Path("/nonexistent/file.py"), "python")

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_validate_unsupported_language(self):
        """Test validation with unsupported language"""
        with pytest.raises(ValueError, match="Unsupported language"):
            await validate_plugin_coverage("nonexistent_language")

    @pytest.mark.asyncio
    async def test_get_covered_types_invalid_file(self):
        """Test with invalid file path"""
        invalid_path = Path("/nonexistent/file.py")
        # Should handle gracefully and return empty set
        covered_types = await _get_covered_node_types_from_plugin(invalid_path, "python")
        assert isinstance(covered_types, set)
        assert len(covered_types) == 0
