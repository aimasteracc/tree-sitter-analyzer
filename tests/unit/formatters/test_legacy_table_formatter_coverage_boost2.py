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

from typing import Any
from unittest.mock import patch

from tree_sitter_analyzer.legacy_table_formatter import LegacyTableFormatter

# ============================================================================
# Platform newline coverage (lines 49-50)
# ============================================================================


class TestPlatformNewlineWindows:
    """Tests for platform-specific newline on Windows (os.name == 'nt')."""

    def test_get_platform_newline_windows(self) -> None:
        """Test _get_platform_newline returns \\r\\n on Windows."""
        formatter = LegacyTableFormatter()
        with patch("os.name", "nt"):
            result = formatter._get_platform_newline()
            assert result == "\r\n"

    def test_convert_to_platform_newlines_on_windows(self) -> None:
        """Test _convert_to_platform_newlines converts \\n to \\r\\n on Windows."""
        formatter = LegacyTableFormatter()
        with patch.object(formatter, "_get_platform_newline", return_value="\r\n"):
            result = formatter._convert_to_platform_newlines("line1\nline2\nline3")
            assert result == "line1\r\nline2\r\nline3"


# ============================================================================
# _format_full_table header edge cases (lines 100-122)
# ============================================================================


class TestFullTableHeaderEdgeCases:
    """Tests for _format_full_table header generation edge cases."""

    def test_package_with_no_classes_and_file_path(self) -> None:
        """Line 114: package name + no classes + file path -> package.filename."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {
            "package": {"name": "com.example"},
            "classes": [],
            "file_path": "/src/MyFile.java",
        }
        result = formatter.format_structure(data)
        assert "# com.example.MyFile" in result

    def test_no_file_path_with_package(self) -> None:
        """Line 120: no file path + package -> package.Unknown."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {
            "package": {"name": "com.example"},
            "file_path": "",
        }
        result = formatter.format_structure(data)
        assert "# com.example.Unknown" in result

    def test_file_path_equals_unknown_string(self) -> None:
        """file_path == 'Unknown' should fall to default."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {
            "file_path": "Unknown",
            "package": {"name": "com.example"},
        }
        result = formatter.format_structure(data)
        assert "# com.example.Unknown" in result

    def test_python_file_header(self) -> None:
        """Test .py extension stripping in header."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {
            "classes": [],
            "file_path": "/src/my_module.py",
            "package": {"name": "mypackage"},
        }
        result = formatter.format_structure(data)
        assert "# mypackage.my_module" in result

    def test_js_file_header(self) -> None:
        """Test .js extension stripping in header."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {
            "classes": [],
            "file_path": "/src/app.js",
            "package": {"name": "mypackage"},
        }
        result = formatter.format_structure(data)
        assert "# mypackage.app" in result


# ============================================================================
# _format_full_table multi-class param types (lines 239-247)
# ============================================================================


class TestFullTableMultiClassParamTypes:
    """Tests for _format_full_table with multiple classes (param type branches)."""

    def _make_multi_data(self, methods) -> dict[str, Any]:
        return {
            "classes": [
                {
                    "name": "Outer",
                    "line_range": {"start": 1, "end": 100},
                    "type": "class",
                    "visibility": "public",
                },
                {
                    "name": "Inner",
                    "line_range": {"start": 40, "end": 60},
                    "type": "class",
                    "visibility": "private",
                },
            ],
            "methods": methods,
        }

    def test_string_parameter(self) -> None:
        """Lines 244-245: string parameters in multi-class path."""
        formatter = LegacyTableFormatter(format_type="full")
        data = self._make_multi_data(
            [
                {
                    "name": "foo",
                    "parameters": ["int x", "String y"],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 10},
                },
            ]
        )
        result = formatter.format_structure(data)
        assert "int x, String y" in result

    def test_fallback_parameter_non_dict_non_string(self) -> None:
        """Lines 246-247: fallback for non-dict non-string params."""
        formatter = LegacyTableFormatter(format_type="full")
        data = self._make_multi_data(
            [
                {
                    "name": "bar",
                    "parameters": [42],
                    "return_type": "int",
                    "visibility": "public",
                    "line_range": {"start": 12},
                },
            ]
        )
        result = formatter.format_structure(data)
        assert "42" in result

    def test_mixed_param_types(self) -> None:
        """Mix of dict, string, and other params."""
        formatter = LegacyTableFormatter(format_type="full")
        data = self._make_multi_data(
            [
                {
                    "name": "mixed",
                    "parameters": [
                        {"type": "String", "name": "a"},
                        "int x",
                        42,
                    ],
                    "return_type": "boolean",
                    "visibility": "public",
                    "line_range": {"start": 15},
                },
            ]
        )
        result = formatter.format_structure(data)
        assert "a" in result
        assert "int x" in result
        assert "42" in result

    def test_multi_class_fields_section(self) -> None:
        """Lines 259-286: multi-class fields with static/final modifiers."""
        formatter = LegacyTableFormatter(format_type="full")
        data = {
            "classes": [
                {
                    "name": "Outer",
                    "line_range": {"start": 1, "end": 100},
                    "type": "class",
                    "visibility": "public",
                },
            ],
            "fields": [
                {
                    "name": "count",
                    "type": "int",
                    "visibility": "private",
                    "modifiers": ["static", "final"],
                    "line_range": {"start": 5},
                },
            ],
        }
        # Need 2+ classes to trigger multi-class path
        data["classes"].append(
            {
                "name": "Inner",
                "line_range": {"start": 40, "end": 60},
                "type": "class",
                "visibility": "private",
            }
        )
        result = formatter.format_structure(data)
        assert "### Fields" in result
        assert "count" in result
        assert "true" in result  # static
        assert (
            "true" in result
        )  # final (only one "true" actually - let's just check count)


# ============================================================================
# _format_class_details (lines 449-534) + _format_method_row_detailed (536-550)
# NOTE: _format_class_details is NOT called by format_structure().
# Test it directly.
# ============================================================================


class TestFormatClassDetails:
    """Tests for _format_class_details via direct invocation."""

    def test_class_with_fields(self) -> None:
        """Lines 467-487: class with fields section."""
        formatter = LegacyTableFormatter(format_type="full")
        class_info = {
            "name": "MyClass",
            "type": "class",
            "visibility": "public",
            "line_range": {"start": 1, "end": 100},
        }
        data = {
            "fields": [
                {
                    "name": "count",
                    "type": "int",
                    "visibility": "private",
                    "modifiers": ["static"],
                    "line_range": {"start": 5},
                },
                {
                    "name": "name",
                    "type": "String",
                    "visibility": "public",
                    "modifiers": [],
                    "line_range": {"start": 10},
                },
            ],
        }
        lines = formatter._format_class_details(class_info, data)
        output = "\n".join(lines)
        assert "### Fields" in output
        assert "count" in output
        assert "name" in output

    def test_class_with_fields_and_javadoc(self) -> None:
        """Lines 478-482: fields with include_javadoc=True."""
        formatter = LegacyTableFormatter(format_type="full", include_javadoc=True)
        class_info = {"name": "DocClass", "line_range": {"start": 1, "end": 100}}
        data = {
            "fields": [
                {
                    "name": "id",
                    "type": "long",
                    "visibility": "private",
                    "modifiers": [],
                    "javadoc": "/** The unique identifier. */",
                    "line_range": {"start": 3},
                },
            ],
        }
        lines = formatter._format_class_details(class_info, data)
        output = "\n".join(lines)
        assert "### Fields" in output
        assert "The unique identifier" in output

    def test_class_with_constructors(self) -> None:
        """Lines 496-503: class with constructors section."""
        formatter = LegacyTableFormatter(format_type="full")
        class_info = {"name": "MyClass", "line_range": {"start": 1, "end": 100}}
        data = {
            "methods": [
                {
                    "name": "MyClass",
                    "is_constructor": True,
                    "parameters": [{"type": "String", "name": "name"}],
                    "return_type": "",
                    "visibility": "public",
                    "line_range": {"start": 10, "end": 15},
                },
                {
                    "name": "doWork",
                    "is_constructor": False,
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 20, "end": 25},
                },
            ],
        }
        lines = formatter._format_class_details(class_info, data)
        output = "\n".join(lines)
        assert "### Constructors" in output
        assert "MyClass" in output

    def test_class_with_constructors_and_javadoc(self) -> None:
        """Constructors with include_javadoc=True."""
        formatter = LegacyTableFormatter(format_type="full", include_javadoc=True)
        class_info = {"name": "Service", "line_range": {"start": 1, "end": 100}}
        data = {
            "methods": [
                {
                    "name": "Service",
                    "is_constructor": True,
                    "parameters": [],
                    "return_type": "",
                    "visibility": "public",
                    "javadoc": "/** Creates a new service. Initializes defaults. */",
                    "line_range": {"start": 5, "end": 10},
                    "complexity_score": 2,
                },
            ],
        }
        lines = formatter._format_class_details(class_info, data)
        output = "\n".join(lines)
        assert "### Constructors" in output
        assert "Creates a new service" in output

    def test_class_with_protected_methods(self) -> None:
        """Lines 509-510, 521: protected methods group."""
        formatter = LegacyTableFormatter(format_type="full")
        class_info = {"name": "Base", "line_range": {"start": 1, "end": 100}}
        data = {
            "methods": [
                {
                    "name": "init",
                    "is_constructor": False,
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "protected",
                    "line_range": {"start": 10, "end": 15},
                },
                {
                    "name": "cleanup",
                    "is_constructor": False,
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "protected",
                    "line_range": {"start": 20, "end": 25},
                },
            ],
        }
        lines = formatter._format_class_details(class_info, data)
        output = "\n".join(lines)
        assert "### Protected Methods" in output
        assert "init" in output
        assert "cleanup" in output

    def test_class_with_package_methods(self) -> None:
        """Lines 512-513, 522: package methods group."""
        formatter = LegacyTableFormatter(format_type="full")
        class_info = {"name": "Pkg", "line_range": {"start": 1, "end": 100}}
        data = {
            "methods": [
                {
                    "name": "packageMethod",
                    "is_constructor": False,
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "package",
                    "line_range": {"start": 30, "end": 35},
                },
            ],
        }
        lines = formatter._format_class_details(class_info, data)
        output = "\n".join(lines)
        assert "### Package Methods" in output
        assert "packageMethod" in output

    def test_class_with_private_methods(self) -> None:
        """Lines 515-517, 523: private methods group."""
        formatter = LegacyTableFormatter(format_type="full")
        class_info = {"name": "Helper", "line_range": {"start": 1, "end": 100}}
        data = {
            "methods": [
                {
                    "name": "helper",
                    "is_constructor": False,
                    "parameters": [],
                    "return_type": "int",
                    "visibility": "private",
                    "line_range": {"start": 40, "end": 45},
                },
            ],
        }
        lines = formatter._format_class_details(class_info, data)
        output = "\n".join(lines)
        assert "### Private Methods" in output
        assert "helper" in output

    def test_class_empty_fields(self) -> None:
        """Line 467: when class_fields is empty, skip fields section."""
        formatter = LegacyTableFormatter(format_type="full")
        class_info = {"name": "EmptyFields", "line_range": {"start": 1, "end": 50}}
        data = {}
        lines = formatter._format_class_details(class_info, data)
        output = "\n".join(lines)
        assert "### Fields" not in output

    def test_class_empty_constructors(self) -> None:
        """Line 496: when constructors list is empty, skip constructors."""
        formatter = LegacyTableFormatter(format_type="full")
        class_info = {"name": "NoCons", "line_range": {"start": 1, "end": 50}}
        data = {"methods": []}
        lines = formatter._format_class_details(class_info, data)
        output = "\n".join(lines)
        assert "### Constructors" not in output

    def test_all_visibility_groups(self) -> None:
        """All four visibility method groups present."""
        formatter = LegacyTableFormatter(format_type="full")
        class_info = {"name": "FullDemo", "line_range": {"start": 1, "end": 200}}
        data = {
            "fields": [
                {
                    "name": "data",
                    "type": "Object",
                    "visibility": "private",
                    "modifiers": [],
                    "line_range": {"start": 5},
                },
            ],
            "methods": [
                {
                    "name": "FullDemo",
                    "is_constructor": True,
                    "parameters": [{"type": "int", "name": "x"}],
                    "return_type": "",
                    "visibility": "public",
                    "line_range": {"start": 10, "end": 20},
                    "complexity_score": 3,
                },
                {
                    "name": "pubMethod",
                    "is_constructor": False,
                    "parameters": [],
                    "return_type": "String",
                    "visibility": "public",
                    "line_range": {"start": 30, "end": 40},
                    "complexity_score": 1,
                },
                {
                    "name": "protMethod",
                    "is_constructor": False,
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "protected",
                    "line_range": {"start": 50, "end": 55},
                },
                {
                    "name": "pkgMethod",
                    "is_constructor": False,
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "package",
                    "line_range": {"start": 60, "end": 65},
                },
                {
                    "name": "privMethod",
                    "is_constructor": False,
                    "parameters": [],
                    "return_type": "boolean",
                    "visibility": "private",
                    "line_range": {"start": 70, "end": 75},
                },
            ],
        }
        lines = formatter._format_class_details(class_info, data)
        output = "\n".join(lines)
        assert "### Fields" in output
        assert "### Constructors" in output
        assert "### Public Methods" in output
        assert "### Protected Methods" in output
        assert "### Package Methods" in output
        assert "### Private Methods" in output

    def test_public_methods_absent(self) -> None:
        """Line 525: public_methods empty, skip Public Methods."""
        formatter = LegacyTableFormatter(format_type="full")
        class_info = {"name": "PrivOnly", "line_range": {"start": 1, "end": 100}}
        data = {
            "methods": [
                {
                    "name": "doPrivate",
                    "is_constructor": False,
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "private",
                    "line_range": {"start": 10, "end": 15},
                },
            ],
        }
        lines = formatter._format_class_details(class_info, data)
        output = "\n".join(lines)
        assert "### Public Methods" not in output
        assert "### Private Methods" in output

    def test_include_javadoc_for_method(self) -> None:
        """Lines 544-548: method with include_javadoc=True."""
        formatter = LegacyTableFormatter(format_type="full", include_javadoc=True)
        class_info = {"name": "DocMethods", "line_range": {"start": 1, "end": 100}}
        data = {
            "methods": [
                {
                    "name": "process",
                    "is_constructor": False,
                    "parameters": [{"type": "String", "name": "input"}],
                    "return_type": "boolean",
                    "visibility": "public",
                    "javadoc": "/** Process the input. Returns success. */",
                    "line_range": {"start": 10, "end": 20},
                    "complexity_score": 5,
                },
            ],
        }
        lines = formatter._format_class_details(class_info, data)
        output = "\n".join(lines)
        assert "process" in output
        assert "Process the input" in output


# ============================================================================
# _format_method_row_detailed (lines 536-550)
# ============================================================================


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


# ============================================================================
# _format_csv (lines 705-813)
# ============================================================================


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


# ============================================================================
# _create_full_signature (lines 815-845)
# ============================================================================


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


# ============================================================================
# _shorten_type (lines 847-890)
# ============================================================================


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


# ============================================================================
# _convert_visibility (lines 892-895)
# ============================================================================


class TestConvertVisibility:
    """Tests for _convert_visibility."""

    def test_all_values(self) -> None:
        formatter = LegacyTableFormatter()
        assert formatter._convert_visibility("public") == "+"
        assert formatter._convert_visibility("private") == "-"
        assert formatter._convert_visibility("protected") == "#"
        assert formatter._convert_visibility("package") == "~"
        assert formatter._convert_visibility("custom") == "custom"


# ============================================================================
# _extract_doc_summary (lines 897-913)
# ============================================================================


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


# ============================================================================
# _clean_csv_text (lines 915-926)
# ============================================================================


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
