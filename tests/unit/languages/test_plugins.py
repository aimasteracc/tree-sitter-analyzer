#!/usr/bin/env python3
"""
Tests for Plugin System

Tests for the plugin-based architecture including plugin registry,
language plugins, and element extractors.
"""

import sys

import tree_sitter

# Add project root to path
sys.path.insert(0, ".")


from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor, JavaPlugin
from tree_sitter_analyzer.languages.javascript_plugin import (
    JavaScriptElementExtractor,
    JavaScriptPlugin,
)
from tree_sitter_analyzer.plugins.manager import PluginManager


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


def test_extract_functions_with_real_tree():
    """PR #1350：真实游标必须终止并提取方法，不能用永真 MagicMock 模拟游标。"""
    extractor = JavaElementExtractor()

    source_code = """
    public class TestClass {
        public void testMethod() {
            System.out.println("test");
        }
    }
    """

    tree = tree_sitter.Parser(JavaPlugin().get_tree_sitter_language()).parse(
        source_code.encode("utf-8")
    )
    assert tree.root_node.has_error is False
    functions = extractor.extract_functions(tree, source_code)
    assert [(f.name, f.return_type, f.is_public) for f in functions] == [
        ("testMethod", "void", True)
    ]


def test_extract_classes_with_real_tree():
    """PR #1350：类提取使用真实 grammar，校验名称和类型而非容器类型。"""
    extractor = JavaElementExtractor()

    source_code = "public class TestClass {}"
    tree = tree_sitter.Parser(JavaPlugin().get_tree_sitter_language()).parse(
        source_code.encode("utf-8")
    )
    assert tree.root_node.has_error is False
    classes = extractor.extract_classes(tree, source_code)
    assert [(c.name, c.class_type, c.visibility) for c in classes] == [
        ("TestClass", "class", "public")
    ]


def test_extract_variables_with_real_tree():
    """PR #1350：字段放在合法类体内，以真实节点验证类型与可见性。"""
    extractor = JavaElementExtractor()

    source_code = "class TestClass { private String testField; }"
    tree = tree_sitter.Parser(JavaPlugin().get_tree_sitter_language()).parse(
        source_code.encode("utf-8")
    )
    assert tree.root_node.has_error is False
    variables = extractor.extract_variables(tree, source_code)
    assert [(v.name, v.variable_type, v.visibility) for v in variables] == [
        ("testField", "String", "private")
    ]


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
