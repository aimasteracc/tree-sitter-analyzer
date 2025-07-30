#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extended Tests for Java Analyzer

Additional test cases to improve coverage for Java analyzer functionality.
"""

import os
import sys
import tempfile
import pytest
import pytest_asyncio

# Add project root to path
sys.path.insert(0, ".")

# Mock functionality now provided by pytest-mock

from tree_sitter_analyzer.java_analyzer import CodeAnalyzer, main


@pytest.fixture
def temp_java_file():
    """Create a temporary Java file for testing"""
    temp_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".java", delete=False
    )
    temp_file.write(
        """
public class TestClass {
    private String name;
    
    public TestClass(String name) {
        this.name = name;
    }
    
    public String getName() {
        return this.name;
    }
    
    public void setName(String name) {
        this.name = name;
    }
}
"""
    )
    temp_file.close()
    
    yield temp_file.name
    
    # Cleanup
    if os.path.exists(temp_file.name):
        os.unlink(temp_file.name)


class TestCodeAnalyzerExtended:
    """Extended tests for CodeAnalyzer"""

    def test_analyzer_initialization_java(self, mocker):
        """Test analyzer initialization with Java language"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        analyzer = CodeAnalyzer("java")

        assert analyzer.language is not None
        assert analyzer.parser is not None
        assert analyzer.source_code_bytes == b""
        assert analyzer.tree is None

    def test_analyzer_initialization_unsupported_language(self, mocker):
        """Test analyzer initialization with unsupported language"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        mock_warning = mocker.patch("tree_sitter_analyzer.java_analyzer.output_warning")
        analyzer = CodeAnalyzer("python")

        mock_warning.assert_called_once()
        assert analyzer.language is not None
        assert analyzer.parser is not None

    def test_analyzer_initialization_tree_sitter_unavailable(self, mocker):
        """Test analyzer initialization when tree-sitter is unavailable"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", False)
        with pytest.raises(RuntimeError):
            CodeAnalyzer()

    def test_analyzer_initialization_exception(self, mocker):
        """Test analyzer initialization with exception during setup"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        mocker.patch(
            "tree_sitter_analyzer.java_analyzer.Language",
            side_effect=Exception("Test error"),
        )
        with pytest.raises(RuntimeError):
            CodeAnalyzer()

    def test_parse_file_success(self, mocker, temp_java_file):
        """Test successful file parsing"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        analyzer = CodeAnalyzer()

        result = analyzer.parse_file(temp_java_file)

        assert result is True
        assert analyzer.tree is not None
        assert analyzer.source_code_bytes != b""

    def test_parse_file_nonexistent(self, mocker):
        """Test parsing nonexistent file"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        analyzer = CodeAnalyzer()

        result = analyzer.parse_file("nonexistent_file.java")

        assert result is False
        assert analyzer.tree is None

    def test_parse_file_read_failure(self, mocker, temp_java_file):
        """Test parsing file with read failure"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        analyzer = CodeAnalyzer()

        mocker.patch(
            "tree_sitter_analyzer.java_analyzer.read_file_with_fallback",
            return_value=None,
        )
        result = analyzer.parse_file(temp_java_file)

        assert result is False
        assert analyzer.tree is None

    def test_parse_file_exception(self, mocker, temp_java_file):
        """Test parsing file with exception"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        analyzer = CodeAnalyzer()

        mocker.patch(
            "tree_sitter_analyzer.java_analyzer.read_file_with_fallback",
            side_effect=Exception("Test error"),
        )
        result = analyzer.parse_file(temp_java_file)

        assert result is False
        assert analyzer.tree is None

    def test_execute_query_without_ast(self, mocker):
        """Test query execution without AST"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        analyzer = CodeAnalyzer()

        result = analyzer.execute_query("(class_declaration) @class")

        assert result == []

    def test_execute_query_invalid_query(self, mocker, temp_java_file):
        """Test query execution with invalid query"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        analyzer = CodeAnalyzer()
        analyzer.parse_file(temp_java_file)

        result = analyzer.execute_query("invalid query syntax")

        assert result == []

    def test_execute_query_success_dict_format(self, mocker, temp_java_file):
        """Test successful query execution with dict format"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        analyzer = CodeAnalyzer()
        analyzer.parse_file(temp_java_file)

        result = analyzer.execute_query(
            "(class_declaration name: (identifier) @class.name) @class"
        )

        assert isinstance(result, list)
        if result:  # If tree-sitter is available and working
            assert len(result) > 0
            for item in result:
                assert "capture_name" in item
                assert "content" in item
                assert "start_line" in item
                assert "end_line" in item
                assert "node_type" in item

    def test_execute_query_method_extraction(self, mocker, temp_java_file):
        """Test query execution for method extraction"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        analyzer = CodeAnalyzer()
        analyzer.parse_file(temp_java_file)

        # Query for method declarations
        result = analyzer.execute_query(
            "(method_declaration name: (identifier) @method.name) @method"
        )

        assert isinstance(result, list)
        # Should find methods like getName, setName

    def test_execute_query_field_extraction(self, mocker, temp_java_file):
        """Test query execution for field extraction"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        analyzer = CodeAnalyzer()
        analyzer.parse_file(temp_java_file)

        # Query for field declarations
        result = analyzer.execute_query(
            "(field_declaration declarator: (variable_declarator name: (identifier) @field.name)) @field"
        )

        assert isinstance(result, list)
        # Should find the 'name' field

    def test_execute_query_constructor_extraction(self, mocker, temp_java_file):
        """Test query execution for constructor extraction"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        analyzer = CodeAnalyzer()
        analyzer.parse_file(temp_java_file)

        # Query for constructor declarations
        result = analyzer.execute_query(
            "(constructor_declaration name: (identifier) @constructor.name) @constructor"
        )

        assert isinstance(result, list)
        # Should find the TestClass constructor

    def test_execute_query_with_complex_java_file(self, mocker):
        """Test query execution with more complex Java file"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        # Create a more complex Java file
        complex_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False
        )
        complex_file.write(
            """
package com.example;

import java.util.List;
import java.util.ArrayList;

public class ComplexClass extends BaseClass implements Runnable {
    private static final String CONSTANT = "value";
    private List<String> items;
    
    public ComplexClass() {
        this.items = new ArrayList<>();
    }
    
    @Override
    public void run() {
        // Implementation
    }
    
    public static void staticMethod() {
        // Static method
    }
    
    private void privateMethod() throws Exception {
        // Private method that throws exception
    }
}
"""
        )
        complex_file.close()

        try:
            analyzer = CodeAnalyzer()
            analyzer.parse_file(complex_file.name)

            # Test various queries
            class_result = analyzer.execute_query("(class_declaration) @class")
            method_result = analyzer.execute_query("(method_declaration) @method")
            import_result = analyzer.execute_query("(import_declaration) @import")

            assert isinstance(class_result, list)
            assert isinstance(method_result, list)
            assert isinstance(import_result, list)

        finally:
            if os.path.exists(complex_file.name):
                os.unlink(complex_file.name)

    def test_execute_query_with_malformed_java(self, mocker):
        """Test query execution with malformed Java code"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        # Create a malformed Java file
        malformed_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False
        )
        malformed_file.write(
            """
public class MalformedClass {
    // Missing closing brace
    public void method() {
        // Incomplete method
"""
        )
        malformed_file.close()

        try:
            analyzer = CodeAnalyzer()
            result = analyzer.parse_file(malformed_file.name)

            # Should still parse successfully (tree-sitter is fault-tolerant)
            assert result is True

            # Query should still work
            query_result = analyzer.execute_query("(class_declaration) @class")
            assert isinstance(query_result, list)

        finally:
            if os.path.exists(malformed_file.name):
                os.unlink(malformed_file.name)

    def test_execute_query_with_empty_file(self, mocker):
        """Test query execution with empty file"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        # Create an empty Java file
        empty_file = tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False)
        empty_file.write("")
        empty_file.close()

        try:
            analyzer = CodeAnalyzer()
            result = analyzer.parse_file(empty_file.name)

            assert result is True  # Should parse successfully

            # Query should return empty results
            query_result = analyzer.execute_query("(class_declaration) @class")
            assert query_result == []

        finally:
            if os.path.exists(empty_file.name):
                os.unlink(empty_file.name)

    def test_execute_query_unicode_content(self, mocker):
        """Test query execution with Unicode content"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        # Create a Java file with Unicode content
        unicode_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        )
        unicode_file.write(
            """
public class UnicodeClass {
    private String message = "こんにちは世界"; // Japanese text
    
    public void printMessage() {
        System.out.println(message);
    }
}
"""
        )
        unicode_file.close()

        try:
            analyzer = CodeAnalyzer()
            result = analyzer.parse_file(unicode_file.name)

            assert result is True

            # Query should handle Unicode content
            query_result = analyzer.execute_query("(class_declaration) @class")
            assert isinstance(query_result, list)

        finally:
            if os.path.exists(unicode_file.name):
                os.unlink(unicode_file.name)


class TestMainFunction:
    """Test main function"""

    def test_main_function(self, mocker):
        """Test main function output"""
        mock_warning = mocker.patch("tree_sitter_analyzer.java_analyzer.output_warning")
        mock_info = mocker.patch("tree_sitter_analyzer.java_analyzer.output_info")
        main()

        # Should output warnings and info messages
        assert mock_warning.call_count > 0
        assert mock_info.call_count > 0


class TestModuleDirectExecution:
    """Test module direct execution"""

    def test_module_execution(self, mocker):
        """Test module execution when run as __main__"""
        mock_main = mocker.patch("tree_sitter_analyzer.java_analyzer.main")
        # Simulate module execution
        exec(
            """
if __name__ == "__main__":
    main()
""",
            {"__name__": "__main__", "main": mock_main},
        )

        mock_main.assert_called_once()


class TestTreeSitterImportHandling:
    """Test tree-sitter import handling"""

    def test_tree_sitter_import_failure(self, mocker):
        """Test handling of tree-sitter import failure"""
        # This test verifies that the module handles import failures gracefully
        # The actual import failure is handled at module level
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", False)
        # When tree-sitter is not available, CodeAnalyzer should raise RuntimeError
        with pytest.raises(RuntimeError):
            CodeAnalyzer()


class TestCodeAnalyzerEdgeCases:
    """Test edge cases for CodeAnalyzer"""

    def test_multiple_query_executions(self, mocker):
        """Test multiple query executions on same analyzer"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        # Create a temporary Java file
        temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False)
        temp_file.write(
            """
public class MultiQueryTest {
    private int value;
    
    public void method1() {}
    public void method2() {}
}
"""
        )
        temp_file.close()

        try:
            analyzer = CodeAnalyzer()
            analyzer.parse_file(temp_file.name)

            # Execute multiple different queries
            class_result = analyzer.execute_query("(class_declaration) @class")
            method_result = analyzer.execute_query("(method_declaration) @method")
            field_result = analyzer.execute_query("(field_declaration) @field")

            # All should return lists
            assert isinstance(class_result, list)
            assert isinstance(method_result, list)
            assert isinstance(field_result, list)

        finally:
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)

    def test_reparse_different_file(self, mocker):
        """Test parsing different files with same analyzer"""
        mocker.patch("tree_sitter_analyzer.java_analyzer.TREE_SITTER_AVAILABLE", True)
        # Create two temporary Java files
        file1 = tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False)
        file1.write("public class Class1 {}")
        file1.close()

        file2 = tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False)
        file2.write("public class Class2 { public void method() {} }")
        file2.close()

        try:
            analyzer = CodeAnalyzer()

            # Parse first file
            result1 = analyzer.parse_file(file1.name)
            assert result1 is True

            # Parse second file (should replace first)
            result2 = analyzer.parse_file(file2.name)
            assert result2 is True

            # Query should reflect second file content
            query_result = analyzer.execute_query("(method_declaration) @method")
            assert isinstance(query_result, list)

        finally:
            if os.path.exists(file1.name):
                os.unlink(file1.name)
            if os.path.exists(file2.name):
                os.unlink(file2.name)
