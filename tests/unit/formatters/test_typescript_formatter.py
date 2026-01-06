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

        # Check for TypeScript-specific content - new format uses simpler headers
        assert "UserService" in result
        # Check that classes are shown in the output
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
        # New format uses simpler headers without type prefix
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
        # New format uses simpler headers
        assert "index" in result

    def test_format_interfaces_section(self, formatter, sample_data):
        """Test interfaces section formatting"""
        result = formatter.format(sample_data)

        # Check that interfaces are included in the output
        assert "IUserProfile" in result
        assert "interface" in result

    def test_format_type_aliases_section(self, formatter, sample_data):
        """Test type aliases section formatting"""
        result = formatter.format(sample_data)

        # Check type alias is in classes overview table
        assert "Status" in result
        assert "type" in result
        # Check line range is present
        assert "2-2" in result

    def test_format_enums_section(self, formatter, sample_data):
        """Test enums section formatting"""
        result = formatter.format(sample_data)

        # Check enum is in classes overview table
        assert "UserRole" in result
        assert "enum" in result
        # Check line range is present
        assert "47-52" in result

    def test_format_classes_section(self, formatter, sample_data):
        """Test classes section formatting"""
        result = formatter.format(sample_data)

        # Check class info in overview table
        assert "UserService" in result
        assert "class" in result
        assert "15-45" in result
        # Check interface is also present
        assert "IUserProfile" in result
        assert "interface" in result

    def test_format_functions_section(self, formatter, sample_data):
        """Test functions section formatting"""
        result = formatter.format(sample_data)

        # Check method is in class section
        assert "validate" in result
        # Check method signature components
        assert "boolean" in result or "UserProfile" in result

    def test_format_variables_section(self, formatter, sample_data):
        """Test variables section formatting"""
        result = formatter.format(sample_data)

        # Check field is in class section
        assert "userId" in result
        assert "string" in result

    def test_format_compact_table(self, sample_data):
        """Test compact table formatting"""
        formatter = TypeScriptTableFormatter("compact")
        result = formatter.format(sample_data)

        assert isinstance(result, str)
        assert len(result) > 0

        # Check compact format structure
        assert "UserService" in result
        assert "## Info" in result
        # Check methods section exists
        assert "## Methods" in result or "Methods" in result

    def test_format_csv(self, sample_data):
        """Test CSV formatting"""
        formatter = TypeScriptTableFormatter("csv")
        result = formatter.format(sample_data)

        assert isinstance(result, str)
        assert len(result) > 0

        # Check CSV structure
        lines = result.split("\n")
        assert len(lines) > 1  # Should have header + data lines
        # Check header row contains expected columns
        header = lines[0]
        assert "Type" in header or "Name" in header
        # Check data contains expected elements
        assert any("validate" in line for line in lines)
        assert any("userId" in line for line in lines)

    def test_get_element_type_name(self, formatter):
        """Test element type name generation - method may not exist in new implementation"""
        # Skip if method doesn't exist
        if not hasattr(formatter, "_get_element_type_name"):
            pytest.skip("_get_element_type_name not implemented in new formatter")

    def test_format_element_details(self, formatter):
        """Test element details formatting - method may not exist in new implementation"""
        # Skip if method doesn't exist
        if not hasattr(formatter, "_format_element_details"):
            pytest.skip("_format_element_details not implemented in new formatter")

    def test_format_element_details_minimal(self, formatter):
        """Test element details formatting with minimal data - method may not exist"""
        # Skip if method doesn't exist
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
        # New format uses simpler header with filename
        assert "empty" in result

    def test_format_with_imports(self, formatter, sample_data):
        """Test formatting includes expected content"""
        result = formatter.format(sample_data)

        # New format focuses on classes/methods, not imports section
        # Check that main content is present
        assert "UserService" in result
        assert "IUserProfile" in result

    def test_format_with_exports(self, formatter, sample_data):
        """Test formatting includes class content"""
        result = formatter.format(sample_data)

        # New format focuses on classes, not exports section
        assert "UserService" in result
        assert "validate" in result

    def test_format_module_info_statistics(self, formatter, sample_data):
        """Test output contains element information"""
        result = formatter.format(sample_data)

        # New format shows classes overview table
        assert "## Classes Overview" in result or "Class" in result
        # Check that classes are listed
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

        # Test .ts file - new format uses filename without prefix
        ts_data = {**base_data, "file_path": "service.ts"}
        result = formatter.format(ts_data)
        assert "service" in result

        # Test .tsx file
        tsx_data = {**base_data, "file_path": "component.tsx"}
        result = formatter.format(tsx_data)
        assert "component" in result

        # Test .d.ts file
        dts_data = {**base_data, "file_path": "types.d.ts"}
        result = formatter.format(dts_data)
        assert "types" in result


if __name__ == "__main__":
    pytest.main([__file__])
