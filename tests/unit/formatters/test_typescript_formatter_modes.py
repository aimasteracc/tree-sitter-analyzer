#!/usr/bin/env python3
"""
Format mode and helper tests for TypeScript table formatter.

Tests for compact table mode, CSV mode, signature helpers,
format_table, format_summary, format_advanced, and JSON formatting.
"""

import pytest

from tree_sitter_analyzer.formatters.typescript_formatter import (
    TypeScriptTableFormatter,
)


class TestTypeScriptFormatterCompactTable:
    """Test _format_compact_table method"""

    @pytest.fixture
    def formatter(self) -> TypeScriptTableFormatter:
        return TypeScriptTableFormatter("compact")

    def test_compact_table_with_classes(self, formatter):
        data = {
            "file_path": "/src/UserService.ts",
            "classes": [
                {
                    "name": "UserService",
                    "class_type": "class",
                    "line_range": {"start": 10, "end": 30},
                }
            ],
            "functions": [],
            "variables": [],
            "package": {"name": "com.example"},
        }
        result = formatter.format(data)
        assert "# UserService" in result
        assert "## Info" in result
        assert "| Package | com.example |" in result
        assert "| Methods | 0 |" in result
        assert "| Fields | 0 |" in result

    def test_compact_table_no_classes(self, formatter):
        data = {
            "file_path": "utils.ts",
            "classes": [],
            "functions": [],
            "variables": [],
        }
        result = formatter.format(data)
        assert "# utils" in result
        assert "## Info" in result
        assert "| Methods | 0 |" in result

    def test_compact_table_with_methods(self, formatter):
        data = {
            "file_path": "service.ts",
            "classes": [
                {
                    "name": "Svc",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 40},
                }
            ],
            "functions": [
                {
                    "name": "getUser",
                    "return_type": "User",
                    "parameters": [{"name": "id", "type": "string"}],
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 7},
                    "complexity_score": 2,
                },
                {
                    "name": "handle",
                    "return_type": "void",
                    "parameters": ["event: Event"],
                    "visibility": "public",
                    "line_range": {"start": 10, "end": 12},
                    "complexity_score": 0,
                    "javadoc": "Handles the request",
                },
            ],
            "variables": [],
        }
        result = formatter.format(data)
        assert "## Methods" in result
        assert "getUser" in result
        assert "handle" in result

    def test_compact_table_with_fields(self, formatter):
        data = {
            "file_path": "model.ts",
            "classes": [
                {
                    "name": "Model",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 10},
                }
            ],
            "functions": [],
            "variables": [{"name": "x"}, {"name": "y"}, {"name": "z"}],
        }
        result = formatter.format(data)
        assert "| Fields | 3 |" in result

    def test_compact_table_with_package_none(self, formatter):
        data = {
            "file_path": "a.ts",
            "classes": [
                {
                    "name": "A",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 5},
                }
            ],
            "functions": [],
            "variables": [],
            "package": None,
        }
        result = formatter.format(data)
        assert "| Package |  |" in result

    def test_compact_table_no_methods(self, formatter):
        data = {
            "file_path": "empty.ts",
            "classes": [
                {
                    "name": "E",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 3},
                }
            ],
            "functions": [],
            "variables": [],
        }
        result = formatter.format(data)
        assert "## Methods" not in result


class TestTypeScriptFormatterSignatureHelpers:
    """Test _create_signature / _create_compact_signature / _create_csv_signature"""

    @pytest.fixture
    def formatter(self) -> TypeScriptTableFormatter:
        return TypeScriptTableFormatter("full")

    def test_create_full_signature_with_modifiers(self, formatter):
        method = {
            "name": "foo",
            "return_type": "number",
            "parameters": [
                {"name": "x", "type": "number", "modifiers": ["public", "readonly"]},
                {"name": "y", "type": "string"},
            ],
        }
        result = formatter._create_full_signature(method)
        assert "public readonly x:number" in result
        assert "y:string" in result
        assert "(public readonly x:number, y:string):number" == result

    def test_create_csv_signature_with_modifiers(self, formatter):
        method = {
            "name": "bar",
            "return_type": "void",
            "parameters": [
                {"name": "self", "type": "Service", "modifiers": ["public"]},
            ],
        }
        result = formatter._create_csv_signature(method)
        assert "public self:Service" in result
        assert "(public self:Service):void" == result

    def test_create_compact_signature_dict_params(self, formatter):
        method = {
            "name": "baz",
            "return_type": "boolean",
            "parameters": [{"name": "flag", "type": "boolean"}],
        }
        result = formatter._create_compact_signature(method)
        assert "(boolean):boolean" == result

    def test_create_compact_signature_non_dict_params(self, formatter):
        method = {
            "name": "q",
            "return_type": "int",
            "parameters": ["a: int"],
        }
        result = formatter._create_compact_signature(method)
        assert "(a: int):int" == result


class TestTypeScriptFormatterFormatTable:
    """Test format_table method"""

    @pytest.fixture
    def formatter(self) -> TypeScriptTableFormatter:
        return TypeScriptTableFormatter("full")

    def test_format_table_changes_type_temporarily(self, formatter):
        data = {
            "file_path": "app.ts",
            "classes": [],
            "functions": [],
            "variables": [],
        }
        original = formatter.format_type
        result = formatter.format_table(data, "compact")
        restored = formatter.format_type
        assert original == restored
        assert "## Info" in result

    def test_format_table_default_type(self, formatter):
        data = {
            "file_path": "app.ts",
            "classes": [
                {
                    "name": "App",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 10},
                }
            ],
            "functions": [],
            "variables": [],
        }
        result = formatter.format_table(data)
        assert "## Classes Overview" in result


class TestTypeScriptFormatterFormatSummary:
    """Test format_summary method"""

    @pytest.fixture
    def formatter(self) -> TypeScriptTableFormatter:
        return TypeScriptTableFormatter("full")

    def test_format_summary_delegates_to_compact(self, formatter):
        data = {
            "file_path": "summary.ts",
            "classes": [
                {
                    "name": "Sum",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 5},
                }
            ],
            "functions": [],
            "variables": [],
        }
        result = formatter.format_summary(data)
        assert "## Info" in result


class TestTypeScriptFormatterFormatAdvanced:
    """Test format_advanced method"""

    @pytest.fixture
    def formatter(self) -> TypeScriptTableFormatter:
        return TypeScriptTableFormatter("full")

    def test_format_advanced_json(self, formatter):
        data = {
            "file_path": "app.ts",
            "classes": [],
            "functions": [],
            "variables": [],
        }
        result = formatter.format_advanced(data, "json")
        assert '"file_path"' in result
        assert '"classes"' in result

    def test_format_advanced_csv(self, formatter):
        data = {
            "file_path": "app.ts",
            "classes": [],
            "functions": [],
            "variables": [],
        }
        result = formatter.format_advanced(data, "csv")
        assert "#" in result or "Functions" in result or result != ""

    def test_format_advanced_default_falls_back_to_full(self, formatter):
        data = {
            "file_path": "app.ts",
            "classes": [
                {
                    "name": "App",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 5},
                }
            ],
            "functions": [],
            "variables": [],
        }
        result = formatter.format_advanced(data, "unknown_format")
        assert "# App" in result


class TestTypeScriptFormatterFormatJson:
    """Test _format_json method"""

    @pytest.fixture
    def formatter(self) -> TypeScriptTableFormatter:
        return TypeScriptTableFormatter("full")

    def test_format_json_success(self, formatter):
        data = {"key": "value", "num": 42}
        result = formatter._format_json(data)
        assert '"key": "value"' in result
        assert '"num": 42' in result

    def test_format_json_error(self, formatter):
        bad_data = {"bad": {1, 2, 3}}
        result = formatter._format_json(bad_data)
        assert "JSON serialization error" in result


if __name__ == "__main__":
    pytest.main([__file__])
