#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Plugin System

Tests for the plugin-based architecture including plugin registry,
language plugins, and element extractors.
"""

import sys

# Add project root to path
sys.path.insert(0, ".")

import os
import tempfile

from tree_sitter_analyzer.models import Class, Function, Import, Variable
from tree_sitter_analyzer.plugins import (
    ElementExtractor,
    LanguagePlugin,
    PluginRegistry,
    plugin_registry,
)
from tree_sitter_analyzer.plugins.java_plugin import JavaElementExtractor, JavaPlugin
from tree_sitter_analyzer.plugins.javascript_plugin import (
    JavaScriptElementExtractor,
    JavaScriptPlugin,
)


def test_plugin_registry_instance():
    """Test plugin registry singleton instance"""
    assert plugin_registry is not None
    assert isinstance(plugin_registry, PluginRegistry)


def test_register_plugin():
    """Test plugin registration"""
    registry = PluginRegistry()
    java_plugin = JavaPlugin()

    registry.register_plugin(java_plugin)

    assert "java" in registry.list_supported_languages()
    assert ".java" in registry.list_supported_extensions()


def test_get_plugin():
    """Test getting plugin by language"""
    registry = PluginRegistry()
    java_plugin = JavaPlugin()
    registry.register_plugin(java_plugin)

    retrieved_plugin = registry.get_plugin("java")
    assert retrieved_plugin is java_plugin


def test_get_plugin_by_extension():
    """Test getting plugin by file extension"""
    registry = PluginRegistry()
    java_plugin = JavaPlugin()
    registry.register_plugin(java_plugin)

    retrieved_plugin = registry.get_plugin_by_extension(".java")
    assert retrieved_plugin is java_plugin


def test_get_nonexistent_plugin():
    """Test getting nonexistent plugin returns None"""
    registry = PluginRegistry()

    plugin = registry.get_plugin("nonexistent")
    assert plugin is None

    plugin = registry.get_plugin_by_extension(".unknown")
    assert plugin is None


def test_java_plugin_properties():
    """Test Java plugin basic properties"""
    plugin = JavaPlugin()

    assert plugin.language_name == "java"
    assert ".java" in plugin.file_extensions
    assert ".jsp" in plugin.file_extensions
    assert ".jspx" in plugin.file_extensions


def test_java_plugin_extractor():
    """Test Java plugin element extractor"""
    plugin = JavaPlugin()
    extractor = plugin.get_extractor()

    assert isinstance(extractor, JavaElementExtractor)


def test_java_plugin_tree_sitter_language():
    """Test Java plugin tree-sitter language loading"""
    plugin = JavaPlugin()
    language = plugin.get_tree_sitter_language()

    # Language may be None if tree-sitter-java is not available
    assert language is None or hasattr(language, "query")


def test_javascript_plugin_properties():
    """Test JavaScript plugin basic properties"""
    plugin = JavaScriptPlugin()

    assert plugin.language_name == "javascript"
    assert ".js" in plugin.file_extensions
    assert ".mjs" in plugin.file_extensions
    assert ".jsx" in plugin.file_extensions


def test_javascript_plugin_extractor():
    """Test JavaScript plugin element extractor"""
    plugin = JavaScriptPlugin()
    extractor = plugin.get_extractor()

    assert isinstance(extractor, JavaScriptElementExtractor)


def test_java_extractor_initialization():
    """Test Java element extractor initialization"""
    extractor = JavaElementExtractor()

    assert extractor.current_package == ""
    assert extractor.current_file == ""
    assert extractor.source_code == ""
    assert extractor.imports == []


def test_extract_functions_with_mock_tree(mocker):
    """Test function extraction with mock tree"""
    extractor = JavaElementExtractor()

    # Mock tree and source code
    mock_tree = mocker.MagicMock()
    mock_tree.language = None  # Simulate no language available
    source_code = """
    public class TestClass {
        public void testMethod() {
            System.out.println("test");
        }
    }
    """

    functions = extractor.extract_functions(mock_tree, source_code)

    # Should return empty list when no language is available
    assert isinstance(functions, list)


def test_extract_classes_with_mock_tree(mocker):
    """Test class extraction with mock tree"""
    extractor = JavaElementExtractor()

    # Mock tree
    mock_tree = mocker.MagicMock()
    mock_tree.language = None
    source_code = "public class TestClass {}"

    classes = extractor.extract_classes(mock_tree, source_code)

    assert isinstance(classes, list)


def test_extract_variables_with_mock_tree(mocker):
    """Test variable extraction with mock tree"""
    extractor = JavaElementExtractor()

    mock_tree = mocker.MagicMock()
    mock_tree.language = None
    source_code = "private String testField;"

    variables = extractor.extract_variables(mock_tree, source_code)

    assert isinstance(variables, list)


def test_extract_imports_with_mock_tree(mocker):
    """Test import extraction with mock tree"""
    extractor = JavaElementExtractor()

    mock_tree = mocker.MagicMock()
    mock_tree.language = None
    source_code = "import java.util.List;"

    imports = extractor.extract_imports(mock_tree, source_code)

    assert isinstance(imports, list)


def test_javascript_extractor_methods_exist():
    """Test JavaScript element extractor has required methods"""
    extractor = JavaScriptElementExtractor()

    assert hasattr(extractor, "extract_functions")
    assert hasattr(extractor, "extract_classes")
    assert hasattr(extractor, "extract_variables")
    assert hasattr(extractor, "extract_imports")


def test_javascript_extract_methods_return_lists(mocker):
    """Test all extract methods return lists"""
    extractor = JavaScriptElementExtractor()

    mock_tree = mocker.MagicMock()
    mock_tree.language = None
    source_code = "function test() { return 'hello'; }"

    functions = extractor.extract_functions(mock_tree, source_code)
    classes = extractor.extract_classes(mock_tree, source_code)
    variables = extractor.extract_variables(mock_tree, source_code)
    imports = extractor.extract_imports(mock_tree, source_code)

    assert isinstance(functions, list)
    assert isinstance(classes, list)
    assert isinstance(variables, list)
    assert isinstance(imports, list)


def test_multiple_plugins_registration():
    """Test registering multiple plugins"""
    registry = PluginRegistry()

    java_plugin = JavaPlugin()
    js_plugin = JavaScriptPlugin()

    registry.register_plugin(java_plugin)
    registry.register_plugin(js_plugin)

    languages = registry.list_supported_languages()
    extensions = registry.list_supported_extensions()

    assert "java" in languages
    assert "javascript" in languages
    assert ".java" in extensions
    assert ".js" in extensions


def test_plugin_extension_mapping():
    """Test file extension to plugin mapping"""
    registry = PluginRegistry()

    java_plugin = JavaPlugin()
    js_plugin = JavaScriptPlugin()

    registry.register_plugin(java_plugin)
    registry.register_plugin(js_plugin)

    # Test Java extensions
    assert registry.get_plugin_by_extension(".java") == java_plugin
    assert registry.get_plugin_by_extension(".jsp") == java_plugin

    # Test JavaScript extensions
    assert registry.get_plugin_by_extension(".js") == js_plugin
    assert registry.get_plugin_by_extension(".jsx") == js_plugin


def test_global_plugin_registry_usage():
    """Test using the global plugin registry"""
    from tree_sitter_analyzer.plugins import plugin_registry

    # Clear any existing plugins for clean test
    original_plugins = plugin_registry._plugins.copy()
    original_extensions = plugin_registry._extension_map.copy()

    try:
        plugin_registry._plugins.clear()
        plugin_registry._extension_map.clear()

        java_plugin = JavaPlugin()
        plugin_registry.register_plugin(java_plugin)

        assert "java" in plugin_registry.list_supported_languages()
        retrieved = plugin_registry.get_plugin("java")
        assert retrieved == java_plugin

    finally:
        # Restore original state
        plugin_registry._plugins = original_plugins
        plugin_registry._extension_map = original_extensions


def test_empty_registry():
    """Test empty plugin registry"""
    registry = PluginRegistry()

    assert registry.list_supported_languages() == []
    assert registry.list_supported_extensions() == []
    assert registry.get_plugin("any") is None
    assert registry.get_plugin_by_extension(".any") is None


def test_plugin_overwrite():
    """Test overwriting existing plugin"""
    registry = PluginRegistry()

    plugin1 = JavaPlugin()
    plugin2 = JavaPlugin()

    registry.register_plugin(plugin1)
    registry.register_plugin(plugin2)

    # Should use the last registered plugin
    retrieved = registry.get_plugin("java")
    assert retrieved == plugin2


def test_case_sensitivity():
    """Test case sensitivity in plugin lookups"""
    registry = PluginRegistry()
    java_plugin = JavaPlugin()
    registry.register_plugin(java_plugin)

    # Language lookup should be case sensitive
    assert registry.get_plugin("Java") is None
    assert registry.get_plugin("JAVA") is None
    assert registry.get_plugin("java") == java_plugin

    # Extension lookup should be case sensitive
    assert registry.get_plugin_by_extension(".JAVA") is None
    assert registry.get_plugin_by_extension(".java") == java_plugin
