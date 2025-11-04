#!/usr/bin/env python3
"""
Tests for OutputFormatValidator
"""

import pytest

from tree_sitter_analyzer.mcp.tools.output_format_validator import (
    OutputFormatValidator,
    get_default_validator,
)


class TestOutputFormatValidator:
    """Test OutputFormatValidator class."""

    def test_single_format_parameter_valid(self):
        """Test that single format parameter is valid."""
        validator = OutputFormatValidator()
        
        # Each format parameter should be valid individually
        validator.validate_output_format_exclusion({"total_only": True})
        validator.validate_output_format_exclusion({"count_only_matches": True})
        validator.validate_output_format_exclusion({"summary_only": True})
        validator.validate_output_format_exclusion({"group_by_file": True})
        validator.validate_output_format_exclusion({"suppress_output": True})

    def test_no_format_parameter_valid(self):
        """Test that no format parameter is valid (normal mode)."""
        validator = OutputFormatValidator()
        validator.validate_output_format_exclusion({})
        validator.validate_output_format_exclusion({"query": "test"})

    def test_multiple_format_parameters_raises_error(self):
        """Test that multiple format parameters raise ValueError."""
        validator = OutputFormatValidator()
        
        # Test various combinations
        with pytest.raises(ValueError, match="Output Format Parameter Error"):
            validator.validate_output_format_exclusion({
                "total_only": True,
                "count_only_matches": True
            })
        
        with pytest.raises(ValueError, match="Output Format Parameter Error"):
            validator.validate_output_format_exclusion({
                "total_only": True,
                "summary_only": True
            })
        
        with pytest.raises(ValueError, match="Output Format Parameter Error"):
            validator.validate_output_format_exclusion({
                "count_only_matches": True,
                "group_by_file": True,
                "summary_only": True
            })

    def test_error_message_contains_token_guidance(self):
        """Test that error messages include token efficiency guidance."""
        validator = OutputFormatValidator()
        
        try:
            validator.validate_output_format_exclusion({
                "total_only": True,
                "summary_only": True
            })
            assert False, "Should have raised ValueError"
        except ValueError as e:
            error_msg = str(e)
            # Check for key elements
            assert "total_only" in error_msg
            assert "summary_only" in error_msg
            assert "~10 tokens" in error_msg or "トークン" in error_msg
            assert "Mutually Exclusive" in error_msg or "相互排他的" in error_msg

    def test_get_active_format(self):
        """Test getting the active format from arguments."""
        validator = OutputFormatValidator()
        
        assert validator.get_active_format({}) == "normal"
        assert validator.get_active_format({"query": "test"}) == "normal"
        assert validator.get_active_format({"total_only": True}) == "total_only"
        assert validator.get_active_format({"count_only_matches": True}) == "count_only_matches"
        assert validator.get_active_format({"summary_only": True}) == "summary_only"
        assert validator.get_active_format({"group_by_file": True}) == "group_by_file"
        assert validator.get_active_format({"suppress_output": True}) == "suppress_output"

    def test_get_default_validator(self):
        """Test getting the default validator instance."""
        validator1 = get_default_validator()
        validator2 = get_default_validator()
        
        # Should return the same instance
        assert validator1 is validator2
        assert isinstance(validator1, OutputFormatValidator)

    def test_false_values_ignored(self):
        """Test that False values are ignored (not treated as specified)."""
        validator = OutputFormatValidator()
        
        # False values should be ignored
        validator.validate_output_format_exclusion({
            "total_only": False,
            "count_only_matches": False,
            "summary_only": True  # Only this one is active
        })
        
        # This should also be valid
        validator.validate_output_format_exclusion({
            "total_only": False,
            "count_only_matches": False,
            "summary_only": False,
            "group_by_file": False
        })

    def test_language_detection(self):
        """Test language detection mechanism."""
        validator = OutputFormatValidator()
        
        # Default should be 'en'
        lang = validator._detect_language()
        assert lang in ["en", "ja"]
