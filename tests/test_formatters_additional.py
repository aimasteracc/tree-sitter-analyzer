#!/usr/bin/env python3
"""
Additional comprehensive tests for formatters to achieve high coverage.
"""

import pytest
from tree_sitter_analyzer.formatters.java_formatter import JavaTableFormatter
from tree_sitter_analyzer.formatters.python_formatter import PythonTableFormatter
from tree_sitter_analyzer.formatters.base_formatter import BaseTableFormatter


class TestJavaFormatterAdditional:
    """Additional comprehensive test suite for Java formatter"""

    def setup_method(self):
        """Set up test fixtures"""
        self.formatter = JavaTableFormatter()

    def test_formatter_initialization(self):
        """Test formatter initialization"""
        assert self.formatter is not None
        assert hasattr(self.formatter, 'format_structure')

    def test_format_structure_basic(self):
        """Test basic format_structure method"""
        data = {
            "file_path": "Test.java",
            "classes": [
                {
                    "name": "TestClass",
                    "methods": [],
                    "fields": [],
                    "line_number": 1
                }
            ]
        }
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)
        assert "TestClass" in result

    def test_format_structure_with_package(self):
        """Test format_structure with package"""
        data = {
            "file_path": "Test.java",
            "package": "com.example.test",
            "classes": [
                {
                    "name": "TestClass",
                    "methods": [],
                    "fields": [],
                    "line_number": 1
                }
            ]
        }
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)
        assert "com.example.test" in result

    def test_format_structure_with_imports(self):
        """Test format_structure with imports"""
        data = {
            "file_path": "Test.java",
            "imports": [
                {"statement": "import java.util.List;"},
                {"statement": "import java.util.ArrayList;"}
            ],
            "classes": []
        }
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)
        assert "java.util.List" in result

    def test_format_structure_with_methods(self):
        """Test format_structure with methods"""
        data = {
            "file_path": "Test.java",
            "classes": [
                {
                    "name": "TestClass",
                    "methods": [
                        {
                            "name": "testMethod",
                            "parameters": ["String param"],
                            "modifiers": ["public"],
                            "return_type": "void",
                            "line_number": 5
                        }
                    ],
                    "fields": [],
                    "line_number": 1
                }
            ]
        }
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)
        assert "testMethod" in result

    def test_format_structure_with_fields(self):
        """Test format_structure with fields"""
        data = {
            "file_path": "Test.java",
            "classes": [
                {
                    "name": "TestClass",
                    "methods": [],
                    "fields": [
                        {
                            "name": "testField",
                            "type": "String",
                            "modifiers": ["private"],
                            "line_number": 3
                        }
                    ],
                    "line_number": 1
                }
            ]
        }
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)
        assert "testField" in result

    def test_format_structure_compact(self):
        """Test compact format structure"""
        self.formatter.format_type = "compact"
        data = {
            "file_path": "Test.java",
            "classes": [
                {
                    "name": "TestClass",
                    "methods": [{"name": "method1", "line_number": 5}],
                    "fields": [{"name": "field1", "line_number": 3}],
                    "line_number": 1
                }
            ]
        }
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)
        assert "TestClass" in result

    def test_format_structure_csv(self):
        """Test CSV format structure"""
        self.formatter.format_type = "csv"
        data = {
            "file_path": "Test.java",
            "classes": [
                {
                    "name": "TestClass",
                    "methods": [{"name": "method1", "line_number": 5}],
                    "fields": [{"name": "field1", "line_number": 3}],
                    "line_number": 1
                }
            ]
        }
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)
        assert "TestClass" in result

    def test_format_structure_empty_data(self):
        """Test format_structure with empty data"""
        data = {}
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)

    def test_format_structure_with_none_collections(self):
        """Test format_structure with None collections"""
        data = {
            "file_path": "Test.java",
            "classes": [],
            "imports": [],
            "functions": []
        }
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)

    def test_different_format_types(self):
        """Test different format types"""
        data = {
            "file_path": "Test.java",
            "classes": [{"name": "TestClass", "line_number": 1, "methods": [], "fields": []}]
        }
        
        # Test full format
        formatter_full = JavaTableFormatter("full")
        result_full = formatter_full.format_structure(data)
        assert isinstance(result_full, str)
        
        # Test compact format
        formatter_compact = JavaTableFormatter("compact")
        result_compact = formatter_compact.format_structure(data)
        assert isinstance(result_compact, str)
        
        # Test CSV format
        formatter_csv = JavaTableFormatter("csv")
        result_csv = formatter_csv.format_structure(data)
        assert isinstance(result_csv, str)


class TestPythonFormatterAdditional:
    """Additional comprehensive test suite for Python formatter"""

    def setup_method(self):
        """Set up test fixtures"""
        self.formatter = PythonTableFormatter()

    def test_formatter_initialization(self):
        """Test formatter initialization"""
        assert self.formatter is not None
        assert hasattr(self.formatter, 'format_structure')

    def test_format_structure_basic(self):
        """Test basic format_structure method"""
        data = {
            "file_path": "test.py",
            "functions": [
                {
                    "name": "test_function",
                    "parameters": ["param1"],
                    "line_number": 1
                }
            ],
            "classes": []
        }
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)
        assert "test_function" in result

    def test_format_structure_with_classes(self):
        """Test format_structure with classes"""
        data = {
            "file_path": "test.py",
            "functions": [],
            "classes": [
                {
                    "name": "TestClass",
                    "methods": [
                        {
                            "name": "__init__",
                            "parameters": ["self", "name"],
                            "line_number": 3
                        }
                    ],
                    "fields": [],
                    "line_number": 1
                }
            ]
        }
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)
        assert "TestClass" in result

    def test_format_structure_with_imports(self):
        """Test format_structure with imports"""
        data = {
            "file_path": "test.py",
            "imports": [
                {"statement": "import os"},
                {"statement": "from typing import List"}
            ],
            "functions": [],
            "classes": []
        }
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)
        assert "import os" in result

    def test_format_structure_compact(self):
        """Test compact format structure"""
        self.formatter.format_type = "compact"
        data = {
            "file_path": "test.py",
            "functions": [{"name": "func1", "line_number": 1}],
            "classes": [{"name": "Class1", "line_number": 5}]
        }
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)
        assert "func1" in result

    def test_format_structure_csv(self):
        """Test CSV format structure"""
        self.formatter.format_type = "csv"
        data = {
            "file_path": "test.py",
            "functions": [{"name": "func1", "line_number": 1}],
            "classes": [{"name": "Class1", "line_number": 5}]
        }
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)
        assert "func1" in result

    def test_different_format_types(self):
        """Test different format types"""
        data = {
            "file_path": "test.py",
            "functions": [{"name": "test_func", "line_number": 1}],
            "classes": [{"name": "TestClass", "line_number": 5}]
        }
        
        # Test full format
        formatter_full = PythonTableFormatter("full")
        result_full = formatter_full.format_structure(data)
        assert isinstance(result_full, str)
        
        # Test compact format
        formatter_compact = PythonTableFormatter("compact")
        result_compact = formatter_compact.format_structure(data)
        assert isinstance(result_compact, str)
        
        # Test CSV format
        formatter_csv = PythonTableFormatter("csv")
        result_csv = formatter_csv.format_structure(data)
        assert isinstance(result_csv, str)


class TestBaseFormatterAdditional:
    """Additional tests for BaseTableFormatter"""

    def test_platform_newline_detection(self):
        """Test platform newline detection"""
        # Create a concrete implementation for testing
        class ConcreteFormatter(BaseTableFormatter):
            def format_structure(self, data):
                return "test"
        
        formatter = ConcreteFormatter()
        newline = formatter._get_platform_newline()
        assert newline in ["\n", "\r\n"]

    def test_newline_conversion(self):
        """Test newline conversion"""
        class ConcreteFormatter(BaseTableFormatter):
            def format_structure(self, data):
                return "test"
        
        formatter = ConcreteFormatter()
        text = "line1\nline2\nline3"
        result = formatter._convert_to_platform_newlines(text)
        assert isinstance(result, str)
        assert "line1" in result and "line2" in result and "line3" in result

    def test_format_type_initialization(self):
        """Test format type initialization"""
        class ConcreteFormatter(BaseTableFormatter):
            def format_structure(self, data):
                return "test"
        
        formatter_default = ConcreteFormatter()
        assert formatter_default.format_type == "full"
        
        formatter_compact = ConcreteFormatter("compact")
        assert formatter_compact.format_type == "compact"
        
        formatter_csv = ConcreteFormatter("csv")
        assert formatter_csv.format_type == "csv"