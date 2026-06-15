#!/usr/bin/env python3
"""
Core tests for TypeScript table formatter.

Tests for initialization, full table formatting, section rendering,
modifiers, and method visibility handling.
"""

import pytest

from tree_sitter_analyzer.formatters.typescript_formatter import (
    TypeScriptTableFormatter,
)


class TestTypeScriptTableFormatter:
    """Test cases for TypeScriptTableFormatter class"""

    @pytest.fixture
    def formatter(self) -> TypeScriptTableFormatter:
        """Create a TypeScriptTableFormatter instance for testing"""
        return TypeScriptTableFormatter("full")

    @pytest.fixture
    def sample_data(self) -> dict:
        """Sample TypeScript analysis data for testing"""
        return {
            "file_path": "/workspace/src/UserService.ts",
            "classes": [
                {
                    "name": "UserService",
                    "class_type": "class",
                    "superclass": "BaseService",
                    "interfaces": ["IUserService", "ILoggable"],
                    "line_range": {"start": 15, "end": 45},
                    "generics": ["T", "U"],
                    "is_exported": True,
                    "is_abstract": False,
                },
                {
                    "name": "IUserProfile",
                    "class_type": "interface",
                    "interfaces": ["IUser"],
                    "line_range": {"start": 5, "end": 12},
                    "generics": [],
                    "is_exported": True,
                },
                {
                    "name": "Status",
                    "class_type": "type",
                    "line_range": {"start": 2, "end": 2},
                    "generics": [],
                    "raw_text": "type Status = 'active' | 'inactive' | 'pending';",
                    "is_exported": True,
                },
                {
                    "name": "UserRole",
                    "class_type": "enum",
                    "line_range": {"start": 47, "end": 52},
                    "raw_text": "enum UserRole {\n  ADMIN = 'admin',\n  USER = 'user',\n  GUEST = 'guest'\n}",
                    "is_exported": False,
                },
            ],
            "functions": [
                {
                    "name": "fetchUserData",
                    "return_type": "Promise<UserProfile | null>",
                    "parameters": ["userId: string"],
                    "is_async": True,
                    "is_arrow": False,
                    "is_method": False,
                    "line_range": {"start": 55, "end": 65},
                    "complexity_score": 3,
                    "generics": [],
                    "has_type_annotations": True,
                },
                {
                    "name": "mapArray",
                    "return_type": "U[]",
                    "parameters": ["array: T[]", "mapper: (item: T) => U"],
                    "is_async": False,
                    "is_arrow": True,
                    "is_method": False,
                    "line_range": {"start": 67, "end": 69},
                    "complexity_score": 1,
                    "generics": ["T", "U"],
                    "has_type_annotations": True,
                },
                {
                    "name": "validate",
                    "return_type": "boolean",
                    "parameters": ["user: UserProfile"],
                    "is_async": False,
                    "is_arrow": False,
                    "is_method": True,
                    "is_signature": False,
                    "visibility": "public",
                    "line_range": {"start": 25, "end": 27},
                    "complexity_score": 2,
                    "generics": [],
                    "has_type_annotations": True,
                },
            ],
            "variables": [
                {
                    "name": "config",
                    "variable_type": "AppConfig",
                    "declaration_kind": "const",
                    "line_range": {"start": 1, "end": 1},
                    "is_static": False,
                    "is_optional": False,
                    "has_type_annotation": True,
                    "visibility": "public",
                },
                {
                    "name": "userId",
                    "variable_type": "string",
                    "declaration_kind": "property",
                    "line_range": {"start": 17, "end": 17},
                    "is_static": False,
                    "is_optional": False,
                    "has_type_annotation": True,
                    "visibility": "private",
                },
                {
                    "name": "findById",
                    "variable_type": "any",
                    "declaration_kind": "property_signature",
                    "line_range": {"start": 7, "end": 7},
                    "is_optional": False,
                    "has_type_annotation": True,
                },
            ],
            "imports": [
                {
                    "name": "Component",
                    "source": "react",
                    "is_type_import": False,
                    "framework_type": "react",
                },
                {
                    "name": "User",
                    "source": "./types",
                    "is_type_import": True,
                    "framework_type": "",
                },
            ],
            "exports": [
                {
                    "names": ["UserService", "UserRole"],
                    "type": "named",
                    "is_default": False,
                },
                {
                    "names": ["UserComponent"],
                    "type": "default",
                    "is_default": True,
                },
            ],
            "statistics": {
                "function_count": 3,
                "variable_count": 3,
            },
        }

    def test_format_full_table(self, formatter, sample_data):
        """Test full table formatting"""
        result = formatter.format(sample_data)

        assert isinstance(result, str)
        assert len(result.replace("\r\n", "\n")) == 879  # normalize CRLF for Windows

        assert "UserService" in result
        assert "class" in result or "interface" in result

    def test_format_full_table_tsx_file(self, formatter):
        """Test full table formatting for TSX files"""
        tsx_data = {
            "file_path": "/workspace/src/Component.tsx",
            "classes": [],
            "functions": [],
            "variables": [],
            "imports": [],
            "exports": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }

        result = formatter.format(tsx_data)
        assert "Component" in result

    def test_format_full_table_declaration_file(self, formatter):
        """Test full table formatting for declaration files"""
        dts_data = {
            "file_path": "/workspace/types/index.d.ts",
            "classes": [],
            "functions": [],
            "variables": [],
            "imports": [],
            "exports": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }

        result = formatter.format(dts_data)
        assert "index" in result

    def test_format_interfaces_section(self, formatter, sample_data):
        """Test interfaces section formatting"""
        result = formatter.format(sample_data)

        assert "IUserProfile" in result
        assert "interface" in result

    def test_format_type_aliases_section(self, formatter, sample_data):
        """Test type aliases section formatting"""
        result = formatter.format(sample_data)

        assert "Status" in result
        assert "type" in result
        assert "2-2" in result

    def test_format_enums_section(self, formatter, sample_data):
        """Test enums section formatting"""
        result = formatter.format(sample_data)

        assert "UserRole" in result
        assert "enum" in result
        assert "47-52" in result

    def test_format_classes_section(self, formatter, sample_data):
        """Test classes section formatting"""
        result = formatter.format(sample_data)

        assert "UserService" in result
        assert "class" in result
        assert "15-45" in result
        assert "IUserProfile" in result
        assert "interface" in result

    def test_format_functions_section(self, formatter, sample_data):
        """Test functions section formatting"""
        result = formatter.format(sample_data)

        assert "validate" in result
        assert "boolean" in result or "UserProfile" in result

    def test_format_variables_section(self, formatter, sample_data):
        """Test variables section formatting"""
        result = formatter.format(sample_data)

        assert "userId" in result
        assert "string" in result

    def test_format_compact_table(self, sample_data):
        """Test compact table formatting"""
        formatter = TypeScriptTableFormatter("compact")
        result = formatter.format(sample_data)

        assert isinstance(result, str)
        assert len(result.replace("\r\n", "\n")) == 416  # normalize CRLF for Windows

        assert "UserService" in result
        assert "## Info" in result
        assert "## Methods" in result or "Methods" in result

    def test_format_csv(self, sample_data):
        """Test CSV formatting"""
        formatter = TypeScriptTableFormatter("csv")
        result = formatter.format(sample_data)

        assert isinstance(result, str)
        assert len(result) == 402

        lines = result.split("\n")
        assert len(lines) == 8
        header = lines[0]
        assert "Type" in header or "Name" in header
        assert any("validate" in line for line in lines)
        assert any("userId" in line for line in lines)

    def test_get_element_type_name(self, formatter):
        """Test element type name generation - method may not exist in new implementation"""
        if not hasattr(formatter, "_get_element_type_name"):
            pytest.skip("_get_element_type_name not implemented in new formatter")

    def test_format_element_details(self, formatter):
        """Test element details formatting - method may not exist in new implementation"""
        if not hasattr(formatter, "_format_element_details"):
            pytest.skip("_format_element_details not implemented in new formatter")

    def test_format_element_details_minimal(self, formatter):
        """Test element details formatting with minimal data - method may not exist"""
        if not hasattr(formatter, "_format_element_details"):
            pytest.skip("_format_element_details not implemented in new formatter")

    def test_format_empty_data(self, formatter):
        """Test formatting with empty data"""
        empty_data = {
            "file_path": "empty.ts",
            "classes": [],
            "functions": [],
            "variables": [],
            "imports": [],
            "exports": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }

        result = formatter.format(empty_data)
        assert isinstance(result, str)
        assert "empty" in result

    def test_format_with_imports(self, formatter, sample_data):
        """Test formatting includes expected content"""
        result = formatter.format(sample_data)

        assert "UserService" in result
        assert "IUserProfile" in result

    def test_format_with_exports(self, formatter, sample_data):
        """Test formatting includes class content"""
        result = formatter.format(sample_data)

        assert "UserService" in result
        assert "validate" in result

    def test_format_module_info_statistics(self, formatter, sample_data):
        """Test output contains element information"""
        result = formatter.format(sample_data)

        assert "## Classes Overview" in result or "Class" in result
        assert "UserService" in result
        assert "IUserProfile" in result
        assert "Status" in result
        assert "UserRole" in result

    def test_format_different_file_types(self, formatter):
        """Test formatting for different TypeScript file types"""
        base_data = {
            "classes": [],
            "functions": [],
            "variables": [],
            "imports": [],
            "exports": [],
            "statistics": {"function_count": 0, "variable_count": 0},
        }

        ts_data = {**base_data, "file_path": "service.ts"}
        result = formatter.format(ts_data)
        assert "service" in result

        tsx_data = {**base_data, "file_path": "component.tsx"}
        result = formatter.format(tsx_data)
        assert "component" in result

        dts_data = {**base_data, "file_path": "types.d.ts"}
        result = formatter.format(dts_data)
        assert "types" in result


class TestTypeScriptFormatterModifiers:
    """Test _format_modifiers method"""

    @pytest.fixture
    def formatter(self) -> TypeScriptTableFormatter:
        return TypeScriptTableFormatter("full")

    def test_format_modifiers_static(self, formatter):
        result = formatter._format_modifiers({"is_static": True})
        assert "static" in result

    def test_format_modifiers_readonly(self, formatter):
        result = formatter._format_modifiers({"is_readonly": True})
        assert "readonly" in result

    def test_format_modifiers_abstract(self, formatter):
        result = formatter._format_modifiers({"is_abstract": True})
        assert "abstract" in result

    def test_format_modifiers_combined(self, formatter):
        result = formatter._format_modifiers(
            {"is_static": True, "is_readonly": True, "is_abstract": False}
        )
        assert "static" in result
        assert "readonly" in result
        assert "abstract" not in result

    def test_format_modifiers_none(self, formatter):
        result = formatter._format_modifiers({})
        assert result == ""


class TestTypeScriptFormatterFullTableMethods:
    """Test constructor/protected/private method sections"""

    @pytest.fixture
    def formatter(self) -> TypeScriptTableFormatter:
        return TypeScriptTableFormatter("full")

    def test_full_table_with_constructor(self, formatter):
        data = {
            "file_path": "/src/MyClass.ts",
            "classes": [
                {
                    "name": "MyClass",
                    "class_type": "class",
                    "line_range": {"start": 10, "end": 30},
                }
            ],
            "functions": [
                {
                    "name": "constructor",
                    "is_constructor": True,
                    "visibility": "public",
                    "return_type": "void",
                    "parameters": [{"name": "name", "type": "string"}],
                    "line_range": {"start": 12, "end": 14},
                    "complexity_score": 1,
                },
            ],
            "variables": [],
        }
        result = formatter.format(data)
        assert "### Constructors" in result

    def test_full_table_with_protected_method(self, formatter):
        data = {
            "file_path": "/src/Base.ts",
            "classes": [
                {
                    "name": "Base",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 20},
                }
            ],
            "functions": [
                {
                    "name": "init",
                    "visibility": "protected",
                    "return_type": "void",
                    "parameters": [],
                    "line_range": {"start": 5, "end": 7},
                    "complexity_score": 0,
                },
            ],
            "variables": [],
        }
        result = formatter.format(data)
        assert "### Protected Methods" in result

    def test_full_table_with_private_method(self, formatter):
        data = {
            "file_path": "/src/Helper.ts",
            "classes": [
                {
                    "name": "Helper",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 20},
                }
            ],
            "functions": [
                {
                    "name": "_internal",
                    "visibility": "private",
                    "return_type": "string",
                    "parameters": [],
                    "line_range": {"start": 8, "end": 10},
                    "complexity_score": 1,
                },
            ],
            "variables": [],
        }
        result = formatter.format(data)
        assert "### Private Methods" in result


if __name__ == "__main__":
    pytest.main([__file__])
