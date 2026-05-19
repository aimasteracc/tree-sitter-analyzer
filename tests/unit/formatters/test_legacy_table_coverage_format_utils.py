#!/usr/bin/env python3
"""
Coverage boost 2 tests for LegacyTableFormatter.

Targets uncovered branches in:
- _get_platform_newline (Windows), _convert_to_platform_newlines
- _format_full_table header edge cases (package+no classes, no file_path+package)
- _format_full_table multi-class param types (string, fallback)
- _format_full_table multi-class fields section
- _format_class_details with fields/constructors/methods + include_javadoc
- _format_method_row_detailed, _create_compact_signature
- _abbreviate_type generics + arrays
- _get_visibility_symbol
- _format_csv field rows, method rows
- _create_full_signature string/fallback params, is_static
- _shorten_type Map, List, array, None, non-string
- _convert_visibility, _extract_doc_summary, _clean_csv_text
- _format_compact_table classes=None, package branch
"""

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
        assert "+" in row
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


class TestCompactTableEdgeCases:
    """Tests for _format_compact_table edge cases."""

    def test_classes_is_none(self) -> None:
        """Lines 640-641: classes is None -> classes = []."""
        formatter = LegacyTableFormatter(format_type="compact")
        data = {"classes": None, "methods": [], "fields": []}
        result = formatter.format_structure(data)
        assert "# Unknown" in result

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
        formatter = LegacyTableFormatter(format_type="compact")
        data = {"classes": [], "methods": [], "fields": []}
        result = formatter.format_structure(data)
        assert "# Unknown" in result

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


class TestCsvFormat:
    """Tests for _format_csv method rows and field rows."""

    def test_csv_with_fields(self) -> None:
        """CSV output with field rows (lines 787-801)."""
        formatter = LegacyTableFormatter(format_type="csv")
        data = {
            "classes": [{"name": "Test"}],
            "fields": [
                {
                    "name": "id",
                    "type": "int",
                    "visibility": "private",
                    "modifiers": [],
                    "line_range": {"start": 3},
                },
                {
                    "name": "COUNT",
                    "type": "int",
                    "visibility": "public",
                    "modifiers": ["static", "final"],
                    "is_static": True,
                    "is_final": True,
                    "line_range": {"start": 5},
                },
            ],
            "methods": [],
        }
        result = formatter.format_structure(data)
        assert "field" in result
        assert "id" in result
        assert "COUNT" in result

    def test_csv_fields_modifier_fallback(self) -> None:
        """Field static/final via is_static/is_final attributes."""
        formatter = LegacyTableFormatter(format_type="csv")
        data = {
            "classes": [{"name": "Test"}],
            "fields": [
                {
                    "name": "VAL",
                    "type": "String",
                    "visibility": "public",
                    "modifiers": [],
                    "is_static": True,
                    "is_final": True,
                    "line_range": {"start": 7},
                },
            ],
            "methods": [],
        }
        result = formatter.format_structure(data)
        assert "VAL" in result

    def test_csv_with_methods_and_fields(self) -> None:
        """CSV output with both methods and fields."""
        formatter = LegacyTableFormatter(format_type="csv")
        data = {
            "classes": [{"name": "Demo"}],
            "methods": [
                {
                    "name": "go",
                    "parameters": [{"type": "String", "name": "arg"}],
                    "return_type": "boolean",
                    "visibility": "public",
                    "modifiers": [],
                    "line_range": {"start": 10},
                },
            ],
            "fields": [
                {
                    "name": "x",
                    "type": "int",
                    "visibility": "private",
                    "modifiers": [],
                    "line_range": {"start": 3},
                },
            ],
        }
        result = formatter.format_structure(data)
        assert "method" in result
        assert "field" in result
        assert "go" in result
        assert "x" in result

    def test_csv_with_parameter_types(self) -> None:
        """CSV method row with parameters (line 776)."""
        formatter = LegacyTableFormatter(format_type="csv")
        data = {
            "classes": [{"name": "CsvTest"}],
            "methods": [
                {
                    "name": "process",
                    "parameters": [
                        {"type": "String", "name": "input"},
                        {"type": "int", "name": "count"},
                    ],
                    "return_type": "boolean",
                    "visibility": "public",
                    "modifiers": [],
                    "is_static": False,
                    "is_final": False,
                    "line_range": {"start": 10},
                },
            ],
            "fields": [],
        }
        result = formatter.format_structure(data)
        assert "process" in result
        assert "boolean" in result


class TestCreateFullSignature:
    """Tests for _create_full_signature with all parameter types."""

    def test_string_parameter(self) -> None:
        """Lines 825-827: string parameter (not dict)."""
        formatter = LegacyTableFormatter()
        method = {
            "parameters": ["int x", "String y"],
            "return_type": "void",
        }
        sig = formatter._create_full_signature(method)
        assert "int x" in sig
        assert "String y" in sig

    def test_fallback_parameter(self) -> None:
        """Lines 828-830: fallback for non-dict non-string params."""
        formatter = LegacyTableFormatter()
        method = {
            "parameters": [123],
            "return_type": "void",
        }
        sig = formatter._create_full_signature(method)
        assert "123" in sig

    def test_static_method(self) -> None:
        """Lines 836-837, 842-843: static method modifier."""
        formatter = LegacyTableFormatter()
        method = {
            "parameters": [],
            "return_type": "MyClass",
            "is_static": True,
        }
        sig = formatter._create_full_signature(method)
        assert "[static]" in sig

    def test_non_static_method(self) -> None:
        """Line 842: modifier_str empty -> no modifier."""
        formatter = LegacyTableFormatter()
        method = {
            "parameters": [],
            "return_type": "void",
            "is_static": False,
        }
        sig = formatter._create_full_signature(method)
        assert "[static]" not in sig

    def test_mixed_parameter_types(self) -> None:
        """Mix of dict, string, and other parameters."""
        formatter = LegacyTableFormatter()
        method = {
            "parameters": [
                {"type": "String", "name": "a"},
                "int b",
                42,
            ],
            "return_type": "boolean",
        }
        sig = formatter._create_full_signature(method)
        assert "a:String" in sig
        assert "int b" in sig
        assert "42" in sig


class TestShortenType:
    """Tests for _shorten_type with all branches."""

    def test_none_type(self) -> None:
        """Lines 849-850: type_name is None -> 'O'."""
        formatter = LegacyTableFormatter()
        assert formatter._shorten_type(None) == "O"

    def test_non_string_type(self) -> None:
        """Lines 853-854: non-string type_name."""
        formatter = LegacyTableFormatter()
        assert formatter._shorten_type(123) == "123"

    def test_map_generic(self) -> None:
        """Lines 871-876: Map<String,Object> -> M<S,O>."""
        formatter = LegacyTableFormatter()
        result = formatter._shorten_type("Map<String,Object>")
        assert "M<" in result

    def test_list_generic(self) -> None:
        """Lines 879-880: List<String> -> L<S>."""
        formatter = LegacyTableFormatter()
        result = formatter._shorten_type("List<String>")
        assert "L<" in result

    def test_array_known_type(self) -> None:
        """Lines 883-886: String[] -> S[]."""
        formatter = LegacyTableFormatter()
        assert formatter._shorten_type("String[]") == "S[]"

    def test_array_unknown_type(self) -> None:
        formatter = LegacyTableFormatter()
        result = formatter._shorten_type("custom[]")
        assert result == "C[]"

    def test_empty_array(self) -> None:
        """Lines 887-888: '[]' with empty base -> 'O[]'."""
        formatter = LegacyTableFormatter()
        assert formatter._shorten_type("[]") == "O[]"

    def test_all_known_mappings(self) -> None:
        formatter = LegacyTableFormatter()
        assert formatter._shorten_type("String") == "S"
        assert formatter._shorten_type("int") == "i"
        assert formatter._shorten_type("long") == "l"
        assert formatter._shorten_type("double") == "d"
        assert formatter._shorten_type("boolean") == "b"
        assert formatter._shorten_type("void") == "void"
        assert formatter._shorten_type("Object") == "O"
        assert formatter._shorten_type("Exception") == "E"
        assert formatter._shorten_type("SQLException") == "SE"
        assert formatter._shorten_type("IllegalArgumentException") == "IAE"
        assert formatter._shorten_type("RuntimeException") == "RE"

    def test_unknown_type(self) -> None:
        formatter = LegacyTableFormatter()
        assert formatter._shorten_type("CustomType") == "CustomType"


class TestConvertVisibility:
    """Tests for _convert_visibility."""

    def test_all_values(self) -> None:
        formatter = LegacyTableFormatter()
        assert formatter._convert_visibility("public") == "+"
        assert formatter._convert_visibility("private") == "-"
        assert formatter._convert_visibility("protected") == "#"
        assert formatter._convert_visibility("package") == "~"
        assert formatter._convert_visibility("custom") == "custom"


class TestExtractDocSummary:
    """Tests for _extract_doc_summary."""

    def test_empty_javadoc(self) -> None:
        """Lines 899-900: empty javadoc -> '-'."""
        formatter = LegacyTableFormatter()
        assert formatter._extract_doc_summary("") == "-"

    def test_none_javadoc(self) -> None:
        formatter = LegacyTableFormatter()
        assert formatter._extract_doc_summary(None) == "-"

    def test_single_sentence(self) -> None:
        """Lines 908-911: javadoc with a single sentence."""
        formatter = LegacyTableFormatter()
        doc = "/** Returns the value. More details here. */"
        result = formatter._extract_doc_summary(doc)
        assert result == "Returns the value"

    def test_no_period(self) -> None:
        """Lines 908-913: javadoc without period."""
        formatter = LegacyTableFormatter()
        doc = "/** Get the name */"
        result = formatter._extract_doc_summary(doc)
        assert result == "Get the name"

    def test_multiline(self) -> None:
        formatter = LegacyTableFormatter()
        doc = "/**\n * Sets the value.\n * @param x the value\n */"
        result = formatter._extract_doc_summary(doc)
        assert result == "Sets the value"

    def test_with_return_tag(self) -> None:
        formatter = LegacyTableFormatter()
        doc = "/**\n * Get the user.\n * @return User\n */"
        result = formatter._extract_doc_summary(doc)
        assert "Get the user" in result


class TestCleanCsvText:
    """Tests for _clean_csv_text."""

    def test_empty_text(self) -> None:
        """Lines 917-918: empty text -> '-'."""
        formatter = LegacyTableFormatter()
        assert formatter._clean_csv_text("") == "-"

    def test_dash_text(self) -> None:
        """Lines 917-918: '-' -> '-'."""
        formatter = LegacyTableFormatter()
        assert formatter._clean_csv_text("-") == "-"

    def test_text_with_newlines(self) -> None:
        """Line 921: newlines collapsed."""
        formatter = LegacyTableFormatter()
        result = formatter._clean_csv_text("line1\nline2\nline3")
        assert result == "line1 line2 line3"

    def test_text_with_quotes(self) -> None:
        """Line 924: quotes doubled."""
        formatter = LegacyTableFormatter()
        result = formatter._clean_csv_text('He said "hello"')
        assert result == 'He said ""hello""'

    def test_extra_whitespace(self) -> None:
        formatter = LegacyTableFormatter()
        result = formatter._clean_csv_text("  too   many    spaces  ")
        assert result == "too many spaces"
