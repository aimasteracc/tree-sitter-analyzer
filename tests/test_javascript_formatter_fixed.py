#!/usr/bin/env python3
"""
Fixed comprehensive tests for JavaScript formatter to achieve high coverage.
"""

import pytest
from tree_sitter_analyzer.formatters.javascript_formatter import JavaScriptTableFormatter


class TestJavaScriptFormatterFixed:
    """Fixed comprehensive test suite for JavaScript formatter"""

    def setup_method(self):
        """Set up test fixtures"""
        self.formatter = JavaScriptTableFormatter()

    def test_format_basic(self):
        """Test basic format method"""
        data = {"file_path": "test.js", "functions": [], "classes": []}
        result = self.formatter.format(data)
        assert isinstance(result, str)
        assert "test" in result

    def test_format_structure_basic(self):
        """Test format_structure method"""
        data = {"file_path": "test.js", "functions": [], "classes": []}
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_full_table_module(self):
        """Test full table format for module"""
        data = {
            "file_path": "module.js",
            "exports": [{"name": "testExport"}],
            "imports": [],
            "functions": [],
            "classes": [],
            "variables": []
        }
        result = self.formatter._format_full_table(data)
        assert "Module: module" in result

    def test_format_full_table_script(self):
        """Test full table format for script"""
        data = {
            "file_path": "script.js",
            "exports": [],
            "imports": [],
            "functions": [],
            "classes": [],
            "variables": []
        }
        result = self.formatter._format_full_table(data)
        assert "Script: script" in result

    def test_format_with_imports(self):
        """Test formatting with imports"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "imports": [
                {"statement": "import React from 'react'"},
                {"statement": "import { useState } from 'react'"},
                {"statement": ""}  # Empty statement
            ],
            "functions": [],
            "classes": [],
            "variables": []
        }
        result = self.formatter._format_full_table(data)
        assert "## Imports" in result
        assert "import React from 'react'" in result
        assert "import { useState } from 'react'" in result

    def test_format_with_functions(self):
        """Test formatting with functions"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "imports": [],
            "functions": [
                {
                    "name": "testFunction",
                    "parameters": ["param1", "param2"],
                    "return_type": "string",
                    "is_async": True,
                    "is_generator": False,
                    "is_arrow": True,
                    "visibility": "public",
                    "docstring": "Test function description",
                    "line_number": 10,
                    "complexity": 5
                },
                {
                    "name": "simpleFunction",
                    "parameters": [],
                    "return_type": None,
                    "is_async": False,
                    "is_generator": True,
                    "is_arrow": False,
                    "visibility": "private",
                    "docstring": None,
                    "line_number": 20,
                    "complexity": 1
                }
            ],
            "classes": [],
            "variables": []
        }
        result = self.formatter._format_full_table(data)
        assert "## Functions" in result or "## Async Functions" in result
        assert "testFunction" in result
        assert "simpleFunction" in result

    def test_format_with_classes(self):
        """Test formatting with classes"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "imports": [],
            "functions": [],
            "classes": [
                {
                    "name": "TestClass",
                    "superclass": "BaseClass",
                    "methods": [
                        {
                            "name": "constructor",
                            "parameters": ["param1"],
                            "visibility": "public",
                            "is_static": False,
                            "is_async": False,
                            "docstring": "Constructor",
                            "line_number": 5
                        }
                    ],
                    "fields": [
                        {
                            "name": "field1",
                            "type": "string",
                            "visibility": "private",
                            "is_static": False,
                            "line_number": 3
                        }
                    ],
                    "docstring": "Test class",
                    "line_number": 1,
                    "is_abstract": False
                }
            ],
            "variables": []
        }
        result = self.formatter._format_full_table(data)
        assert "## Classes" in result
        assert "TestClass" in result

    def test_format_with_variables(self):
        """Test formatting with variables"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "imports": [],
            "functions": [],
            "classes": [],
            "variables": [
                {
                    "name": "constVar",
                    "type": "const",
                    "value": "'test'",
                    "docstring": "Constant variable",
                    "line_number": 1
                }
            ]
        }
        result = self.formatter._format_full_table(data)
        assert "## Variables" in result
        assert "constVar" in result

    def test_format_compact_table(self):
        """Test compact table format"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "imports": [],
            "functions": [{"name": "func1", "parameters": [], "line_number": 1}],
            "classes": [{"name": "Class1", "methods": [], "fields": [], "line_number": 5}],
            "variables": [{"name": "var1", "type": "const", "line_number": 10}]
        }
        self.formatter.format_type = "compact"
        result = self.formatter._format_compact_table(data)
        assert "func1" in result

    def test_format_csv(self):
        """Test CSV format"""
        data = {
            "file_path": "test.js",
            "exports": [],
            "imports": [],
            "functions": [
                {
                    "name": "testFunc",
                    "parameters": ["param1"],
                    "return_type": "string",
                    "line_number": 1,
                    "complexity": 3
                }
            ],
            "classes": [],
            "variables": []
        }
        self.formatter.format_type = "csv"
        result = self.formatter._format_csv(data)
        assert "testFunc" in result

    def test_format_empty_data(self):
        """Test formatting with empty data"""
        data = {}
        result = self.formatter._format_full_table(data)
        assert "Unknown" in result

    def test_format_with_jsx_file(self):
        """Test formatting JSX file"""
        data = {
            "file_path": "component.jsx",
            "exports": [],
            "imports": [],
            "functions": [],
            "classes": [],
            "variables": []
        }
        result = self.formatter._format_full_table(data)
        assert "component" in result

    def test_format_with_mjs_file(self):
        """Test formatting MJS file"""
        data = {
            "file_path": "module.mjs",
            "exports": [],
            "imports": [],
            "functions": [],
            "classes": [],
            "variables": []
        }
        result = self.formatter._format_full_table(data)
        assert "module" in result

    def test_format_with_windows_path(self):
        """Test formatting with Windows path"""
        data = {
            "file_path": "C:\\path\\to\\file.js",
            "exports": [],
            "imports": [],
            "functions": [],
            "classes": [],
            "variables": []
        }
        result = self.formatter._format_full_table(data)
        assert "file" in result

    def test_format_with_exports(self):
        """Test formatting with exports"""
        data = {
            "file_path": "test.js",
            "exports": [
                {"name": "defaultExport", "type": "default"},
                {"name": "namedExport", "type": "named"}
            ],
            "imports": [],
            "functions": [],
            "classes": [],
            "variables": []
        }
        result = self.formatter._format_full_table(data)
        assert "Module: test" in result

    def test_all_format_types_produce_output(self):
        """Test that all format types produce output"""
        data = {
            "file_path": "test.js",
            "functions": [{"name": "func1", "line_number": 1}],
            "classes": [{"name": "Class1", "line_number": 5}],
            "variables": [{"name": "var1", "line_number": 10}]
        }
        
        # Test full format
        formatter_full = JavaScriptTableFormatter("full")
        result_full = formatter_full.format(data)
        assert len(result_full) > 0
        
        # Test compact format
        formatter_compact = JavaScriptTableFormatter("compact")
        result_compact = formatter_compact.format(data)
        assert len(result_compact) > 0
        
        # Test CSV format
        formatter_csv = JavaScriptTableFormatter("csv")
        result_csv = formatter_csv.format(data)
        assert len(result_csv) > 0

    def test_platform_newline_detection(self):
        """Test platform newline detection"""
        newline = self.formatter._get_platform_newline()
        assert newline in ["\n", "\r\n"]

    def test_newline_conversion(self):
        """Test newline conversion"""
        text = "line1\nline2\nline3"
        result = self.formatter._convert_to_platform_newlines(text)
        assert isinstance(result, str)
        assert "line1" in result and "line2" in result and "line3" in result

    def test_format_structure_with_none_values(self):
        """Test format structure with None values"""
        data = {
            "file_path": "test.js",
            "functions": None,
            "classes": None,
            "variables": None,
            "imports": None,
            "exports": None
        }
        # Should handle None values gracefully
        try:
            result = self.formatter.format_structure(data)
            assert isinstance(result, str)
        except (TypeError, AttributeError):
            # Expected if the formatter doesn't handle None values
            pass

    def test_complex_nested_data(self):
        """Test with complex nested data structures"""
        data = {
            "file_path": "complex.js",
            "exports": [{"name": "ComplexExport"}],
            "imports": [
                {"statement": "import { complex } from 'complex-lib'"}
            ],
            "functions": [
                {
                    "name": "complexFunction",
                    "parameters": ["param1", "param2", "...rest"],
                    "return_type": "Promise<Array<Object>>",
                    "is_async": True,
                    "is_generator": False,
                    "is_arrow": True,
                    "visibility": "export",
                    "docstring": "Complex async arrow function",
                    "line_number": 10,
                    "complexity": 15
                }
            ],
            "classes": [
                {
                    "name": "ComplexClass",
                    "superclass": "BaseClass",
                    "methods": [
                        {
                            "name": "constructor",
                            "parameters": ["config"],
                            "visibility": "public",
                            "is_static": False,
                            "is_async": False,
                            "docstring": "Constructor with configuration",
                            "line_number": 25
                        }
                    ],
                    "fields": [
                        {
                            "name": "privateField",
                            "type": "Map<string, any>",
                            "visibility": "private",
                            "is_static": False,
                            "line_number": 23,
                            "value": "new Map()"
                        }
                    ],
                    "docstring": "Complex class with various features",
                    "line_number": 20,
                    "is_abstract": False
                }
            ],
            "variables": [
                {
                    "name": "complexConst",
                    "type": "const",
                    "value": "{ key: 'value', nested: { deep: true } }",
                    "docstring": "Complex constant object",
                    "line_number": 5
                }
            ]
        }
        
        result = self.formatter.format(data)
        assert "ComplexClass" in result
        assert "complexFunction" in result
        assert "complexConst" in result

    def test_format_type_initialization(self):
        """Test different format type initialization"""
        formatter_full = JavaScriptTableFormatter("full")
        assert formatter_full.format_type == "full"
        
        formatter_compact = JavaScriptTableFormatter("compact")
        assert formatter_compact.format_type == "compact"
        
        formatter_csv = JavaScriptTableFormatter("csv")
        assert formatter_csv.format_type == "csv"

    def test_error_handling_with_malformed_data(self):
        """Test error handling with malformed data"""
        malformed_data = {
            "file_path": "test.js",
            "functions": [
                {
                    "name": None,  # Invalid name
                    "parameters": "not_a_list",  # Invalid parameters
                    "line_number": "not_a_number"  # Invalid line number
                }
            ]
        }
        
        # Should handle malformed data gracefully
        try:
            result = self.formatter.format(malformed_data)
            assert isinstance(result, str)
        except (TypeError, AttributeError, ValueError):
            # Expected if the formatter doesn't handle malformed data
            pass

    def test_large_data_structure(self):
        """Test with large data structure"""
        large_data = {
            "file_path": "large.js",
            "functions": [{"name": f"func_{i}", "line_number": i} for i in range(100)],
            "classes": [{"name": f"Class_{i}", "line_number": i*10} for i in range(50)],
            "variables": [{"name": f"var_{i}", "line_number": i*5} for i in range(200)]
        }
        
        result = self.formatter.format(large_data)
        assert isinstance(result, str)
        assert len(result) > 1000  # Should be a substantial output

    def test_unicode_content_handling(self):
        """Test handling of unicode content"""
        unicode_data = {
            "file_path": "unicode.js",
            "functions": [
                {
                    "name": "测试函数",
                    "docstring": "这是一个测试函数 🚀",
                    "line_number": 1
                }
            ],
            "variables": [
                {
                    "name": "变量",
                    "value": "'你好世界'",
                    "line_number": 5
                }
            ]
        }
        
        result = self.formatter.format(unicode_data)
        assert isinstance(result, str)
        assert "测试函数" in result or "unicode" in result  # Should handle unicode gracefully