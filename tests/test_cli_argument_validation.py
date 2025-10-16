#!/usr/bin/env python3
"""
CLI Argument Validation Tests

Tests for the CLI argument validation functionality.
"""

import argparse

import pytest

from tree_sitter_analyzer.cli.argument_validator import CLIArgumentValidator


class TestCLIArgumentValidation:
    """Tests for CLI argument validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = CLIArgumentValidator()

    def create_args(self, **kwargs):
        """Helper to create argparse.Namespace with specified attributes."""
        args = argparse.Namespace()
        for key, value in kwargs.items():
            setattr(args, key, value)
        return args

    def test_valid_table_only(self):
        """Test that --table only is valid."""
        args = self.create_args(table="full", query_key=None)
        result = self.validator.validate_arguments(args)
        assert result is None

    def test_valid_query_key_only(self):
        """Test that --query-key only is valid."""
        args = self.create_args(table=None, query_key="methods")
        result = self.validator.validate_arguments(args)
        assert result is None

    def test_valid_query_key_with_filter(self):
        """Test that --query-key with --filter is valid."""
        args = self.create_args(table=None, query_key="methods", filter="name=main")
        result = self.validator.validate_arguments(args)
        assert result is None

    def test_valid_no_table_no_query_key(self):
        """Test that neither --table nor --query-key is valid."""
        args = self.create_args(table=None, query_key=None)
        result = self.validator.validate_arguments(args)
        assert result is None

    def test_invalid_table_and_query_key_combination(self):
        """Test that --table and --query-key together is invalid."""
        args = self.create_args(table="full", query_key="methods")
        result = self.validator.validate_arguments(args)
        assert result is not None
        assert "--table and --query-key cannot be used together" in result
        assert "Use --query-key with --filter instead" in result

    def test_invalid_table_and_query_key_with_filter(self):
        """Test that --table and --query-key with --filter is invalid."""
        args = self.create_args(table="full", query_key="methods", filter="name=main")
        result = self.validator.validate_arguments(args)
        assert result is not None
        assert "--table and --query-key cannot be used together" in result

    def test_table_query_exclusivity_validator(self):
        """Test the specific table-query exclusivity validator."""
        # Valid cases
        args = self.create_args(table="full", query_key=None)
        result = self.validator.validate_table_query_exclusivity(args)
        assert result is None

        args = self.create_args(table=None, query_key="methods")
        result = self.validator.validate_table_query_exclusivity(args)
        assert result is None

        # Invalid case
        args = self.create_args(table="full", query_key="methods")
        result = self.validator.validate_table_query_exclusivity(args)
        assert result is not None
        assert "--table and --query-key cannot be used together" in result

    def test_usage_examples_content(self):
        """Test that usage examples contain expected content."""
        examples = self.validator.get_usage_examples()
        assert "Correct usage examples:" in examples
        assert "--table full" in examples
        assert "--query-key methods" in examples
        assert "--query-key methods --filter" in examples
        assert "Invalid combination" in examples

    def test_different_table_formats_with_query_key(self):
        """Test that all table formats are invalid with query-key."""
        table_formats = ["full", "compact", "csv", "json"]

        for table_format in table_formats:
            args = self.create_args(table=table_format, query_key="methods")
            result = self.validator.validate_arguments(args)
            assert result is not None, (
                f"Table format '{table_format}' should be invalid with query-key"
            )
            assert "--table and --query-key cannot be used together" in result

    def test_missing_attributes_handling(self):
        """Test handling of missing attributes in args."""
        # Args without table or query_key attributes
        args = argparse.Namespace()
        result = self.validator.validate_arguments(args)
        assert result is None

        # Args with only table attribute
        args = argparse.Namespace()
        args.table = "full"
        result = self.validator.validate_arguments(args)
        assert result is None

        # Args with only query_key attribute
        args = argparse.Namespace()
        args.query_key = "methods"
        result = self.validator.validate_arguments(args)
        assert result is None

    def test_empty_string_values(self):
        """Test handling of empty string values."""
        # Empty string should be treated as None/not specified
        args = self.create_args(table="", query_key="")
        result = self.validator.validate_arguments(args)
        assert result is None

        # One empty, one with value
        args = self.create_args(table="", query_key="methods")
        result = self.validator.validate_arguments(args)
        assert result is None

        args = self.create_args(table="full", query_key="")
        result = self.validator.validate_arguments(args)
        assert result is None

    def test_none_values_explicitly(self):
        """Test explicit None values."""
        args = self.create_args(table=None, query_key=None)
        result = self.validator.validate_arguments(args)
        assert result is None

    def test_validator_initialization(self):
        """Test validator can be initialized properly."""
        validator = CLIArgumentValidator()
        assert validator is not None

        # Test that methods are callable
        assert callable(validator.validate_arguments)
        assert callable(validator.validate_table_query_exclusivity)
        assert callable(validator.get_usage_examples)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
