#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Java Plugin Coverage Enhancement

Additional tests to improve coverage for plugins/java_plugin.py
"""

import sys
import pytest
import pytest_asyncio

# Add project root to path
sys.path.insert(0, ".")

# Mock functionality now provided by pytest-mock

from tree_sitter_analyzer.plugins.java_plugin import JavaElementExtractor, JavaPlugin


@pytest.fixture
def java_extractor():
    """Fixture for JavaElementExtractor instance"""
    return JavaElementExtractor()


@pytest.fixture
def java_plugin():
    """Fixture for JavaPlugin instance"""
    return JavaPlugin()


class TestJavaElementExtractorAdvanced:
    """Test advanced Java element extractor functionality"""

    def test_extract_detailed_method_info_with_exception(self, java_extractor, mocker):
        """Test detailed method info extraction with exception"""
        mock_node = mocker.MagicMock()
        mock_node.children = None  # This will cause an exception

        source_code = "public void testMethod() {}"

        result = java_extractor._extract_detailed_method_info(
            mock_node, source_code, False
        )

        assert result is None

    def test_extract_detailed_class_info_with_exception(self, java_extractor, mocker):
        """Test detailed class info extraction with exception"""
        mock_node = mocker.MagicMock()
        mock_node.children = None  # This will cause an exception

        source_code = "public class TestClass {}"

        result = java_extractor._extract_detailed_class_info(
            mock_node, source_code, "class"
        )

        assert result is None

    def test_extract_return_type_from_node(self, java_extractor, mocker):
        """Test return type extraction from method node"""
        mock_type_node = mocker.MagicMock()
        mock_type_node.type = "type_identifier"
        mock_type_node.start_byte = 7
        mock_type_node.end_byte = 13

        mock_node = mocker.MagicMock()
        mock_node.children = [mock_type_node]

        source_code = "public String testMethod() {}"

        return_type = java_extractor._extract_return_type_from_node(
            mock_node, source_code
        )

        assert return_type == "String"

    def test_extract_return_type_from_node_no_type(self, java_extractor, mocker):
        """Test return type extraction when no type found"""
        mock_node = mocker.MagicMock()
        mock_node.children = []

        source_code = "public void testMethod() {}"

        return_type = java_extractor._extract_return_type_from_node(
            mock_node, source_code
        )

        assert return_type == "void"

    def test_extract_modifiers_from_node_with_modifiers(self, java_extractor, mocker):
        """Test modifier extraction with actual modifiers"""
        mock_modifiers_node = mocker.MagicMock()
        mock_modifiers_node.type = "modifiers"
        mock_modifiers_node.start_byte = 0
        mock_modifiers_node.end_byte = 13

        mock_node = mocker.MagicMock()
        mock_node.children = [mock_modifiers_node]

        source_code = "public static void testMethod() {}"

        modifiers = java_extractor._extract_modifiers_from_node(mock_node, source_code)

        assert "public" in modifiers
        assert "static" in modifiers

    def test_extract_modifiers_from_node_no_modifiers(self, java_extractor, mocker):
        """Test modifier extraction when no modifiers found"""
        mock_node = mocker.MagicMock()
        mock_node.children = []

        source_code = "void testMethod() {}"

        modifiers = java_extractor._extract_modifiers_from_node(mock_node, source_code)

        assert modifiers == []

    def test_extract_annotations_from_node(self, java_extractor, mocker):
        """Test annotation extraction from node"""
        mock_node = mocker.MagicMock()
        mock_node.children = []

        source_code = "@Override public void testMethod() {}"

        annotations = java_extractor._extract_annotations_from_node(
            mock_node, source_code
        )

        assert isinstance(annotations, list)

    def test_generate_method_signature(self, java_extractor):
        """Test method signature generation"""
        name = "testMethod"
        return_type = "String"
        parameters = ["int param1", "String param2"]
        modifiers = ["public", "static"]

        signature = java_extractor._generate_method_signature(
            name, return_type, parameters, modifiers
        )

        assert "public static" in signature
        assert "String testMethod" in signature
        assert "int param1, String param2" in signature

    def test_calculate_complexity(self, java_extractor):
        """Test complexity calculation"""
        body = """
        {
            if (condition) {
                for (int i = 0; i < 10; i++) {
                    if (i % 2 == 0) {
                        System.out.println(i);
                    }
                }
            }
        }
        """

        complexity = java_extractor._calculate_complexity(body)

        assert complexity > 1

    def test_extract_field_info_with_exception(self, java_extractor, mocker):
        """Test field info extraction with exception"""
        mock_node = mocker.MagicMock()
        mock_node.start_byte = None  # This will cause an exception

        source_code = "private String field;"

        result = java_extractor._extract_field_info(mock_node, source_code)

        assert result is None

    def test_extract_import_info_with_exception(self, java_extractor, mocker):
        """Test import info extraction with exception"""
        mock_node = mocker.MagicMock()
        mock_node.start_byte = None  # This will cause an exception

        source_code = "import java.util.List;"

        result = java_extractor._extract_import_info(mock_node, source_code)

        assert result is None

    def test_extract_functions_with_no_language(self, java_extractor, mocker):
        """Test function extraction when tree has no language"""
        mock_tree = mocker.MagicMock()
        mock_tree.language = None

        source_code = "public void testMethod() {}"

        functions = java_extractor.extract_functions(mock_tree, source_code)

        assert functions == []

    def test_extract_classes_with_no_language(self, java_extractor, mocker):
        """Test class extraction when tree has no language"""
        mock_tree = mocker.MagicMock()
        mock_tree.language = None

        source_code = "public class TestClass {}"

        classes = java_extractor.extract_classes(mock_tree, source_code)

        assert classes == []

    def test_extract_variables_with_no_language(self, java_extractor, mocker):
        """Test variable extraction when tree has no language"""
        mock_tree = mocker.MagicMock()
        mock_tree.language = None

        source_code = "private String field;"

        variables = java_extractor.extract_variables(mock_tree, source_code)

        assert variables == []

    def test_extract_imports_with_no_language(self, java_extractor, mocker):
        """Test import extraction when tree has no language"""
        mock_tree = mocker.MagicMock()
        mock_tree.language = None

        source_code = "import java.util.List;"

        imports = java_extractor.extract_imports(mock_tree, source_code)

        assert imports == []


class TestJavaPluginAdvanced:
    """Test advanced Java plugin functionality"""

    def test_get_language_name(self, java_plugin):
        """Test language name method"""
        assert java_plugin.get_language_name() == "java"

    def test_get_file_extensions(self, java_plugin):
        """Test file extensions method"""
        extensions = java_plugin.get_file_extensions()
        assert ".java" in extensions
        assert ".jsp" in extensions
        assert ".jspx" in extensions

    def test_create_extractor(self, java_plugin):
        """Test extractor creation method"""
        extractor = java_plugin.create_extractor()
        assert isinstance(extractor, JavaElementExtractor)

    def test_get_tree_sitter_language_caching(self, java_plugin):
        """Test tree-sitter language caching"""
        # First call
        language1 = java_plugin.get_tree_sitter_language()

        # Second call should return cached result
        language2 = java_plugin.get_tree_sitter_language()

        # Should be the same object (cached)
        assert language1 is language2

    def test_get_tree_sitter_language_with_mock_loader(self, mocker):
        """Test tree-sitter language loading with mock loader"""
        mock_language = mocker.MagicMock()
        mock_loader = mocker.patch("tree_sitter_analyzer.plugins.java_plugin.loader")
        mock_loader.load_language.return_value = mock_language

        plugin = JavaPlugin()  # Fresh instance
        language = plugin.get_tree_sitter_language()

        mock_loader.load_language.assert_called_once_with("java")
        assert language == mock_language


class TestJavaElementExtractorEdgeCases:
    """Test edge cases for Java element extractor"""

    def test_extract_with_complex_tree_structure(self, java_extractor, mocker):
        """Test extraction with complex tree structure"""
        # Mock a complex tree with nested nodes
        mock_tree = mocker.MagicMock()
        mock_language = mocker.MagicMock()
        mock_query = mocker.MagicMock()

        # Mock query results as list instead of dict
        mock_query.captures.return_value = []
        mock_language.query.return_value = mock_query
        mock_tree.language = mock_language
        mock_tree.root_node = mocker.MagicMock()

        source_code = """
        public class TestClass {
            public void method1() {}
            private String field;
        }
        """

        # Test all extraction methods
        functions = java_extractor.extract_functions(mock_tree, source_code)
        classes = java_extractor.extract_classes(mock_tree, source_code)
        variables = java_extractor.extract_variables(mock_tree, source_code)
        imports = java_extractor.extract_imports(mock_tree, source_code)

        assert isinstance(functions, list)
        assert isinstance(classes, list)
        assert isinstance(variables, list)
        assert isinstance(imports, list)

    def test_extract_with_query_exception(self, java_extractor, mocker):
        """Test extraction when query raises exception"""
        mock_tree = mocker.MagicMock()
        mock_language = mocker.MagicMock()
        mock_language.query.side_effect = Exception("Query error")
        mock_tree.language = mock_language

        source_code = "public class TestClass {}"

        # Should handle exception gracefully
        classes = java_extractor.extract_classes(mock_tree, source_code)

        assert classes == []


if __name__ == "__main__":
    pytest.main([__file__])
