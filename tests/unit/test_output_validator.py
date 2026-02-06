"""
Tests for output_validator module.

TDD: Testing TOON format validation and token waste estimation.
"""

import pytest

from tree_sitter_analyzer_v2.utils.output_validator import (
    validate_toon_output,
    estimate_token_waste,
)


class TestValidateToonOutput:
    """Test validate_toon_output function."""

    def test_non_toon_format_is_valid(self) -> None:
        """Non-TOON format should be valid (no validation needed)."""
        result = {"format": "json", "data": {"key": "value"}}
        validation = validate_toon_output(result)
        
        assert validation["valid"] is True
        assert "Not TOON format" in validation["reason"]

    def test_missing_format_key_is_valid(self) -> None:
        """Result without format key is valid (not TOON)."""
        result = {"data": {"key": "value"}}
        validation = validate_toon_output(result)
        
        assert validation["valid"] is True

    def test_toon_without_content_is_invalid(self) -> None:
        """TOON format without toon_content is invalid."""
        result = {"format": "toon"}
        validation = validate_toon_output(result)
        
        assert validation["valid"] is False
        assert "toon_content" in validation["reason"]

    def test_clean_toon_output_is_valid(self) -> None:
        """Clean TOON output (only format + toon_content) is valid."""
        result = {
            "format": "toon",
            "toon_content": "FUNC:main→CALLS[helper]"
        }
        validation = validate_toon_output(result)
        
        assert validation["valid"] is True
        assert "Clean TOON output" in validation["reason"]

    def test_toon_with_extra_fields_is_invalid(self) -> None:
        """TOON output with redundant fields is invalid."""
        result = {
            "format": "toon",
            "toon_content": "FUNC:main→CALLS[helper]",
            "functions": ["main", "helper"],  # redundant
            "count": 2,  # redundant
        }
        validation = validate_toon_output(result)
        
        assert validation["valid"] is False
        assert "redundant fields" in validation["reason"]
        assert "extra_fields" in validation
        assert "count" in validation["extra_fields"]
        assert "functions" in validation["extra_fields"]
        assert "suggestion" in validation

    def test_toon_with_single_extra_field(self) -> None:
        """TOON output with single extra field is invalid."""
        result = {
            "format": "toon",
            "toon_content": "data",
            "metadata": {"version": 1}
        }
        validation = validate_toon_output(result)
        
        assert validation["valid"] is False
        assert validation["extra_fields"] == ["metadata"]


class TestEstimateTokenWaste:
    """Test estimate_token_waste function."""

    def test_clean_output_has_zero_waste(self) -> None:
        """Clean TOON output should have 0% waste."""
        result = {
            "format": "toon",
            "toon_content": "data"
        }
        estimate = estimate_token_waste(result)
        
        assert estimate["redundant_chars"] == 0
        assert estimate["waste_percentage"] == 0.0
        assert estimate["total_chars"] > 0

    def test_non_toon_has_zero_waste(self) -> None:
        """Non-TOON output should have 0% waste."""
        result = {"format": "json", "data": "test"}
        estimate = estimate_token_waste(result)
        
        assert estimate["redundant_chars"] == 0
        assert estimate["waste_percentage"] == 0.0

    def test_redundant_fields_have_waste(self) -> None:
        """Redundant fields should be counted as waste."""
        result = {
            "format": "toon",
            "toon_content": "compact data",
            "extra_data": {"large": "redundant content here"}
        }
        estimate = estimate_token_waste(result)
        
        assert estimate["redundant_chars"] > 0
        assert estimate["waste_percentage"] > 0
        assert estimate["total_chars"] > estimate["redundant_chars"]

    def test_multiple_redundant_fields(self) -> None:
        """Multiple redundant fields should all be counted."""
        result = {
            "format": "toon",
            "toon_content": "x",
            "field1": "abc",
            "field2": "def",
            "field3": "ghi"
        }
        estimate = estimate_token_waste(result)
        
        assert estimate["redundant_chars"] > 0
        # Waste should include all three fields
        assert estimate["waste_percentage"] > 0

    def test_waste_percentage_calculation(self) -> None:
        """Waste percentage should be calculated correctly."""
        # Create result where redundant data is significant
        result = {
            "format": "toon",
            "toon_content": "a",  # very small
            "big_redundant": "x" * 100  # large redundant
        }
        estimate = estimate_token_waste(result)
        
        # Waste should be significant percentage
        assert estimate["waste_percentage"] > 50
