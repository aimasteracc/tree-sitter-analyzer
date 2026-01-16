#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.languages.java_plugin module.

This module tests the JavaPlugin class which provides Java language
support in the new plugin architecture.
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor, JavaPlugin
from tree_sitter_analyzer.models import Class, Function, Import
from tree_sitter_analyzer.plugins.base import ElementExtractor, LanguagePlugin


class TestJavaElementExtractor:
    """Test cases for JavaElementExtractor class"""

    @pytest.fixture
    def extractor(self) -> JavaElementExtractor:
        """Create a JavaElementExtractor instance for testing"""
        return JavaElementExtractor()

    @pytest.fixture
    def mock_tree(self) -> Mock:
        """Create a mock tree-sitter tree"""
        tree = Mock()
        root_node = Mock()
        root_node.children = []
        tree.root_node = root_node
        tree.language = Mock()
        return tree

    @pytest.fixture
    def sample_java_code(self) -> str:
        """Sample Java code for testing"""
        return """
package com.example;

import java.util.List;
import java.util.ArrayList;

/**
 * Calculator class for basic arithmetic operations
 */
public class Calculator {
    private int value;
    private static final String VERSION = "1.0";

    /**
     * Constructor
     */
    public Calculator(int initialValue) {
        this.value = initialValue;
    }

    /**
     * Add a number to the current value
     */
    public int add(int number) {
        return value + number;
    }

    /**
     * Get the current value
     */
    public int getValue() {
        return value;
    }

    private void reset() {
        this.value = 0;
    }
}
"""

    def test_extractor_initialization(self, extractor: JavaElementExtractor) -> None:
        """Test JavaElementExtractor initialization"""
        assert extractor is not None
        assert isinstance(extractor, ElementExtractor)
        assert hasattr(extractor, "extract_functions")
        assert hasattr(extractor, "extract_classes")
        assert hasattr(extractor, "extract_variables")
        assert hasattr(extractor, "extract_imports")

    def test_extract_functions_success(
        self, extractor: JavaElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful function extraction"""
        # Mock the language query
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"method.declaration": []}

        functions = extractor.extract_functions(mock_tree, "test code")

        assert isinstance(functions, list)

    def test_extract_functions_no_language(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test function extraction when language is not available"""
        mock_tree = Mock()
        mock_tree.language = None
        # Mock root_node with children that can be reversed
        mock_root = Mock()
        mock_root.children = []  # Empty list that can be reversed
        mock_tree.root_node = mock_root

        functions = extractor.extract_functions(mock_tree, "test code")

        assert isinstance(functions, list)
        assert len(functions) == 0

    def test_extract_classes_success(
        self, extractor: JavaElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful class extraction"""
        # Mock the language query
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"class.declaration": []}

        classes = extractor.extract_classes(mock_tree, "test code")

        assert isinstance(classes, list)

    def test_extract_variables_success(
        self, extractor: JavaElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful variable extraction"""
        # Mock the language query
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"field.declaration": []}

        variables = extractor.extract_variables(mock_tree, "test code")

        assert isinstance(variables, list)

    def test_extract_imports_success(
        self, extractor: JavaElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful import extraction"""
        # Mock the language query
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"import.declaration": []}

        imports = extractor.extract_imports(mock_tree, "test code")

        assert isinstance(imports, list)

    def test_extract_method_optimized(self, extractor: JavaElementExtractor) -> None:
        """Test optimized method extraction"""
        mock_node = Mock()
        mock_node.type = "method_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.children = []

        result = extractor._extract_method_optimized(mock_node)

        # The method should handle the mock gracefully
        assert result is None or isinstance(result, Function)

    def test_extract_class_optimized(self, extractor: JavaElementExtractor) -> None:
        """Test optimized class extraction"""
        mock_node = Mock()
        mock_node.type = "class_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.children = []

        result = extractor._extract_class_optimized(mock_node)

        # The method should handle the mock gracefully
        assert result is None or isinstance(result, Class)

    def test_extract_field_optimized(self, extractor: JavaElementExtractor) -> None:
        """Test field information extraction"""
        mock_node = Mock()
        mock_node.type = "field_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 20
        mock_node.children = []

        result = extractor._extract_field_optimized(mock_node)

        # The method should handle the mock gracefully and return a list
        assert isinstance(result, list)

    def test_extract_import_info(self, extractor: JavaElementExtractor) -> None:
        """Test import information extraction"""
        mock_node = Mock()
        mock_node.type = "import_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 25
        mock_node.children = []

        result = extractor._extract_import_info(mock_node, "import java.util.List;")

        # The method should handle gracefully
        assert result is None or isinstance(result, Import)

    def test_extract_class_name(self, extractor: JavaElementExtractor) -> None:
        """Test class name extraction from node"""
        mock_node = Mock()
        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_identifier.text = b"TestClass"
        mock_node.children = [mock_identifier]

        # Mock the _get_node_text_optimized method to return our expected value
        with patch.object(
            extractor, "_get_node_text_optimized", return_value="TestClass"
        ):
            name = extractor._extract_class_name(mock_node)

            assert name == "TestClass"

    def test_extract_class_name_no_identifier(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test class name extraction when no identifier is found"""
        mock_node = Mock()
        mock_node.children = []

        name = extractor._extract_class_name(mock_node)

        assert name is None

    def test_calculate_complexity_optimized(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test complexity calculation"""
        # Create mock nodes for testing complexity
        simple_node = Mock()
        simple_node.type = "return_statement"
        simple_node.children = []

        complex_node = Mock()
        complex_node.type = "if_statement"
        complex_node.children = [
            Mock(),
            Mock(),
            Mock(),
        ]  # Multiple children for complexity

        simple_complexity = extractor._calculate_complexity_optimized(simple_node)
        complex_complexity = extractor._calculate_complexity_optimized(complex_node)

        assert isinstance(simple_complexity, int)
        assert isinstance(complex_complexity, int)
        assert simple_complexity >= 1
        assert complex_complexity >= 1


class TestJavaPlugin:
    """Test cases for JavaPlugin class"""

    @pytest.fixture
    def plugin(self) -> JavaPlugin:
        """Create a JavaPlugin instance for testing"""
        return JavaPlugin()

    def test_plugin_initialization(self, plugin: JavaPlugin) -> None:
        """Test JavaPlugin initialization"""
        assert plugin is not None
        assert isinstance(plugin, LanguagePlugin)
        assert hasattr(plugin, "get_language_name")
        assert hasattr(plugin, "get_file_extensions")
        assert hasattr(plugin, "create_extractor")

    def test_get_language_name(self, plugin: JavaPlugin) -> None:
        """Test getting language name"""
        language_name = plugin.get_language_name()

        assert language_name == "java"

    def test_get_file_extensions(self, plugin: JavaPlugin) -> None:
        """Test getting file extensions"""
        extensions = plugin.get_file_extensions()

        assert isinstance(extensions, list)
        assert ".java" in extensions

    def test_create_extractor(self, plugin: JavaPlugin) -> None:
        """Test creating element extractor"""
        extractor = plugin.create_extractor()

        assert isinstance(extractor, JavaElementExtractor)
        assert isinstance(extractor, ElementExtractor)

    def test_is_applicable_java_file(self, plugin: JavaPlugin) -> None:
        """Test applicability check for Java file"""
        is_applicable = plugin.is_applicable("test.java")

        assert is_applicable is True

    def test_is_applicable_non_java_file(self, plugin: JavaPlugin) -> None:
        """Test applicability check for non-Java file"""
        is_applicable = plugin.is_applicable("test.py")

        assert is_applicable is False

    def test_get_plugin_info(self, plugin: JavaPlugin) -> None:
        """Test getting plugin information"""
        info = plugin.get_plugin_info()

        assert isinstance(info, dict)
        assert "language" in info
        assert "extensions" in info
        assert info["language"] == "java"

    def test_get_tree_sitter_language(self, plugin: JavaPlugin) -> None:
        """Test getting tree-sitter language"""
        with (
            patch("tree_sitter_java.language") as mock_language,
            patch("tree_sitter.Language") as mock_language_constructor,
        ):
            mock_lang_obj = Mock()
            mock_language.return_value = mock_lang_obj
            mock_language_constructor.return_value = mock_lang_obj

            language = plugin.get_tree_sitter_language()

            assert language is mock_lang_obj

    def test_get_tree_sitter_language_caching(self, plugin: JavaPlugin) -> None:
        """Test tree-sitter language caching"""
        with (
            patch("tree_sitter_java.language") as mock_language,
            patch("tree_sitter.Language") as mock_language_constructor,
        ):
            mock_lang_obj = Mock()
            mock_language.return_value = mock_lang_obj
            mock_language_constructor.return_value = mock_lang_obj

            # First call
            language1 = plugin.get_tree_sitter_language()

            # Second call (should use cache)
            language2 = plugin.get_tree_sitter_language()

            assert language1 is language2
            # Should only be called once due to caching
            mock_language.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_file_success(self, plugin: JavaPlugin) -> None:
        """Test successful file analysis"""
        java_code = """
public class TestClass {
    public void testMethod() {
        System.out.println("Hello");
    }
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            # Mock AnalysisRequest
            mock_request = Mock()
            mock_request.file_path = temp_path
            mock_request.language = "java"
            mock_request.include_complexity = False
            mock_request.include_details = False

            result = await plugin.analyze_file(temp_path, mock_request)

            assert result is not None
            assert hasattr(result, "success")
            assert hasattr(result, "file_path")
            assert hasattr(result, "language")

        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_analyze_file_nonexistent(self, plugin: JavaPlugin) -> None:
        """Test analysis of non-existent file"""
        mock_request = Mock()
        mock_request.file_path = "/nonexistent/file.java"
        mock_request.language = "java"

        result = await plugin.analyze_file("/nonexistent/file.java", mock_request)

        # Should return an AnalysisResult with success=False instead of raising
        assert result is not None
        assert hasattr(result, "success")
        assert result.success is False


class TestJavaPluginErrorHandling:
    """Test error handling in JavaPlugin"""

    @pytest.fixture
    def plugin(self) -> JavaPlugin:
        """Create a JavaPlugin instance for testing"""
        return JavaPlugin()

    @pytest.fixture
    def extractor(self) -> JavaElementExtractor:
        """Create a JavaElementExtractor instance for testing"""
        return JavaElementExtractor()

    def test_extract_functions_with_exception(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test function extraction with exception"""
        mock_tree = Mock()
        mock_tree.language = None  # This will cause the extraction to fail gracefully
        # Mock root_node with children that can be reversed
        mock_root = Mock()
        mock_root.children = []  # Empty list that can be reversed
        mock_tree.root_node = mock_root

        functions = extractor.extract_functions(mock_tree, "test code")

        # Should handle gracefully
        assert isinstance(functions, list)
        assert len(functions) == 0

    def test_extract_classes_with_exception(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test class extraction with exception"""
        mock_tree = Mock()
        mock_tree.language = None  # This will cause the extraction to fail gracefully
        # Mock root_node with children that can be reversed
        mock_root = Mock()
        mock_root.children = []  # Empty list that can be reversed
        mock_tree.root_node = mock_root

        classes = extractor.extract_classes(mock_tree, "test code")

        # Should handle gracefully
        assert isinstance(classes, list)
        assert len(classes) == 0

    def test_extract_method_optimized_with_exception(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test optimized method extraction with exception"""
        mock_node = Mock()
        mock_node.type = "method_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.children = []

        # Mock an exception during processing
        with patch.object(extractor, "_extract_class_name") as mock_extract:
            mock_extract.side_effect = Exception("Extraction error")

            result = extractor._extract_method_optimized(mock_node)

            # Should handle gracefully
            assert result is None

    def test_get_tree_sitter_language_failure(self, plugin: JavaPlugin) -> None:
        """Test tree-sitter language loading failure"""
        with patch("tree_sitter_java.language") as mock_language:
            mock_language.side_effect = ImportError("Module not found")

            language = plugin.get_tree_sitter_language()

            assert language is None

    @pytest.mark.asyncio
    async def test_analyze_file_with_exception(self, plugin: JavaPlugin) -> None:
        """Test file analysis with exception"""
        java_code = "public class Test {}"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            mock_request = Mock()
            mock_request.file_path = temp_path
            mock_request.language = "java"

            # Mock read_file_safe_async on the plugin module, as that's where it's imported
            # OR where it's used. The error message shows it's called in java_plugin.py
            # The test previously patched 'tree_sitter_analyzer.encoding_utils.read_file_safe_async'
            # But maybe the import in java_plugin.py is 'from ... import read_file_safe_async'
            # If so, we need to patch 'tree_sitter_analyzer.languages.java_plugin.read_file_safe_async'

            with patch(
                "tree_sitter_analyzer.languages.java_plugin.read_file_safe_async"
            ) as mock_read:
                mock_read.side_effect = Exception("Read error")

                result = await plugin.analyze_file(temp_path, mock_request)

                # Should return error result instead of raising
                assert result is not None
                assert hasattr(result, "success")
                assert result.success is False

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestJavaPluginIntegration:
    """Integration tests for JavaPlugin"""

    @pytest.fixture
    def plugin(self) -> JavaPlugin:
        """Create a JavaPlugin instance for testing"""
        return JavaPlugin()

    def test_full_extraction_workflow(self, plugin: JavaPlugin) -> None:
        """Test complete extraction workflow"""
        # Test that plugin can handle complex Java code

        # Test that plugin can handle complex Java code
        extractor = plugin.create_extractor()
        assert isinstance(extractor, JavaElementExtractor)

        # Test applicability
        assert plugin.is_applicable("Calculator.java") is True
        assert plugin.is_applicable("calculator.py") is False

        # Test plugin info
        info = plugin.get_plugin_info()
        assert info["language"] == "java"
        assert ".java" in info["extensions"]

    def test_plugin_consistency(self, plugin: JavaPlugin) -> None:
        """Test plugin consistency across multiple calls"""
        # Multiple calls should return consistent results
        for _ in range(5):
            assert plugin.get_language_name() == "java"
            assert ".java" in plugin.get_file_extensions()
            assert isinstance(plugin.create_extractor(), JavaElementExtractor)

    def test_extractor_consistency(self, plugin: JavaPlugin) -> None:
        """Test extractor consistency"""
        # Multiple extractors should be independent
        extractor1 = plugin.create_extractor()
        extractor2 = plugin.create_extractor()

        assert extractor1 is not extractor2
        assert isinstance(extractor1, JavaElementExtractor)
        assert isinstance(extractor2, JavaElementExtractor)

    def test_plugin_with_various_java_files(self, plugin: JavaPlugin) -> None:
        """Test plugin with various Java file types"""
        java_files = [
            "Test.java",
            "com/example/Test.java",
            "src/main/java/Test.java",
            "TEST.JAVA",  # Case variations
            "test.Java",
        ]

        for java_file in java_files:
            assert plugin.is_applicable(java_file) is True

        non_java_files = [
            "test.py",
            "test.js",
            "test.cpp",
            "test.txt",
            "java.txt",  # Contains 'java' but wrong extension
        ]

        for non_java_file in non_java_files:
            assert plugin.is_applicable(non_java_file) is False
