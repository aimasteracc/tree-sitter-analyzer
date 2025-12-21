#!/usr/bin/env python3
"""
Tests for Plugin System

Tests for the plugin-based architecture including plugin registry,
language plugins, and element extractors.
"""

import sys

# Add project root to path
sys.path.insert(0, ".")


from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor, JavaPlugin
from tree_sitter_analyzer.languages.javascript_plugin import (
    JavaScriptElementExtractor,
    JavaScriptPlugin,
)
from tree_sitter_analyzer.plugins.manager import PluginManager


def test_plugin_manager_instance():
    """Test plugin manager instance creation"""
    manager = PluginManager()
    assert manager is not None


def test_register_plugin():
    """Test plugin registration"""
    manager = PluginManager()
    java_plugin = JavaPlugin()

    manager.register_plugin(java_plugin)

    assert "java" in manager.get_supported_languages()
    assert manager.get_plugin("java") is java_plugin


def test_get_plugin():
    """Test getting plugin by language"""
    manager = PluginManager()
    java_plugin = JavaPlugin()
    manager.register_plugin(java_plugin)

    retrieved_plugin = manager.get_plugin("java")
    assert retrieved_plugin is java_plugin


def test_get_nonexistent_plugin():
    """Test getting nonexistent plugin returns None"""
    manager = PluginManager()

    plugin = manager.get_plugin("nonexistent")
    assert plugin is None


def test_java_plugin_properties():
    """Test Java plugin basic properties"""
    plugin = JavaPlugin()

    assert plugin.get_language_name() == "java"
    extensions = plugin.get_file_extensions()
    assert ".java" in extensions
    assert ".jsp" in extensions
    assert ".jspx" in extensions


def test_java_plugin_extractor():
    """Test Java plugin element extractor"""
    plugin = JavaPlugin()
    extractor = plugin.create_extractor()

    assert isinstance(extractor, JavaElementExtractor)


def test_java_plugin_tree_sitter_language():
    """Test Java plugin tree-sitter language loading"""
    plugin = JavaPlugin()
    language = plugin.get_tree_sitter_language()

    # Language may be None if tree-sitter-java is not available
    # Tree-sitter Language objects can be PyCapsule or tree_sitter.Language objects
    assert language is None or str(type(language)) in [
        "<class 'PyCapsule'>",
        "<class 'tree_sitter.Language'>",
    ]


def test_javascript_plugin_properties():
    """Test JavaScript plugin basic properties"""
    plugin = JavaScriptPlugin()

    assert plugin.get_language_name() == "javascript"
    extensions = plugin.get_file_extensions()
    assert ".js" in extensions
    assert ".mjs" in extensions
    assert ".jsx" in extensions


def test_javascript_plugin_extractor():
    """Test JavaScript plugin element extractor"""
    plugin = JavaScriptPlugin()
    extractor = plugin.create_extractor()

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


# Legacy PluginRegistry tests removed - now using PluginManager
# See tests/test_plugins/test_manager.py for comprehensive PluginManager tests
