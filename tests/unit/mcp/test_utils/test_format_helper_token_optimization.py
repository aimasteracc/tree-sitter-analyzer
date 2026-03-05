#!/usr/bin/env python3
"""Tests for token optimization in format_helper."""
import pytest


class TestToonRedundantFields:
    """Tests for TOON redundant field constants."""

    def test_redundant_fields_constant_exists(self):
        """TOON_REDUNDANT_FIELDS constant should be defined."""
        from tree_sitter_analyzer.mcp.utils.format_helper import TOON_REDUNDANT_FIELDS

        assert TOON_REDUNDANT_FIELDS is not None
        assert isinstance(TOON_REDUNDANT_FIELDS, frozenset)

    def test_redundant_fields_contains_expected_fields(self):
        """TOON_REDUNDANT_FIELDS should contain expected data fields."""
        from tree_sitter_analyzer.mcp.utils.format_helper import TOON_REDUNDANT_FIELDS

        expected = {
            "results",
            "matches",
            "content",
            "data",
            "items",
            "files",
            "lines",
            "detailed_analysis",
            "structural_overview",
            "summary",
        }
        assert expected.issubset(TOON_REDUNDANT_FIELDS)

    def test_metadata_fields_constant_exists(self):
        """TOON_METADATA_FIELDS constant should be defined."""
        from tree_sitter_analyzer.mcp.utils.format_helper import TOON_METADATA_FIELDS

        assert TOON_METADATA_FIELDS is not None
        assert isinstance(TOON_METADATA_FIELDS, frozenset)

    def test_metadata_fields_contains_expected_fields(self):
        """TOON_METADATA_FIELDS should contain expected metadata fields."""
        from tree_sitter_analyzer.mcp.utils.format_helper import TOON_METADATA_FIELDS

        expected = {"success", "file_path", "language", "format", "warnings"}
        assert expected.issubset(TOON_METADATA_FIELDS)
