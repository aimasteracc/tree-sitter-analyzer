#!/usr/bin/env python3
"""
Comprehensive tests for JavaScript formatter to achieve high coverage.
"""

import pytest
from tree_sitter_analyzer.formatters.javascript_formatter import JavaScriptTableFormatter


class TestJavaScriptFormatterComprehensive:
    """Comprehensive test suite for JavaScript formatter"""

    def setup_method(self):
        """Set up test fixtures"""
        self.formatter = JavaScriptTableFormatter()

    def test_format_basic(self):
        """Test basic format method"""
        data = {"file_path": "test.js", "functions": [], "classes": []}
        result = self.formatter.format(data)
        assert isinstance(result, str)
        assert "test" in result

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
        assert "async" in result or "generator" in result

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
                        },
                        {
                            "name": "staticMethod",
                            "parameters": [],
                            "visibility": "public",
                            "is_static": True,
                            "is_async": True,
                            "docstring": None,
                            "line_number": 10
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
        assert "BaseClass" in result
        assert "constructor" in result
        assert "staticMethod" in result
        assert "field1" in result

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
                },
                {
                    "name": "letVar",
                    "type": "let",
                    "value": "42",
                    "docstring": None,
                    "line_number": 2
                },
                {
                    "name": "varVar",
                    "type": "var",
                    "value": None,
                    "docstring": None,
                    "line_number": 3
                }
            ]
        }
        result = self.formatter._format_full_table(data)
        assert "## Variables" in result
        assert "constVar" in result
        assert "letVar" in result
        assert "varVar" in result

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
        assert "Class1" in result
        assert "var1" in result

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
            "classes": [
                {
                    "name": "TestClass",
                    "methods": [{"name": "method1", "line_number": 5}],
                    "fields": [],
                    "line_number": 3
                }
            ],
            "variables": [
                {
                    "name": "testVar",
                    "type": "const",
                    "line_number": 8
                }
            ]
        }
        self.formatter.format_type = "csv"
        result = self.formatter._format_csv(data)
        assert "Type,Name,Line" in result
        assert "Function,testFunc,1" in result
        assert "Class,TestClass,3" in result
        assert "Variable,testVar,8" in result

    def test_get_element_type_name(self):
        """Test element type name extraction"""
        assert self.formatter._get_element_type_name("functions") == "Function"
        assert self.formatter._get_element_type_name("classes") == "Class"
        assert self.formatter._get_element_type_name("variables") == "Variable"
        assert self.formatter._get_element_type_name("imports") == "Import"
        assert self.formatter._get_element_type_name("exports") == "Export"
        assert self.formatter._get_element_type_name("unknown") == "Element"

    def test_format_element_details_function(self):
        """Test formatting function element details"""
        element = {
            "name": "testFunc",
            "parameters": ["a", "b"],
            "return_type": "number",
            "is_async": True,
            "is_generator": False,
            "is_arrow": True,
            "visibility": "public",
            "docstring": "Test function",
            "complexity": 5
        }
        result = self.formatter._format_element_details(element, "functions")
        assert "testFunc(a, b)" in result
        assert "async" in result
        assert "arrow" in result
        assert "→ number" in result

    def test_format_element_details_class(self):
        """Test formatting class element details"""
        element = {
            "name": "TestClass",
            "superclass": "BaseClass",
            "methods": [{"name": "method1"}],
            "fields": [{"name": "field1"}],
            "is_abstract": True,
            "docstring": "Test class"
        }
        result = self.formatter._format_element_details(element, "classes")
        assert "TestClass extends BaseClass" in result
        assert "abstract" in result
        assert "1 method" in result
        assert "1 field" in result

    def test_format_element_details_variable(self):
        """Test formatting variable element details"""
        element = {
            "name": "testVar",
            "type": "const",
            "value": "'hello'",
            "docstring": "Test variable"
        }
        result = self.formatter._format_element_details(element, "variables")
        assert "const testVar = 'hello'" in result

    def test_format_element_details_minimal(self):
        """Test formatting with minimal element data"""
        element = {"name": "minimal"}
        result = self.formatter._format_element_details(element, "functions")
        assert "minimal" in result

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

    def test_format_method_with_all_properties(self):
        """Test formatting method with all properties"""
        method = {
            "name": "complexMethod",
            "parameters": ["param1", "param2"],
            "visibility": "private",
            "is_static": True,
            "is_async": True,
            "docstring": "Complex method description",
            "line_number": 15,
            "return_type": "Promise<string>"
        }
        result = self.formatter._format_method_signature(method)
        assert "private static async complexMethod(param1, param2)" in result
        assert "Promise<string>" in result

    def test_format_method_minimal(self):
        """Test formatting method with minimal properties"""
        method = {"name": "simpleMethod"}
        result = self.formatter._format_method_signature(method)
        assert "simpleMethod()" in result

    def test_format_field_with_all_properties(self):
        """Test formatting field with all properties"""
        field = {
            "name": "complexField",
            "type": "string",
            "visibility": "protected",
            "is_static": True,
            "value": "'default'",
            "docstring": "Complex field"
        }
        result = self.formatter._format_field_signature(field)
        assert "protected static complexField: string = 'default'" in result

    def test_format_field_minimal(self):
        """Test formatting field with minimal properties"""
        field = {"name": "simpleField"}
        result = self.formatter._format_field_signature(field)
        assert "simpleField" in result

    def test_extract_doc_summary(self):
        """Test document summary extraction"""
        # Test with JSDoc comment
        docstring = "/**\n * This is a test function\n * @param {string} param - A parameter\n * @returns {number} The result\n */"
        result = self.formatter._extract_doc_summary(docstring)
        assert "This is a test function" in result

        # Test with single line comment
        docstring = "// Simple comment"
        result = self.formatter._extract_doc_summary(docstring)
        assert "Simple comment" in result

        # Test with multiline comment
        docstring = "/* Multi\nline\ncomment */"
        result = self.formatter._extract_doc_summary(docstring)
        assert "Multi line comment" in result

        # Test with None
        result = self.formatter._extract_doc_summary(None)
        assert result == ""

        # Test with empty string
        result = self.formatter._extract_doc_summary("")
        assert result == ""

    def test_clean_csv_text(self):
        """Test CSV text cleaning"""
        # Test with quotes
        text = 'Text with "quotes" inside'
        result = self.formatter._clean_csv_text(text)
        assert '"' not in result or '""' in result

        # Test with commas
        text = "Text, with, commas"
        result = self.formatter._clean_csv_text(text)
        assert result.startswith('"') and result.endswith('"')

        # Test with newlines
        text = "Text\nwith\nnewlines"
        result = self.formatter._clean_csv_text(text)
        assert "\n" not in result

        # Test with None
        result = self.formatter._clean_csv_text(None)
        assert result == ""

    def test_format_structure_with_missing_keys(self):
        """Test format structure with missing keys"""
        data = {"file_path": "test.js"}  # Missing other expected keys
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)
        assert len(result) > 0

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
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)

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
                    "docstring": "/**\n * Complex async arrow function\n * @param {string} param1 - First parameter\n * @param {number} param2 - Second parameter\n * @param {...any} rest - Rest parameters\n * @returns {Promise<Array<Object>>} Promise resolving to array of objects\n */",
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
                        },
                        {
                            "name": "asyncStaticMethod",
                            "parameters": ["data"],
                            "visibility": "public",
                            "is_static": True,
                            "is_async": True,
                            "docstring": "Async static method",
                            "line_number": 30,
                            "return_type": "Promise<void>"
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
                        },
                        {
                            "name": "staticField",
                            "type": "string",
                            "visibility": "public",
                            "is_static": True,
                            "line_number": 24,
                            "value": "'default'"
                        }
                    ],
                    "docstring": "/**\n * Complex class with various features\n * @extends BaseClass\n */",
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
        assert "async" in result
        assert "static" in result
        assert "Promise" in result