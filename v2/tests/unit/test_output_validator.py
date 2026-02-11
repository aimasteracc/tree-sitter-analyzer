"""
Unit tests for output validator module.

Tests validation of TOON format outputs and token waste estimation.
"""

from tree_sitter_analyzer_v2.utils.output_validator import (
    estimate_token_waste,
    validate_toon_output,
)


class TestValidateToonOutput:
    """Tests for validate_toon_output."""

    def test_non_toon_format_skips_validation(self):
        """Non-TOON format should skip validation."""
        result = {"format": "json", "data": {"key": "value"}}
        validation = validate_toon_output(result)
        assert validation["valid"] is True
        assert "Not TOON format" in validation["reason"]

    def test_missing_format_field_skips_validation(self):
        """Missing format field should skip validation."""
        result = {"data": "some content"}
        validation = validate_toon_output(result)
        assert validation["valid"] is True

    def test_toon_missing_toon_content(self):
        """TOON format without toon_content should be invalid."""
        result = {"format": "toon"}
        validation = validate_toon_output(result)
        assert validation["valid"] is False
        assert "toon_content" in validation["reason"]

    def test_clean_toon_output(self):
        """Clean TOON output (only format + toon_content) should be valid."""
        result = {"format": "toon", "toon_content": "CLS Foo L1-10"}
        validation = validate_toon_output(result)
        assert validation["valid"] is True
        assert "Clean TOON" in validation["reason"]

    def test_toon_with_extra_fields(self):
        """TOON output with redundant fields should be invalid."""
        result = {
            "format": "toon",
            "toon_content": "CLS Foo L1-10",
            "classes": [{"name": "Foo"}],
            "methods": [],
        }
        validation = validate_toon_output(result)
        assert validation["valid"] is False
        assert "redundant" in validation["reason"].lower()
        assert "classes" in validation["extra_fields"]
        assert "methods" in validation["extra_fields"]
        assert "suggestion" in validation

    def test_toon_with_single_extra_field(self):
        """TOON output with one extra field should be invalid."""
        result = {
            "format": "toon",
            "toon_content": "CLS Foo L1-10",
            "success": True,
        }
        validation = validate_toon_output(result)
        assert validation["valid"] is False
        assert validation["extra_fields"] == ["success"]


class TestEstimateTokenWaste:
    """Tests for estimate_token_waste."""

    def test_clean_output_no_waste(self):
        """Clean TOON output should have 0% waste."""
        result = {"format": "toon", "toon_content": "CLS Foo L1-10"}
        waste = estimate_token_waste(result)
        assert waste["redundant_chars"] == 0
        assert waste["waste_percentage"] == 0.0
        assert waste["total_chars"] > 0

    def test_redundant_fields_show_waste(self):
        """Output with redundant fields should show non-zero waste."""
        result = {
            "format": "toon",
            "toon_content": "CLS Foo L1-10",
            "classes": [{"name": "Foo", "line_start": 1, "line_end": 10}],
        }
        waste = estimate_token_waste(result)
        assert waste["redundant_chars"] > 0
        assert waste["waste_percentage"] > 0
        assert waste["total_chars"] > waste["redundant_chars"]

    def test_non_toon_output_no_waste(self):
        """Non-TOON output should show 0% waste."""
        result = {"format": "json", "data": {"key": "value"}}
        waste = estimate_token_waste(result)
        assert waste["redundant_chars"] == 0
        assert waste["waste_percentage"] == 0.0

    def test_waste_percentage_calculation(self):
        """Waste percentage should be correctly calculated."""
        result = {
            "format": "toon",
            "toon_content": "x",
            "extra_data": "a" * 100,
        }
        waste = estimate_token_waste(result)
        assert waste["waste_percentage"] > 0
        assert waste["waste_percentage"] <= 100
