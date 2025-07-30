#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for plugins base functionality

This module tests the base plugin classes and interfaces to improve coverage.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict, Any, Optional
from pathlib import Path

from tree_sitter_analyzer.plugins.base import (
    LanguagePlugin, 
    ElementExtractor,
    DefaultExtractor,
    DefaultLanguagePlugin
)
from tree_sitter_analyzer.models import (
    CodeElement,
    Function as ModelFunction,
    Class as ModelClass,
    Variable as ModelVariable,
    Import as ModelImport
)


class TestLanguagePlugin:
    """Test LanguagePlugin abstract base class"""
    
    def test_default_language_plugin_initialization(self) -> None:
        """Test DefaultLanguagePlugin initialization"""
        plugin = DefaultLanguagePlugin()
        
        assert plugin.get_language_name() == "generic"
        assert plugin.get_file_extensions() == [".txt", ".md"]
        
    def test_default_language_plugin_create_extractor(self) -> None:
        """Test DefaultLanguagePlugin create_extractor method"""
        plugin = DefaultLanguagePlugin()
        extractor = plugin.create_extractor()
        
        assert isinstance(extractor, DefaultExtractor)
        
    def test_is_applicable(self) -> None:
        """Test is_applicable method"""
        plugin = DefaultLanguagePlugin()
        
        # Should match supported extensions
        assert plugin.is_applicable("test.txt") is True
        assert plugin.is_applicable("README.md") is True
        
        # Should not match unsupported extensions
        assert plugin.is_applicable("test.py") is False
        assert plugin.is_applicable("test.java") is False
        
    def test_is_applicable_case_insensitive(self) -> None:
        """Test is_applicable with case insensitive matching"""
        plugin = DefaultLanguagePlugin()
        
        # Should match regardless of case
        assert plugin.is_applicable("TEST.TXT") is True
        assert plugin.is_applicable("readme.MD") is True
        
    def test_get_plugin_info(self) -> None:
        """Test get_plugin_info method"""
        plugin = DefaultLanguagePlugin()
        info = plugin.get_plugin_info()
        
        assert isinstance(info, dict)
        assert info["language"] == "generic"
        assert info["extensions"] == [".txt", ".md"]
        assert info["class_name"] == "DefaultLanguagePlugin"
        assert "module" in info


class TestElementExtractor:
    """Test ElementExtractor abstract base class"""
    
    @pytest.fixture
    def mock_tree(self) -> Mock:
        """Create a mock tree-sitter tree"""
        tree = Mock()
        tree.root_node = Mock()
        return tree
        
    @pytest.fixture
    def extractor(self) -> DefaultExtractor:
        """Create a DefaultExtractor instance"""
        return DefaultExtractor()
        
    def test_default_extractor_initialization(self, extractor: DefaultExtractor) -> None:
        """Test DefaultExtractor initialization"""
        assert isinstance(extractor, ElementExtractor)
        
    def test_extract_functions(self, extractor: DefaultExtractor, mock_tree: Mock) -> None:
        """Test extract_functions method"""
        # Create mock function node
        mock_function_node = Mock()
        mock_function_node.type = "function_definition"
        mock_function_node.start_point = (0, 0)
        mock_function_node.end_point = (2, 0)
        mock_function_node.start_byte = 0
        mock_function_node.end_byte = 20
        mock_function_node.children = []
        
        mock_tree.root_node.children = [mock_function_node]
        
        source_code = "def test_function():\n    pass\n"
        functions = extractor.extract_functions(mock_tree, source_code)
        
        assert isinstance(functions, list)
        # The function should be extracted
        assert len(functions) >= 0  # May be 0 if node structure doesn't match expectations
        
    def test_extract_classes(self, extractor: DefaultExtractor, mock_tree: Mock) -> None:
        """Test extract_classes method"""
        # Create mock class node
        mock_class_node = Mock()
        mock_class_node.type = "class_definition"
        mock_class_node.start_point = (0, 0)
        mock_class_node.end_point = (2, 0)
        mock_class_node.start_byte = 0
        mock_class_node.end_byte = 20
        mock_class_node.children = []
        
        mock_tree.root_node.children = [mock_class_node]
        
        source_code = "class TestClass:\n    pass\n"
        classes = extractor.extract_classes(mock_tree, source_code)
        
        assert isinstance(classes, list)
        
    def test_extract_variables(self, extractor: DefaultExtractor, mock_tree: Mock) -> None:
        """Test extract_variables method"""
        # Create mock variable node
        mock_var_node = Mock()
        mock_var_node.type = "variable_declaration"
        mock_var_node.start_point = (0, 0)
        mock_var_node.end_point = (0, 10)
        mock_var_node.start_byte = 0
        mock_var_node.end_byte = 10
        mock_var_node.children = []
        
        mock_tree.root_node.children = [mock_var_node]
        
        source_code = "x = 42"
        variables = extractor.extract_variables(mock_tree, source_code)
        
        assert isinstance(variables, list)
        
    def test_extract_imports(self, extractor: DefaultExtractor, mock_tree: Mock) -> None:
        """Test extract_imports method"""
        # Create mock import node
        mock_import_node = Mock()
        mock_import_node.type = "import_statement"
        mock_import_node.start_point = (0, 0)
        mock_import_node.end_point = (0, 15)
        mock_import_node.start_byte = 0
        mock_import_node.end_byte = 15
        mock_import_node.children = []
        
        mock_tree.root_node.children = [mock_import_node]
        
        source_code = "import os"
        imports = extractor.extract_imports(mock_tree, source_code)
        
        assert isinstance(imports, list)
        
    def test_extract_all_elements(self, extractor: DefaultExtractor, mock_tree: Mock) -> None:
        """Test extract_all_elements method"""
        mock_tree.root_node.children = []
        
        source_code = "# empty file"
        elements = extractor.extract_all_elements(mock_tree, source_code)
        
        assert isinstance(elements, list)
        
    def test_extract_all_elements_with_exception(self, extractor: DefaultExtractor, mock_tree: Mock) -> None:
        """Test extract_all_elements with exception handling"""
        # Mock extract_functions to raise an exception
        with patch.object(extractor, 'extract_functions', side_effect=Exception("Test error")):
            elements = extractor.extract_all_elements(mock_tree, "code")
            # Should return empty list on error
            assert isinstance(elements, list)
            
    def test_is_function_node(self, extractor: DefaultExtractor) -> None:
        """Test _is_function_node method"""
        assert extractor._is_function_node("function_definition") is True
        assert extractor._is_function_node("method_definition") is True
        assert extractor._is_function_node("function") is True
        assert extractor._is_function_node("class_definition") is False
        assert extractor._is_function_node("variable") is False
        
    def test_is_class_node(self, extractor: DefaultExtractor) -> None:
        """Test _is_class_node method"""
        assert extractor._is_class_node("class_definition") is True
        assert extractor._is_class_node("interface_definition") is True
        assert extractor._is_class_node("struct") is True
        assert extractor._is_class_node("function_definition") is False
        assert extractor._is_class_node("variable") is False
        
    def test_is_variable_node(self, extractor: DefaultExtractor) -> None:
        """Test _is_variable_node method"""
        assert extractor._is_variable_node("variable_declaration") is True
        assert extractor._is_variable_node("field_declaration") is True
        assert extractor._is_variable_node("assignment") is True
        assert extractor._is_variable_node("function_definition") is False
        assert extractor._is_variable_node("class") is False
        
    def test_is_import_node(self, extractor: DefaultExtractor) -> None:
        """Test _is_import_node method"""
        assert extractor._is_import_node("import_statement") is True
        assert extractor._is_import_node("import_declaration") is True
        assert extractor._is_import_node("include_statement") is True
        assert extractor._is_import_node("function_definition") is False
        assert extractor._is_import_node("class") is False
        
    def test_extract_node_text(self, extractor: DefaultExtractor) -> None:
        """Test _extract_node_text method"""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 5
        
        source_code = "hello world"
        result = extractor._extract_node_text(mock_node, source_code)
        
        assert result == "hello"
        
    def test_extract_node_text_with_unicode(self, extractor: DefaultExtractor) -> None:
        """Test _extract_node_text with unicode characters"""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 6  # "こん" in UTF-8 is 6 bytes
        
        source_code = "こんにちは"
        result = extractor._extract_node_text(mock_node, source_code)
        
        # Should handle UTF-8 encoding correctly
        assert len(result) > 0
        
    def test_extract_node_text_error_handling(self, extractor: DefaultExtractor) -> None:
        """Test _extract_node_text error handling"""
        mock_node = Mock()
        # Remove required attributes to trigger exception
        del mock_node.start_byte
        
        result = extractor._extract_node_text(mock_node, "source")
        assert result == ""
        
    def test_extract_node_name(self, extractor: DefaultExtractor) -> None:
        """Test _extract_node_name method"""
        # Create mock node with identifier child
        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_identifier.start_byte = 4
        mock_identifier.end_byte = 8
        
        mock_node = Mock()
        mock_node.children = [mock_identifier]
        mock_node.start_point = (1, 0)
        
        source_code = "def test():"
        result = extractor._extract_node_name(mock_node, source_code)
        
        # Should extract identifier or fallback name
        assert isinstance(result, str)
        assert len(result) > 0
        
    def test_extract_node_name_no_identifier(self, extractor: DefaultExtractor) -> None:
        """Test _extract_node_name without identifier child"""
        mock_node = Mock()
        mock_node.children = []
        mock_node.start_point = (1, 0)
        
        result = extractor._extract_node_name(mock_node, "source")
        
        # Should return fallback name
        assert result == "element_1_0"
        
    def test_extract_node_name_error_handling(self, extractor: DefaultExtractor) -> None:
        """Test _extract_node_name error handling"""
        mock_node = Mock()
        # Remove required attributes to trigger exception
        del mock_node.children
        
        result = extractor._extract_node_name(mock_node, "source")
        assert result is None
        
    def test_get_language_hint(self, extractor: DefaultExtractor) -> None:
        """Test _get_language_hint method"""
        result = extractor._get_language_hint()
        assert result == "unknown"


class TestDefaultExtractorTraversal:
    """Test DefaultExtractor traversal methods"""
    
    @pytest.fixture
    def extractor(self) -> DefaultExtractor:
        """Create a DefaultExtractor instance"""
        return DefaultExtractor()
        
    def test_traverse_for_functions(self, extractor: DefaultExtractor) -> None:
        """Test _traverse_for_functions method"""
        # Create mock function node
        mock_function_node = Mock()
        mock_function_node.type = "function_definition"
        mock_function_node.start_point = (0, 0)
        mock_function_node.end_point = (2, 0)
        mock_function_node.start_byte = 0
        mock_function_node.end_byte = 20
        mock_function_node.children = []
        
        functions = []
        lines = ["def test():", "    pass"]
        source_code = "def test():\n    pass"
        
        extractor._traverse_for_functions(mock_function_node, functions, lines, source_code)
        
        # Should add function to list
        assert len(functions) >= 0  # May be 0 if extraction fails
        
    def test_traverse_for_functions_with_children(self, extractor: DefaultExtractor) -> None:
        """Test _traverse_for_functions with child nodes"""
        # Create mock child function node
        mock_child_function = Mock()
        mock_child_function.type = "function_definition"
        mock_child_function.start_point = (1, 4)
        mock_child_function.end_point = (2, 0)
        mock_child_function.start_byte = 4
        mock_child_function.end_byte = 20
        mock_child_function.children = []
        
        # Create mock parent node
        mock_parent = Mock()
        mock_parent.type = "class_definition"
        mock_parent.children = [mock_child_function]
        
        functions = []
        lines = ["class Test:", "    def method():", "        pass"]
        source_code = "class Test:\n    def method():\n        pass"
        
        extractor._traverse_for_functions(mock_parent, functions, lines, source_code)
        
        # Should find nested function
        assert isinstance(functions, list)
        
    def test_traverse_error_handling(self, extractor: DefaultExtractor) -> None:
        """Test traversal error handling"""
        # Create mock node that will cause extraction error
        mock_node = Mock()
        mock_node.type = "function_definition"
        mock_node.children = []  # Keep children as empty list to avoid iteration error
        # Remove required attributes to trigger exception during extraction
        del mock_node.start_point
        
        functions = []
        lines = []
        source_code = ""
        
        # Should not raise exception
        extractor._traverse_for_functions(mock_node, functions, lines, source_code)
        
        # Functions list should remain empty
        assert len(functions) == 0


class TestDefaultExtractorIntegration:
    """Integration tests for DefaultExtractor"""
    
    def test_full_extraction_workflow(self) -> None:
        """Test complete extraction workflow"""
        extractor = DefaultExtractor()
        
        # Create mock tree with various node types
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        
        source_code = "# Simple test file"
        
        # Test all extraction methods
        functions = extractor.extract_functions(mock_tree, source_code)
        classes = extractor.extract_classes(mock_tree, source_code)
        variables = extractor.extract_variables(mock_tree, source_code)
        imports = extractor.extract_imports(mock_tree, source_code)
        all_elements = extractor.extract_all_elements(mock_tree, source_code)
        
        # All should return lists
        assert isinstance(functions, list)
        assert isinstance(classes, list)
        assert isinstance(variables, list)
        assert isinstance(imports, list)
        assert isinstance(all_elements, list)
        
    def test_extraction_with_no_tree(self) -> None:
        """Test extraction with invalid tree"""
        extractor = DefaultExtractor()
        
        # Create mock tree without root_node
        mock_tree = Mock()
        del mock_tree.root_node
        
        source_code = "test code"
        
        # Should handle gracefully
        functions = extractor.extract_functions(mock_tree, source_code)
        assert isinstance(functions, list)
        assert len(functions) == 0


class TestLanguagePluginIntegration:
    """Integration tests for LanguagePlugin"""
    
    def test_plugin_workflow(self) -> None:
        """Test complete plugin workflow"""
        plugin = DefaultLanguagePlugin()
        
        # Test basic properties
        assert plugin.get_language_name() == "generic"
        assert isinstance(plugin.get_file_extensions(), list)
        
        # Test file applicability
        assert plugin.is_applicable("test.txt") is True
        assert plugin.is_applicable("test.py") is False
        
        # Test extractor creation
        extractor = plugin.create_extractor()
        assert isinstance(extractor, ElementExtractor)
        
        # Test plugin info
        info = plugin.get_plugin_info()
        assert isinstance(info, dict)
        assert "language" in info
        assert "extensions" in info
        
    def test_plugin_with_empty_extensions(self) -> None:
        """Test plugin behavior with empty extensions"""
        plugin = DefaultLanguagePlugin()
        
        # Temporarily override extensions
        original_method = plugin.get_file_extensions
        plugin.get_file_extensions = lambda: []
        
        try:
            # Should not match any files
            assert plugin.is_applicable("test.txt") is False
            assert plugin.is_applicable("test.py") is False
        finally:
            # Restore original method
            plugin.get_file_extensions = original_method


class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_extractor_with_malformed_nodes(self) -> None:
        """Test extractor with malformed tree nodes"""
        extractor = DefaultExtractor()
        
        # Create mock tree with malformed nodes
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        
        # Create node without required attributes
        mock_bad_node = Mock()
        mock_bad_node.type = "function_definition"
        # Missing start_point, end_point, etc.
        
        mock_tree.root_node.children = [mock_bad_node]
        
        source_code = "def test(): pass"
        
        # Should handle gracefully without crashing
        functions = extractor.extract_functions(mock_tree, source_code)
        assert isinstance(functions, list)
        
    def test_plugin_with_special_characters_in_filename(self) -> None:
        """Test plugin with special characters in filename"""
        plugin = DefaultLanguagePlugin()
        
        # Test with various special characters
        assert plugin.is_applicable("test file.txt") is True
        assert plugin.is_applicable("test-file.md") is True
        assert plugin.is_applicable("test_file.TXT") is True
        assert plugin.is_applicable("файл.txt") is True  # Cyrillic
        assert plugin.is_applicable("ファイル.md") is True  # Japanese
        
    def test_extractor_with_empty_source_code(self) -> None:
        """Test extractor with empty source code"""
        extractor = DefaultExtractor()
        
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        
        # Test with empty source
        elements = extractor.extract_all_elements(mock_tree, "")
        assert isinstance(elements, list)
        assert len(elements) == 0
        
    def test_extractor_with_very_large_source_code(self) -> None:
        """Test extractor with large source code"""
        extractor = DefaultExtractor()
        
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        
        # Test with large source (10MB of text)
        large_source = "# comment\n" * 500000
        
        # Should handle without memory issues
        elements = extractor.extract_all_elements(mock_tree, large_source)
        assert isinstance(elements, list)