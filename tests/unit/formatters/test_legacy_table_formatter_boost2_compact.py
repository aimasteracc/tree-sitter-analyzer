#!/usr/bin/env python3
"""Legacy table formatter boost2 — compact signatures, abbreviate, visibility, compact table."""

from tree_sitter_analyzer.legacy_table_formatter import LegacyTableFormatter


class TestFormatMethodRowDetailed:
    """Tests for _format_method_row_detailed."""

    def test_basic(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        method = {
            "name": "doWork",
            "parameters": [{"type": "String", "name": "input"}],
            "return_type": "boolean",
            "visibility": "public",
            "line_range": {"start": 10, "end": 20},
            "complexity_score": 5,
        }
        row = formatter._format_method_row_detailed(method)
        assert "doWork" in row
        assert "+" in row  # visibility converted to symbol
        assert "10-20" in row
        assert "5" in row

    def test_with_javadoc_enabled(self) -> None:
        formatter = LegacyTableFormatter(format_type="full", include_javadoc=True)
        method = {
            "name": "process",
            "parameters": [],
            "return_type": "void",
            "visibility": "public",
            "line_range": {"start": 5, "end": 8},
            "complexity_score": 1,
            "javadoc": "/** The process method. */",
        }
        row = formatter._format_method_row_detailed(method)
        assert "The process method" in row

    def test_static_method(self) -> None:
        formatter = LegacyTableFormatter(format_type="full")
        method = {
            "name": "create",
            "parameters": [],
            "return_type": "MyClass",
            "visibility": "public",
            "is_static": True,
            "line_range": {"start": 15, "end": 20},
            "complexity_score": 2,
        }
        row = formatter._format_method_row_detailed(method)
        assert "[static]" in row


# ============================================================================
# _create_compact_signature (lines 566-580)
# ============================================================================


class TestCreateCompactSignature:
    """Tests for _create_compact_signature."""

    def test_with_params(self) -> None:
        """Lines 568-578: compact signature with parameters."""
        formatter = LegacyTableFormatter()
        method = {
            "parameters": [
                {"type": "String", "name": "a"},
                {"type": "int", "name": "b"},
            ],
            "return_type": "boolean",
        }
        result = formatter._create_compact_signature(method)
        assert "(S,i):b" in result

    def test_no_params(self) -> None:
        """Compact signature with no parameters."""
        formatter = LegacyTableFormatter()
        method = {
            "parameters": [],
            "return_type": "void",
        }
        result = formatter._create_compact_signature(method)
        assert result == "():void"


# ============================================================================
# _abbreviate_type (lines 595-620)
# ============================================================================


class TestAbbreviateType:
    """Tests for _abbreviate_type."""

    def test_standard_types(self) -> None:
        formatter = LegacyTableFormatter()
        assert formatter._abbreviate_type("int") == "i"
        assert formatter._abbreviate_type("String") == "S"
        assert formatter._abbreviate_type("void") == "void"
        assert formatter._abbreviate_type("boolean") == "b"

    def test_generic_type(self) -> None:
        """Lines 607-613: abbreviate generic type."""
        formatter = LegacyTableFormatter()
        result = formatter._abbreviate_type("Map<String, Object>")
        assert result in ("M<S, O>", "M<S,O>")

    def test_array_type(self) -> None:
        """Lines 616-618: abbreviate array type."""
        formatter = LegacyTableFormatter()
        assert formatter._abbreviate_type("String[]") == "S[]"

    def test_unknown_array(self) -> None:
        """Array of unknown type."""
        formatter = LegacyTableFormatter()
        result = formatter._abbreviate_type("Custom[]")
        assert result == "C[]"

    def test_empty_type(self) -> None:
        """Line 620: empty type -> '?'."""
        formatter = LegacyTableFormatter()
        assert formatter._abbreviate_type("") == "?"

    def test_exception_type(self) -> None:
        formatter = LegacyTableFormatter()
        assert formatter._abbreviate_type("Exception") == "E"


# ============================================================================
# _get_visibility_symbol (lines 622-631)
# ============================================================================


class TestGetVisibilitySymbol:
    """Tests for _get_visibility_symbol."""

    def test_all_symbols(self) -> None:
        formatter = LegacyTableFormatter()
        assert formatter._get_visibility_symbol("public") == "+"
        assert formatter._get_visibility_symbol("private") == "-"
        assert formatter._get_visibility_symbol("protected") == "#"
        assert formatter._get_visibility_symbol("package") == "~"
        assert formatter._get_visibility_symbol("internal") == "~"
        assert formatter._get_visibility_symbol("custom") == "+"
        assert formatter._get_visibility_symbol("PUBLIC") == "+"


# ============================================================================
# _format_compact_table edge cases (lines 633-665)
# ============================================================================


class TestCompactTableEdgeCases:
    """Tests for _format_compact_table edge cases."""

    def test_classes_is_none(self) -> None:
        """Bug #778 fixed: classes=None must not produce '# Unknown'."""
        formatter = LegacyTableFormatter(format_type="compact")
        data = {"classes": None, "methods": [], "fields": []}
        result = formatter.format_structure(data)
        assert "# Unknown" not in result

    def test_with_package_name(self) -> None:
        """Lines 645-646, 658-659: with package name."""
        formatter = LegacyTableFormatter(format_type="compact")
        data = {
            "classes": [{"name": "Test"}],
            "package": {"name": "com.example"},
            "methods": [
                {
                    "name": "run",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 5},
                },
            ],
            "fields": [],
        }
        result = formatter.format_structure(data)
        assert "# com.example.Test" in result
        assert "| Package | com.example |" in result

    def test_classes_empty_list(self) -> None:
        # Bug #778 fixed: empty classes list must not produce '# Unknown'.
        formatter = LegacyTableFormatter(format_type="compact")
        data = {"classes": [], "methods": [], "fields": []}
        result = formatter.format_structure(data)
        assert "# Unknown" not in result

    def test_compact_with_methods(self) -> None:
        """Compact table with methods (hits _format_compact_method_row)."""
        formatter = LegacyTableFormatter(format_type="compact")
        data = {
            "classes": [{"name": "Demo"}],
            "methods": [
                {
                    "name": "foo",
                    "parameters": [{"type": "String", "name": "x"}],
                    "return_type": "boolean",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 10},
                    "complexity_score": 3,
                },
            ],
            "fields": [],
        }
        result = formatter.format_structure(data)
        assert "foo" in result
        assert "3" in result

    def test_compact_with_fields(self) -> None:
        """Compact table with fields."""
        formatter = LegacyTableFormatter(format_type="compact")
        data = {
            "classes": [{"name": "Demo"}],
            "methods": [],
            "fields": [
                {
                    "name": "x",
                    "type": "int",
                    "visibility": "private",
                    "line_range": {"start": 3},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "## Fields" in result
        assert "x" in result


# ============================================================================
# _format_csv (lines 705-813)
# ============================================================================
