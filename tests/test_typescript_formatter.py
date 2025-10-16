#!/usr/bin/env python3
"""
Tests for TypeScript table formatter.

This module tests the TypeScriptTableFormatter class which provides
specialized formatting for TypeScript code analysis results.
"""

import pytest

from tree_sitter_analyzer.formatters.base_formatter import BaseTableFormatter
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

    def test_formatter_initialization(self):
        """Test formatter initialization with different format types"""
        full_formatter = TypeScriptTableFormatter("full")
        assert isinstance(full_formatter, TypeScriptTableFormatter)
        assert isinstance(full_formatter, BaseTableFormatter)

        compact_formatter = TypeScriptTableFormatter("compact")
        assert isinstance(compact_formatter, TypeScriptTableFormatter)

        csv_formatter = TypeScriptTableFormatter("csv")
        assert isinstance(csv_formatter, TypeScriptTableFormatter)

    def test_format_full_table(self, formatter, sample_data):
        """Test full table formatting"""
        result = formatter.format(sample_data)

        assert isinstance(result, str)
        assert len(result) > 0

        # Check for TypeScript-specific sections
        assert "# TypeScript Module: UserService" in result
        assert "## Module Info" in result
        assert "## Interfaces" in result
        assert "## Type Aliases" in result
        assert "## Enums" in result
        assert "## Classes" in result
        assert "## Functions" in result
        assert "## Variables & Properties" in result
        assert "## Exports" in result

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
        assert "# TSX Module: Component" in result

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
        assert "# Declaration File: index" in result

    def test_format_interfaces_section(self, formatter, sample_data):
        """Test interfaces section formatting"""
        result = formatter.format(sample_data)

        # Check interface table headers
        assert (
            "| Interface | Extends | Lines | Properties | Methods | Generics |"
            in result
        )

        # Check interface data
        assert "| IUserProfile | IUser | 5-12 | 1 | 0 | - |" in result

    def test_format_type_aliases_section(self, formatter, sample_data):
        """Test type aliases section formatting"""
        result = formatter.format(sample_data)

        # Check type alias table headers
        assert "| Type | Lines | Generics | Definition |" in result

        # Check type alias data
        assert "| Status | 2-2 | - |" in result
        assert "'active' | 'inactive' | 'pending'" in result

    def test_format_enums_section(self, formatter, sample_data):
        """Test enums section formatting"""
        result = formatter.format(sample_data)

        # Check enum table headers
        assert "| Enum | Lines | Values |" in result

        # Check enum data
        assert "| UserRole | 47-52 | 3 |" in result

    def test_format_classes_section(self, formatter, sample_data):
        """Test classes section formatting"""
        result = formatter.format(sample_data)

        # Check class table headers
        assert (
            "| Class | Type | Extends | Implements | Lines | Methods | Properties | Generics |"
            in result
        )

        # Check class data
        assert (
            "| UserService | class | BaseService | IUserService, ILoggable | 15-45 | 1 | 1 | T, U |"
            in result
        )

    def test_format_functions_section(self, formatter, sample_data):
        """Test functions section formatting"""
        result = formatter.format(sample_data)

        # Check function table headers
        assert (
            "| Function | Type | Return Type | Parameters | Async | Generic | Lines | Complexity |"
            in result
        )

        # Check function data
        assert (
            "| fetchUserData | function | Promise<UserProfile | null> | 1 | ✓ |  | 55-65 | 3 |"
            in result
        )
        assert "| mapArray | arrow | U[] | 2 |  | ✓ | 67-69 | 1 |" in result
        assert "| validate | method | boolean | 1 |  |  | 25-27 | 2 |" in result

    def test_format_variables_section(self, formatter, sample_data):
        """Test variables section formatting"""
        result = formatter.format(sample_data)

        # Check variable table headers
        assert (
            "| Name | Type | Kind | Visibility | Static | Optional | Lines |" in result
        )

        # Check variable data
        assert "| config | AppConfig | const | public |  |  | 1-1 |" in result
        assert "| userId | string | property | private |  |  | 17-17 |" in result
        assert "| findById | any | property_signature | public |  |  | 7-7 |" in result

    def test_format_compact_table(self, sample_data):
        """Test compact table formatting"""
        formatter = TypeScriptTableFormatter("compact")
        result = formatter.format(sample_data)

        assert isinstance(result, str)
        assert len(result) > 0

        # Check for compact format elements
        assert "# UserService.ts" in result
        assert "## Summary" in result
        assert "- **Classes**: 1" in result
        assert "- **Interfaces**: 1" in result
        assert "- **Type Aliases**: 1" in result
        assert "- **Enums**: 1" in result
        assert "- **Functions**: 3" in result
        assert "- **Variables**: 3" in result

    def test_format_csv(self, sample_data):
        """Test CSV formatting"""
        formatter = TypeScriptTableFormatter("csv")
        result = formatter.format(sample_data)

        assert isinstance(result, str)
        assert len(result) > 0

        # Check CSV headers
        assert (
            "Type,Name,Kind,Return/Type,Lines,Visibility,Static,Async,Generic" in result
        )

        # Check CSV data
        lines = result.split("\n")
        assert len(lines) > 1  # Should have header + data lines

        # Check for TypeScript-specific data
        assert any("Class,UserService,class" in line for line in lines)
        assert any("Function,fetchUserData,function" in line for line in lines)
        assert any("Variable,config,const" in line for line in lines)

    def test_get_element_type_name(self, formatter):
        """Test element type name generation"""
        # Test class types
        assert (
            formatter._get_element_type_name(
                {"element_type": "class", "class_type": "interface"}
            )
            == "Interface"
        )
        assert (
            formatter._get_element_type_name(
                {"element_type": "class", "class_type": "type"}
            )
            == "Type Alias"
        )
        assert (
            formatter._get_element_type_name(
                {"element_type": "class", "class_type": "enum"}
            )
            == "Enum"
        )
        assert (
            formatter._get_element_type_name(
                {"element_type": "class", "class_type": "abstract_class"}
            )
            == "Abstract Class"
        )
        assert (
            formatter._get_element_type_name(
                {"element_type": "class", "class_type": "class"}
            )
            == "Class"
        )

        # Test function types
        assert (
            formatter._get_element_type_name(
                {"element_type": "function", "is_arrow": True}
            )
            == "Arrow Function"
        )
        assert (
            formatter._get_element_type_name(
                {"element_type": "function", "is_method": True}
            )
            == "Method"
        )
        assert (
            formatter._get_element_type_name(
                {"element_type": "function", "is_constructor": True}
            )
            == "Constructor"
        )
        assert (
            formatter._get_element_type_name({"element_type": "function"}) == "Function"
        )

        # Test variable types
        assert (
            formatter._get_element_type_name(
                {"element_type": "variable", "declaration_kind": "property"}
            )
            == "Property"
        )
        assert (
            formatter._get_element_type_name(
                {"element_type": "variable", "declaration_kind": "property_signature"}
            )
            == "Property Signature"
        )
        assert (
            formatter._get_element_type_name({"element_type": "variable"}) == "Variable"
        )

        # Test other types
        assert formatter._get_element_type_name({"element_type": "import"}) == "Import"
        assert (
            formatter._get_element_type_name({"element_type": "unknown"}) == "Unknown"
        )

    def test_format_element_details(self, formatter):
        """Test element details formatting"""
        # Test with type annotations
        element = {
            "has_type_annotations": True,
            "generics": ["T", "U"],
            "visibility": "private",
            "is_static": True,
            "is_async": True,
            "is_abstract": True,
            "is_optional": True,
            "framework_type": "react",
        }

        details = formatter._format_element_details(element)
        assert "typed" in details
        assert "<T, U>" in details
        assert "private" in details
        assert "static" in details
        assert "async" in details
        assert "abstract" in details
        assert "optional" in details
        assert "react" in details

    def test_format_element_details_minimal(self, formatter):
        """Test element details formatting with minimal data"""
        element = {"visibility": "public"}
        details = formatter._format_element_details(element)
        assert details == ""  # Public visibility should not be shown

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
        assert "# TypeScript Script: empty" in result
        assert "## Module Info" in result

    def test_format_with_imports(self, formatter, sample_data):
        """Test formatting with imports section"""
        result = formatter.format(sample_data)

        assert "## Imports" in result
        assert "```typescript" in result
        assert "import Component from react;" in result
        assert "import type User from ./types;" in result

    def test_format_with_exports(self, formatter, sample_data):
        """Test formatting with exports section"""
        result = formatter.format(sample_data)

        assert "## Exports" in result
        assert "| Export | Type | Default |" in result
        assert "| UserService | named |  |" in result
        assert "| UserComponent | default | ✓ |" in result

    def test_format_module_info_statistics(self, formatter, sample_data):
        """Test module info statistics"""
        result = formatter.format(sample_data)

        # Check module info table
        assert "| Functions | 3 |" in result
        assert "| Classes | 1 |" in result
        assert "| Interfaces | 1 |" in result
        assert "| Type Aliases | 1 |" in result
        assert "| Enums | 1 |" in result
        assert "| Variables | 3 |" in result
        assert "| Exports | 2 |" in result

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

        # Test .ts file
        ts_data = {**base_data, "file_path": "service.ts"}
        result = formatter.format(ts_data)
        assert "# TypeScript Script: service" in result

        # Test .tsx file
        tsx_data = {**base_data, "file_path": "component.tsx"}
        result = formatter.format(tsx_data)
        assert "# TSX Module: component" in result

        # Test .d.ts file
        dts_data = {**base_data, "file_path": "types.d.ts"}
        result = formatter.format(dts_data)
        assert "# Declaration File: types" in result


if __name__ == "__main__":
    pytest.main([__file__])
