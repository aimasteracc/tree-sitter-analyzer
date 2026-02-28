#!/usr/bin/env python3
"""
Tests for CLIArgumentValidator

Covers validate_arguments and validate_table_query_exclusivity.
"""

from types import SimpleNamespace

import pytest

from tree_sitter_analyzer.cli.argument_validator import CLIArgumentValidator


class TestCLIArgumentValidatorValidateTableQueryExclusivity:
    """Tests for CLIArgumentValidator.validate_table_query_exclusivity."""

    def setup_method(self):
        self.validator = CLIArgumentValidator()

    def test_returns_none_when_neither_table_nor_query_key(self):
        """No error when neither --table nor --query-key is provided."""
        args = SimpleNamespace()
        result = self.validator.validate_table_query_exclusivity(args)
        assert result is None

    def test_returns_none_when_only_table_is_set(self):
        """No error when only --table is provided."""
        args = SimpleNamespace(table="users", query_key=None)
        result = self.validator.validate_table_query_exclusivity(args)
        assert result is None

    def test_returns_none_when_only_query_key_is_set(self):
        """No error when only --query-key is provided."""
        args = SimpleNamespace(table=None, query_key="class_declaration")
        result = self.validator.validate_table_query_exclusivity(args)
        assert result is None

    def test_returns_error_when_both_table_and_query_key_are_set(self):
        """Error message returned when both --table and --query-key are set."""
        args = SimpleNamespace(table="users", query_key="class_declaration")
        result = self.validator.validate_table_query_exclusivity(args)
        assert isinstance(result, str)
        assert "--table" in result
        assert "--query-key" in result

    def test_returns_none_when_table_is_empty_string(self):
        """Empty string for --table is treated as not specified."""
        args = SimpleNamespace(table="", query_key="class_declaration")
        result = self.validator.validate_table_query_exclusivity(args)
        assert result is None

    def test_returns_none_when_query_key_is_empty_string(self):
        """Empty string for --query-key is treated as not specified."""
        args = SimpleNamespace(table="users", query_key="")
        result = self.validator.validate_table_query_exclusivity(args)
        assert result is None

    def test_returns_none_when_args_has_no_relevant_attributes(self):
        """No error when args object has no table or query_key attribute."""
        args = SimpleNamespace()  # no table, no query_key
        result = self.validator.validate_table_query_exclusivity(args)
        assert result is None


class TestCLIArgumentValidatorValidateArguments:
    """Tests for CLIArgumentValidator.validate_arguments (the broader method)."""

    def setup_method(self):
        self.validator = CLIArgumentValidator()

    def test_returns_none_for_clean_args(self):
        """validate_arguments returns None when no conflict exists."""
        args = SimpleNamespace(table=None, query_key=None)
        result = self.validator.validate_arguments(args)
        assert result is None

    def test_returns_error_string_for_conflicting_args(self):
        """validate_arguments returns an error string when both table and query_key are given."""
        args = SimpleNamespace(table="users", query_key="functions")
        result = self.validator.validate_arguments(args)
        assert isinstance(result, str)
