#!/usr/bin/env python3
"""Unit tests for platform_compat adapter - AdaptationRule, RemovePhantomFunctionsRule."""

from tree_sitter_analyzer.models import SQLFunction, SQLTrigger
from tree_sitter_analyzer.platform_compat.adapter import RemovePhantomFunctionsRule


class TestAdaptationRule:
    """Tests for AdaptationRule protocol compliance."""

    def test_remove_phantom_functions_rule_has_rule_id(self) -> None:
        """RemovePhantomFunctionsRule implements rule_id property."""
        rule = RemovePhantomFunctionsRule()
        assert rule.rule_id == "remove_phantom_functions"

    def test_remove_phantom_functions_rule_has_description(self) -> None:
        """RemovePhantomFunctionsRule implements description property."""
        rule = RemovePhantomFunctionsRule()
        assert "phantom" in rule.description.lower()

    def test_remove_phantom_functions_returns_none_for_phantom(self) -> None:
        """RemovePhantomFunctionsRule returns None when raw_text lacks CREATE FUNCTION."""
        rule = RemovePhantomFunctionsRule()
        # Phantom: SQLFunction but raw_text is comment or table
        element = SQLFunction(
            name="fake_func",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE users (id INT);",
        )
        result = rule.apply(element, {"source_code": ""})
        assert result is None

    def test_remove_phantom_functions_returns_element_for_valid(self) -> None:
        """RemovePhantomFunctionsRule returns element when raw_text contains CREATE FUNCTION."""
        rule = RemovePhantomFunctionsRule()
        element = SQLFunction(
            name="my_func",
            start_line=1,
            end_line=10,
            raw_text="CREATE FUNCTION my_func() RETURNS INT BEGIN RETURN 1; END;",
        )
        result = rule.apply(element, {"source_code": ""})
        assert result is element

    def test_remove_phantom_functions_passes_non_function_through(self) -> None:
        """RemovePhantomFunctionsRule passes through non-SQLFunction elements."""
        rule = RemovePhantomFunctionsRule()
        element = SQLTrigger(
            name="my_trigger",
            start_line=1,
            end_line=5,
            raw_text="CREATE TRIGGER my_trigger BEFORE INSERT ON t",
        )
        result = rule.apply(element, {"source_code": ""})
        assert result is element
