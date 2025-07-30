#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Plugin System Coverage Enhancement

Additional tests to improve coverage for plugins/__init__.py
"""

import sys
import pytest
import pytest_asyncio

# Add project root to path
sys.path.insert(0, ".")

from tree_sitter_analyzer.plugins import (
    DefaultExtractor,
    DefaultLanguagePlugin,
    ElementExtractor,
    LanguagePlugin,
    PluginRegistry,
    plugin_registry,
)


@pytest.fixture
def default_extractor():
    """Fixture for DefaultExtractor"""
    return DefaultExtractor()


@pytest.fixture
def default_language_plugin():
    """Fixture for DefaultLanguagePlugin"""
    return DefaultLanguagePlugin()


@pytest.fixture
def plugin_registry_instance():
    """Fixture for PluginRegistry"""
    return PluginRegistry()


class TestDefaultExtractor:
    """Test DefaultExtractor functionality"""

    def test_extract_functions_with_valid_tree(self, mocker, default_extractor):
        """Test function extraction with valid tree"""
        mock_tree = mocker.MagicMock()
        mock_root = mocker.MagicMock()
        mock_root.type = "function_declaration"
        mock_root.start_point = (0, 0)
        mock_root.end_point = (5, 10)
        mock_root.children = []

        mock_tree.root_node = mock_root
        source_code = "function test() { return 'hello'; }"

        functions = default_extractor.extract_functions(mock_tree, source_code)

        assert isinstance(functions, list)

    def test_extract_functions_with_exception(self, mocker, default_extractor):
        """Test function extraction with exception"""
        mock_tree = mocker.MagicMock()
        mock_tree.root_node = None  # This will cause an exception

        source_code = "function test() { return 'hello'; }"

        functions = default_extractor.extract_functions(mock_tree, source_code)

        assert functions == []

    def test_extract_classes_with_valid_tree(self, mocker, default_extractor):
        """Test class extraction with valid tree"""
        mock_tree = mocker.MagicMock()
        mock_root = mocker.MagicMock()
        mock_root.type = "class_declaration"
        mock_root.start_point = (0, 0)
        mock_root.end_point = (5, 10)
        mock_root.children = []

        mock_tree.root_node = mock_root
        source_code = "class TestClass {}"

        classes = default_extractor.extract_classes(mock_tree, source_code)

        assert isinstance(classes, list)

    def test_extract_classes_with_exception(self, mocker, default_extractor):
        """Test class extraction with exception"""
        mock_tree = mocker.MagicMock()
        mock_tree.root_node = None

        source_code = "class TestClass {}"

        classes = default_extractor.extract_classes(mock_tree, source_code)

        assert classes == []

    def test_extract_variables_with_valid_tree(self, mocker, default_extractor):
        """Test variable extraction with valid tree"""
        mock_tree = mocker.MagicMock()
        mock_root = mocker.MagicMock()
        mock_root.type = "variable_declaration"
        mock_root.start_point = (0, 0)
        mock_root.end_point = (1, 10)
        mock_root.children = []

        mock_tree.root_node = mock_root
        source_code = "var test = 'hello';"

        variables = default_extractor.extract_variables(mock_tree, source_code)

        assert isinstance(variables, list)

    def test_extract_variables_with_exception(self, mocker, default_extractor):
        """Test variable extraction with exception"""
        mock_tree = mocker.MagicMock()
        mock_tree.root_node = None

        source_code = "var test = 'hello';"

        variables = default_extractor.extract_variables(mock_tree, source_code)

        assert variables == []

    def test_extract_imports_with_valid_tree(self, mocker, default_extractor):
        """Test import extraction with valid tree"""
        mock_tree = mocker.MagicMock()
        mock_root = mocker.MagicMock()
        mock_root.type = "import_statement"
        mock_root.start_point = (0, 0)
        mock_root.end_point = (1, 20)
        mock_root.children = []

        mock_tree.root_node = mock_root
        source_code = "import { test } from 'module';"

        imports = default_extractor.extract_imports(mock_tree, source_code)

        assert isinstance(imports, list)

    def test_extract_imports_with_exception(self, mocker, default_extractor):
        """Test import extraction with exception"""
        mock_tree = mocker.MagicMock()
        mock_tree.root_node = None

        source_code = "import { test } from 'module';"

        imports = default_extractor.extract_imports(mock_tree, source_code)

        assert imports == []

    def test_traverse_for_functions_with_nested_nodes(self, mocker, default_extractor):
        """Test function traversal with nested nodes"""
        mock_node = mocker.MagicMock()
        mock_node.type = "function_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 10)

        mock_child = mocker.MagicMock()
        mock_child.type = "identifier"
        mock_child.start_point = (1, 5)
        mock_child.start_point = (1, 9)

        mock_node.children = [mock_child]

        functions = []
        lines = ["function test() {", "  return 'hello';", "}"]

        default_extractor._traverse_for_functions(mock_node, functions, lines)

        assert len(functions) == 1

    def test_traverse_for_classes_with_nested_nodes(self, mocker, default_extractor):
        """Test class traversal with nested nodes"""
        mock_node = mocker.MagicMock()
        mock_node.type = "class_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 10)

        mock_child = mocker.MagicMock()
        mock_child.type = "identifier"
        mock_child.start_point = (1, 5)

        mock_node.children = [mock_child]

        classes = []
        lines = ["class TestClass {", "  constructor() {}", "}"]

        default_extractor._traverse_for_classes(mock_node, classes, lines)

        assert len(classes) == 1

    def test_traverse_for_variables_with_nested_nodes(self, mocker, default_extractor):
        """Test variable traversal with nested nodes"""
        mock_node = mocker.MagicMock()
        mock_node.type = "variable_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 10)

        mock_child = mocker.MagicMock()
        mock_child.type = "identifier"
        mock_child.start_point = (0, 4)

        mock_node.children = [mock_child]

        variables = []
        lines = ["var test = 'hello';"]

        default_extractor._traverse_for_variables(mock_node, variables, lines)

        assert len(variables) == 1

    def test_traverse_for_imports_with_nested_nodes(self, mocker, default_extractor):
        """Test import traversal with nested nodes"""
        mock_node = mocker.MagicMock()
        mock_node.type = "import_statement"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 20)

        mock_child = mocker.MagicMock()
        mock_child.type = "identifier"
        mock_child.start_point = (0, 8)

        mock_node.children = [mock_child]

        imports = []
        lines = ["import { test } from 'module';"]

        default_extractor._traverse_for_imports(mock_node, imports, lines)

        assert len(imports) == 1

    def test_extract_node_name_with_identifier(self, mocker, default_extractor):
        """Test node name extraction with identifier"""
        mock_node = mocker.MagicMock()
        mock_child = mocker.MagicMock()
        mock_child.type = "identifier"
        mock_child.start_point = (1, 5)

        mock_node.children = [mock_child]

        name = default_extractor._extract_node_name(mock_node)

        assert name is not None
        assert name.startswith("element_")

    def test_extract_node_name_without_identifier(self, mocker, default_extractor):
        """Test node name extraction without identifier"""
        mock_node = mocker.MagicMock()
        mock_node.children = []

        name = default_extractor._extract_node_name(mock_node)

        assert name is None

    def test_extract_node_name_with_exception(self, mocker, default_extractor):
        """Test node name extraction with exception"""
        mock_node = mocker.MagicMock()
        mock_node.children = None  # This will cause an exception

        name = default_extractor._extract_node_name(mock_node)

        assert name is None


class TestDefaultLanguagePlugin:
    """Test DefaultLanguagePlugin functionality"""

    def test_get_language_name(self, default_language_plugin):
        """Test language name"""
        assert default_language_plugin.get_language_name() == "generic"

    def test_get_file_extensions(self, default_language_plugin):
        """Test file extensions"""
        extensions = default_language_plugin.get_file_extensions()
        assert ".txt" in extensions
        assert ".md" in extensions

    def test_create_extractor(self, default_language_plugin):
        """Test extractor creation"""
        extractor = default_language_plugin.create_extractor()
        assert isinstance(extractor, DefaultExtractor)

    def test_is_applicable(self, default_language_plugin):
        """Test file applicability"""
        assert default_language_plugin.is_applicable("test.txt") is True
        assert default_language_plugin.is_applicable("README.md") is True
        assert default_language_plugin.is_applicable("test.py") is False


class TestPluginRegistryAdvanced:
    """Test advanced PluginRegistry functionality"""

    def test_register_plugin_with_exception(self, mocker, plugin_registry_instance):
        """Test plugin registration with exception"""
        mock_plugin = mocker.MagicMock()
        mock_plugin.get_language_name.side_effect = Exception("Test error")

        # Should not raise exception
        plugin_registry_instance.register_plugin(mock_plugin)

    def test_get_plugin_for_file_with_applicable_plugin(self, mocker, plugin_registry_instance):
        """Test getting plugin for file with applicable plugin"""
        mock_plugin = mocker.MagicMock()
        mock_plugin.get_language_name.return_value = "test"
        mock_plugin.get_file_extensions.return_value = [".test"]
        mock_plugin.is_applicable.return_value = True

        plugin_registry_instance.register_plugin(mock_plugin)

        result = plugin_registry_instance.get_plugin_for_file("test.test")
        assert result == mock_plugin

    def test_get_plugin_for_file_with_no_applicable_plugin(self, plugin_registry_instance):
        """Test getting plugin for file with no applicable plugin"""
        result = plugin_registry_instance.get_plugin_for_file("unknown.xyz")
        assert isinstance(result, DefaultLanguagePlugin)

    def test_list_supported_languages_empty(self, plugin_registry_instance):
        """Test listing supported languages when empty"""
        languages = plugin_registry_instance.list_supported_languages()
        assert languages == []

    def test_list_supported_extensions_empty(self, plugin_registry_instance):
        """Test listing supported extensions when empty"""
        extensions = plugin_registry_instance.list_supported_extensions()
        assert extensions == []
