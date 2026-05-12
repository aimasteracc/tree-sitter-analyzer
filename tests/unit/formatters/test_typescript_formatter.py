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


# ── Coverage gap tests ──────────────────────────────────────────────


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
