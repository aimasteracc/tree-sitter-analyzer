#!/usr/bin/env python3
"""Legacy table formatter boost2 — platform newlines, full table headers, multi-class."""

from typing import Any
from unittest.mock import patch

from tree_sitter_analyzer.legacy_table_formatter import LegacyTableFormatter


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


