#!/usr/bin/env python3
"""Branch coverage tests for LegacyTableFormatter — signature branches, type abbreviations, doc helpers."""


import tree_sitter_analyzer.formatters  # noqa: F401
from tree_sitter_analyzer.legacy_table_formatter import (
    LegacyTableFormatter,
)


class TestCreateFullSignatureBranches:
    """Cover _create_full_signature with static, string/fallback params."""

    def test_static_method_signature(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        result = formatter._create_full_signature(
            {
                "name": "main",
                "parameters": [],
                "return_type": "void",
                "is_static": True,
            }
        )
        assert "[static]" in result
        assert "):void" in result

    def test_string_param_signature(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        result = formatter._create_full_signature(
            {
                "name": "foo",
                "parameters": ["String msg"],
                "return_type": "int",
            }
        )
        assert "String msg" in result
        assert ":int" in result

    def test_fallback_param_signature(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        result = formatter._create_full_signature(
            {
                "name": "foo",
                "parameters": [None],
                "return_type": "void",
            }
        )
        assert "None" in result


# ============================================================================
# Coverage boost: _abbreviate_type generics and arrays (608-618)
# ============================================================================


class TestAbbreviateTypeAdvanced:
    """Cover _abbreviate_type generic and array branches."""

    def test_generic_type_map(self) -> None:
        formatter = LegacyTableFormatter(format_type="compact")
        result = formatter._abbreviate_type("Map<String, Object>")
        assert result == "M<S, O>"

    def test_generic_type_custom(self) -> None:
        formatter = LegacyTableFormatter(format_type="compact")
        result = formatter._abbreviate_type("Custom<String>")
        assert result.startswith("C<")

    def test_array_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="compact")
        result = formatter._abbreviate_type("String[]")
        assert result == "S[]"

    def test_empty_string_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="compact")
        result = formatter._abbreviate_type("")
        assert result == "?"

    def test_unknown_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="compact")
        result = formatter._abbreviate_type("CustomType")
        assert result == "C"


# ============================================================================
# Coverage boost: _shorten_type branches (883-926)
# ============================================================================


class TestShortenTypeBranches:
    """Cover _shorten_type edge cases."""

    def test_none_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        assert formatter._shorten_type(None) == "O"

    def test_non_string_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        assert formatter._shorten_type(42) == "42"

    def test_map_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        result = formatter._shorten_type("Map<String,Object>")
        assert result == "M<S,O>"

    def test_list_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        result = formatter._shorten_type("List<String>")
        assert result == "L<S>"

    def test_array_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        result = formatter._shorten_type("String[]")
        assert result == "S[]"

    def test_empty_array_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        result = formatter._shorten_type("[]")
        assert result == "O[]"

    def test_unmapped_type(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        result = formatter._shorten_type("MyCustomType")
        assert result == "MyCustomType"


# ============================================================================
# Coverage boost: _extract_doc_summary and _clean_csv_text
# ============================================================================


class TestDocSummaryAndCSVText:
    """Cover _extract_doc_summary and _clean_csv_text edge cases."""

    def test_extract_doc_with_javadoc(self) -> None:
        formatter = LegacyTableFormatter(include_javadoc=True)
        result = formatter._extract_doc_summary("/**This is a test. More text.*/")
        assert "This is a test" in result

    def test_extract_doc_empty(self) -> None:
        formatter = LegacyTableFormatter()
        assert formatter._extract_doc_summary("") == "-"
