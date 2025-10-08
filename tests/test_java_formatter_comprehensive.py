#!/usr/bin/env python3
"""
Comprehensive tests for Java formatter to achieve high coverage.
"""

import pytest
from tree_sitter_analyzer.formatters.java_formatter import JavaTableFormatter


class TestJavaFormatterComprehensive:
    """Comprehensive test suite for Java formatter"""

    def setup_method(self):
        """Set up test fixtures"""
        self.formatter = JavaTableFormatter()

    def test_format_basic(self):
        """Test basic format method"""
        data = {"file_path": "Test.java", "classes": [], "functions": []}
        result = self.formatter.format(data)
        assert isinstance(result, str)
        assert "Test" in result

    def test_format_full_table_basic(self):
        """Test full table format basic functionality"""
        data = {
            "file_path": "Example.java",
            "package": "com.example",
            "imports": [],
            "classes": [],
            "functions": [],
            "variables": []
        }
        result = self.formatter._format_full_table(data)
        assert "Package: com.example" in result
        assert "Example.java" in result

    def test_format_full_table_no_package(self):
        """Test full table format without package"""
        data = {
            "file_path": "Example.java",
            "imports": [],
            "classes": [],
            "functions": [],
            "variables": []
        }
        result = self.formatter._format_full_table(data)
        assert "Example.java" in result

    def test_format_with_imports(self):
        """Test formatting with imports"""
        data = {
            "file_path": "Test.java",
            "package": "com.test",
            "imports": [
                {"statement": "import java.util.List;"},
                {"statement": "import java.util.ArrayList;"},
                {"statement": ""}  # Empty import
            ],
            "classes": [],
            "functions": [],
            "variables": []
        }
        result = self.formatter._format_full_table(data)
        assert "## Imports" in result
        assert "java.util.List" in result
        assert "java.util.ArrayList" in result

    def test_format_with_classes(self):
        """Test formatting with classes"""
        data = {
            "file_path": "Test.java",
            "package": "com.test",
            "imports": [],
            "classes": [
                {
                    "name": "TestClass",
                    "superclass": "BaseClass",
                    "interfaces": ["Serializable", "Comparable"],
                    "modifiers": ["public", "final"],
                    "methods": [
                        {
                            "name": "constructor",
                            "parameters": ["String name"],
                            "modifiers": ["public"],
                            "return_type": None,
                            "docstring": "Constructor",
                            "line_number": 5
                        },
                        {
                            "name": "getName",
                            "parameters": [],
                            "modifiers": ["public"],
                            "return_type": "String",
                            "docstring": "Get name",
                            "line_number": 10
                        }
                    ],
                    "fields": [
                        {
                            "name": "name",
                            "type": "String",
                            "modifiers": ["private", "final"],
                            "value": None,
                            "line_number": 3
                        }
                    ],
                    "docstring": "Test class documentation",
                    "line_number": 1,
                    "is_abstract": False,
                    "is_interface": False
                }
            ],
            "functions": [],
            "variables": []
        }
        result = self.formatter._format_full_table(data)
        assert "## Classes" in result
        assert "TestClass" in result
        assert "extends BaseClass" in result
        assert "implements Serializable, Comparable" in result
        assert "public final" in result
        assert "constructor" in result
        assert "getName" in result
        assert "private final String name" in result

    def test_format_with_interface(self):
        """Test formatting with interface"""
        data = {
            "file_path": "Test.java",
            "classes": [
                {
                    "name": "TestInterface",
                    "superclass": None,
                    "interfaces": ["BaseInterface"],
                    "modifiers": ["public"],
                    "methods": [
                        {
                            "name": "abstractMethod",
                            "parameters": ["int param"],
                            "modifiers": ["public", "abstract"],
                            "return_type": "void",
                            "line_number": 3
                        }
                    ],
                    "fields": [],
                    "line_number": 1,
                    "is_abstract": False,
                    "is_interface": True
                }
            ]
        }
        result = self.formatter._format_full_table(data)
        assert "TestInterface" in result
        assert "extends BaseInterface" in result
        assert "interface" in result

    def test_format_with_abstract_class(self):
        """Test formatting with abstract class"""
        data = {
            "file_path": "Test.java",
            "classes": [
                {
                    "name": "AbstractClass",
                    "superclass": None,
                    "interfaces": [],
                    "modifiers": ["public", "abstract"],
                    "methods": [],
                    "fields": [],
                    "line_number": 1,
                    "is_abstract": True,
                    "is_interface": False
                }
            ]
        }
        result = self.formatter._format_full_table(data)
        assert "AbstractClass" in result
        assert "abstract" in result

    def test_format_with_functions(self):
        """Test formatting with standalone functions"""
        data = {
            "file_path": "Test.java",
            "classes": [],
            "functions": [
                {
                    "name": "staticMethod",
                    "parameters": ["String input", "int count"],
                    "modifiers": ["public", "static"],
                    "return_type": "String",
                    "docstring": "Static utility method",
                    "line_number": 5,
                    "complexity": 3
                }
            ]
        }
        result = self.formatter._format_full_table(data)
        assert "## Functions" in result
        assert "staticMethod" in result
        assert "public static" in result
        assert "String input, int count" in result
        assert "→ String" in result

    def test_format_with_variables(self):
        """Test formatting with variables"""
        data = {
            "file_path": "Test.java",
            "classes": [],
            "variables": [
                {
                    "name": "CONSTANT",
                    "type": "String",
                    "modifiers": ["public", "static", "final"],
                    "value": "\"test\"",
                    "docstring": "String constant",
                    "line_number": 1
                }
            ]
        }
        result = self.formatter._format_full_table(data)
        assert "## Variables" in result
        assert "CONSTANT" in result
        assert "public static final" in result
        assert "String" in result

    def test_format_compact_table(self):
        """Test compact table format"""
        data = {
            "file_path": "Test.java",
            "classes": [
                {
                    "name": "TestClass",
                    "methods": [{"name": "method1", "line_number": 5}],
                    "fields": [{"name": "field1", "line_number": 3}],
                    "line_number": 1
                }
            ],
            "functions": [
                {"name": "function1", "line_number": 10}
            ],
            "variables": [
                {"name": "variable1", "line_number": 15}
            ]
        }
        self.formatter.format_type = "compact"
        result = self.formatter._format_compact_table(data)
        assert "TestClass" in result
        assert "function1" in result
        assert "variable1" in result

    def test_format_csv(self):
        """Test CSV format"""
        data = {
            "file_path": "Test.java",
            "classes": [
                {
                    "name": "TestClass",
                    "methods": [{"name": "method1", "line_number": 5}],
                    "fields": [{"name": "field1", "line_number": 3}],
                    "line_number": 1
                }
            ],
            "functions": [
                {"name": "function1", "line_number": 10}
            ],
            "variables": [
                {"name": "variable1", "line_number": 15}
            ]
        }
        self.formatter.format_type = "csv"
        result = self.formatter._format_csv(data)
        assert "Type,Name,Line" in result
        assert "Class,TestClass,1" in result
        assert "Function,function1,10" in result
        assert "Variable,variable1,15" in result

    def test_get_element_type_name(self):
        """Test element type name extraction"""
        assert self.formatter._get_element_type_name("classes") == "Class"
        assert self.formatter._get_element_type_name("functions") == "Function"
        assert self.formatter._get_element_type_name("variables") == "Variable"
        assert self.formatter._get_element_type_name("imports") == "Import"
        assert self.formatter._get_element_type_name("unknown") == "Element"

    def test_format_element_details_class(self):
        """Test formatting class element details"""
        element = {
            "name": "TestClass",
            "superclass": "BaseClass",
            "interfaces": ["Interface1", "Interface2"],
            "modifiers": ["public", "final"],
            "methods": [{"name": "method1"}, {"name": "method2"}],
            "fields": [{"name": "field1"}],
            "docstring": "Test class",
            "is_abstract": False,
            "is_interface": False
        }
        result = self.formatter._format_element_details(element, "classes")
        assert "public final class TestClass extends BaseClass implements Interface1, Interface2" in result
        assert "2 methods" in result
        assert "1 field" in result

    def test_format_element_details_interface(self):
        """Test formatting interface element details"""
        element = {
            "name": "TestInterface",
            "interfaces": ["BaseInterface"],
            "modifiers": ["public"],
            "methods": [{"name": "method1"}],
            "fields": [],
            "is_interface": True
        }
        result = self.formatter._format_element_details(element, "classes")
        assert "public interface TestInterface extends BaseInterface" in result

    def test_format_element_details_abstract_class(self):
        """Test formatting abstract class element details"""
        element = {
            "name": "AbstractClass",
            "modifiers": ["public", "abstract"],
            "methods": [],
            "fields": [],
            "is_abstract": True,
            "is_interface": False
        }
        result = self.formatter._format_element_details(element, "classes")
        assert "public abstract class AbstractClass" in result

    def test_format_element_details_function(self):
        """Test formatting function element details"""
        element = {
            "name": "testMethod",
            "parameters": ["String param1", "int param2"],
            "modifiers": ["public", "static"],
            "return_type": "boolean",
            "docstring": "Test method",
            "complexity": 5
        }
        result = self.formatter._format_element_details(element, "functions")
        assert "public static testMethod(String param1, int param2) → boolean" in result

    def test_format_element_details_variable(self):
        """Test formatting variable element details"""
        element = {
            "name": "testVar",
            "type": "String",
            "modifiers": ["private", "final"],
            "value": "\"default\"",
            "docstring": "Test variable"
        }
        result = self.formatter._format_element_details(element, "variables")
        assert "private final String testVar = \"default\"" in result

    def test_format_element_details_minimal(self):
        """Test formatting with minimal element data"""
        element = {"name": "minimal"}
        result = self.formatter._format_element_details(element, "classes")
        assert "minimal" in result

    def test_format_method_signature_full(self):
        """Test formatting full method signature"""
        method = {
            "name": "complexMethod",
            "parameters": ["List<String> items", "boolean flag"],
            "modifiers": ["protected", "synchronized"],
            "return_type": "Map<String, Object>",
            "docstring": "Complex method"
        }
        result = self.formatter._format_method_signature(method)
        assert "protected synchronized complexMethod(List<String> items, boolean flag) → Map<String, Object>" in result

    def test_format_method_signature_minimal(self):
        """Test formatting minimal method signature"""
        method = {"name": "simpleMethod"}
        result = self.formatter._format_method_signature(method)
        assert "simpleMethod()" in result

    def test_format_field_signature_full(self):
        """Test formatting full field signature"""
        field = {
            "name": "complexField",
            "type": "Map<String, List<Integer>>",
            "modifiers": ["private", "static", "final"],
            "value": "new HashMap<>()",
            "docstring": "Complex field"
        }
        result = self.formatter._format_field_signature(field)
        assert "private static final Map<String, List<Integer>> complexField = new HashMap<>()" in result

    def test_format_field_signature_minimal(self):
        """Test formatting minimal field signature"""
        field = {"name": "simpleField"}
        result = self.formatter._format_field_signature(field)
        assert "simpleField" in result

    def test_extract_doc_summary_javadoc(self):
        """Test extracting JavaDoc summary"""
        javadoc = """/**
         * This is a test method that does something important.
         * It has multiple lines of documentation.
         * @param param1 The first parameter
         * @param param2 The second parameter
         * @return The result of the operation
         */"""
        result = self.formatter._extract_doc_summary(javadoc)
        assert "This is a test method that does something important." in result

    def test_extract_doc_summary_single_line(self):
        """Test extracting single line comment summary"""
        comment = "// Simple single line comment"
        result = self.formatter._extract_doc_summary(comment)
        assert "Simple single line comment" in result

    def test_extract_doc_summary_multiline(self):
        """Test extracting multiline comment summary"""
        comment = """/*
         * Multi-line comment
         * with multiple lines
         */"""
        result = self.formatter._extract_doc_summary(comment)
        assert "Multi-line comment with multiple lines" in result

    def test_extract_doc_summary_none(self):
        """Test extracting summary from None"""
        result = self.formatter._extract_doc_summary(None)
        assert result == ""

    def test_extract_doc_summary_empty(self):
        """Test extracting summary from empty string"""
        result = self.formatter._extract_doc_summary("")
        assert result == ""

    def test_clean_csv_text_with_quotes(self):
        """Test CSV text cleaning with quotes"""
        text = 'Text with "quotes" inside'
        result = self.formatter._clean_csv_text(text)
        assert '"' not in result or '""' in result

    def test_clean_csv_text_with_commas(self):
        """Test CSV text cleaning with commas"""
        text = "Text, with, commas"
        result = self.formatter._clean_csv_text(text)
        assert result.startswith('"') and result.endswith('"')

    def test_clean_csv_text_with_newlines(self):
        """Test CSV text cleaning with newlines"""
        text = "Text\nwith\nnewlines"
        result = self.formatter._clean_csv_text(text)
        assert "\n" not in result

    def test_clean_csv_text_none(self):
        """Test CSV text cleaning with None"""
        result = self.formatter._clean_csv_text(None)
        assert result == ""

    def test_format_empty_data(self):
        """Test formatting with empty data"""
        data = {}
        result = self.formatter._format_full_table(data)
        assert "Unknown" in result

    def test_format_structure_with_missing_keys(self):
        """Test format structure with missing keys"""
        data = {"file_path": "Test.java"}
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_structure_with_none_values(self):
        """Test format structure with None values"""
        data = {
            "file_path": "Test.java",
            "classes": None,
            "functions": None,
            "variables": None,
            "imports": None
        }
        result = self.formatter.format_structure(data)
        assert isinstance(result, str)

    def test_all_format_types_produce_output(self):
        """Test that all format types produce output"""
        data = {
            "file_path": "Test.java",
            "classes": [{"name": "TestClass", "line_number": 1, "methods": [], "fields": []}],
            "functions": [{"name": "testFunction", "line_number": 10}],
            "variables": [{"name": "testVariable", "line_number": 15}]
        }
        
        # Test full format
        formatter_full = JavaTableFormatter("full")
        result_full = formatter_full.format(data)
        assert len(result_full) > 0
        
        # Test compact format
        formatter_compact = JavaTableFormatter("compact")
        result_compact = formatter_compact.format(data)
        assert len(result_compact) > 0
        
        # Test CSV format
        formatter_csv = JavaTableFormatter("csv")
        result_csv = formatter_csv.format(data)
        assert len(result_csv) > 0

    def test_complex_nested_data(self):
        """Test with complex nested data structures"""
        data = {
            "file_path": "ComplexExample.java",
            "package": "com.example.complex",
            "imports": [
                {"statement": "import java.util.concurrent.ConcurrentHashMap;"},
                {"statement": "import java.util.function.Function;"}
            ],
            "classes": [
                {
                    "name": "ComplexClass",
                    "superclass": "AbstractBaseClass",
                    "interfaces": ["Serializable", "Cloneable", "Comparable<ComplexClass>"],
                    "modifiers": ["public", "final"],
                    "methods": [
                        {
                            "name": "ComplexClass",
                            "parameters": ["Map<String, Object> config", "Logger logger"],
                            "modifiers": ["public"],
                            "return_type": None,
                            "docstring": "/**\n * Complex constructor with dependency injection\n * @param config Configuration map\n * @param logger Logger instance\n */",
                            "line_number": 15
                        },
                        {
                            "name": "processData",
                            "parameters": ["List<? extends DataItem> items", "Function<DataItem, Result> processor"],
                            "modifiers": ["public", "synchronized"],
                            "return_type": "CompletableFuture<List<Result>>",
                            "docstring": "/**\n * Asynchronously processes data items\n * @param items List of data items to process\n * @param processor Function to process each item\n * @return Future containing processed results\n */",
                            "line_number": 25,
                            "complexity": 12
                        },
                        {
                            "name": "validateInput",
                            "parameters": ["Object input"],
                            "modifiers": ["private", "static"],
                            "return_type": "boolean",
                            "docstring": "// Validates input data",
                            "line_number": 45
                        }
                    ],
                    "fields": [
                        {
                            "name": "CONFIG_CACHE",
                            "type": "Map<String, Object>",
                            "modifiers": ["private", "static", "final"],
                            "value": "new ConcurrentHashMap<>()",
                            "docstring": "/** Thread-safe configuration cache */",
                            "line_number": 8
                        },
                        {
                            "name": "logger",
                            "type": "Logger",
                            "modifiers": ["private", "final"],
                            "value": None,
                            "docstring": "// Logger instance for this class",
                            "line_number": 10
                        }
                    ],
                    "docstring": "/**\n * Complex class demonstrating various Java features\n * including generics, concurrency, and functional programming.\n * \n * @author Example Author\n * @version 1.0\n * @since 2023\n */",
                    "line_number": 5,
                    "is_abstract": False,
                    "is_interface": False
                }
            ],
            "functions": [
                {
                    "name": "utilityMethod",
                    "parameters": ["String... args"],
                    "modifiers": ["public", "static"],
                    "return_type": "Optional<String>",
                    "docstring": "/**\n * Utility method with varargs\n * @param args Variable arguments\n * @return Optional result\n */",
                    "line_number": 60,
                    "complexity": 3
                }
            ],
            "variables": [
                {
                    "name": "DEFAULT_TIMEOUT",
                    "type": "Duration",
                    "modifiers": ["public", "static", "final"],
                    "value": "Duration.ofSeconds(30)",
                    "docstring": "/** Default timeout for operations */",
                    "line_number": 3
                }
            ]
        }
        
        result = self.formatter.format(data)
        assert "ComplexClass" in result
        assert "AbstractBaseClass" in result
        assert "Serializable, Cloneable, Comparable<ComplexClass>" in result
        assert "processData" in result
        assert "CompletableFuture<List<Result>>" in result
        assert "CONFIG_CACHE" in result
        assert "ConcurrentHashMap" in result
        assert "utilityMethod" in result
        assert "DEFAULT_TIMEOUT" in result

    def test_generic_types_handling(self):
        """Test handling of generic types"""
        data = {
            "file_path": "Generic.java",
            "classes": [
                {
                    "name": "GenericClass",
                    "methods": [
                        {
                            "name": "genericMethod",
                            "parameters": ["T input", "Class<? extends T> clazz"],
                            "return_type": "Optional<T>",
                            "modifiers": ["public"]
                        }
                    ],
                    "fields": [
                        {
                            "name": "genericField",
                            "type": "Map<String, List<? super Number>>",
                            "modifiers": ["private"]
                        }
                    ]
                }
            ]
        }
        
        result = self.formatter.format(data)
        assert "Optional<T>" in result
        assert "Class<? extends T>" in result
        assert "Map<String, List<? super Number>>" in result

    def test_annotation_handling(self):
        """Test handling of annotations"""
        data = {
            "file_path": "Annotated.java",
            "classes": [
                {
                    "name": "AnnotatedClass",
                    "methods": [
                        {
                            "name": "annotatedMethod",
                            "modifiers": ["@Override", "public"],
                            "parameters": [],
                            "return_type": "void"
                        }
                    ],
                    "fields": [
                        {
                            "name": "annotatedField",
                            "type": "String",
                            "modifiers": ["@Autowired", "private"]
                        }
                    ]
                }
            ]
        }
        
        result = self.formatter.format(data)
        assert "@Override public" in result
        assert "@Autowired private" in result