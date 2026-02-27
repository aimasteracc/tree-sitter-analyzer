#!/usr/bin/env python3
"""
Tests for Plugin System

Tests for the plugin-based architecture including plugin registry,
language plugins, and element extractors.
"""

import sys
from unittest.mock import Mock, patch

# Add project root to path
sys.path.insert(0, ".")


from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor, JavaPlugin
from tree_sitter_analyzer.languages.javascript_plugin import (
    JavaScriptElementExtractor,
    JavaScriptPlugin,
)
from tree_sitter_analyzer.models import Class, Function
from tree_sitter_analyzer.plugins.base import (
    DefaultExtractor,
    DefaultLanguagePlugin,
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


# ---------------------------------------------------------------------------
# Merged from test_plugins_base.py, test_plugins_coverage.py,
# test_plugins_fixed.py -- unique tests covering different code paths
# ---------------------------------------------------------------------------


def test_default_language_plugin_is_applicable():
    """Test DefaultLanguagePlugin.is_applicable for supported and unsupported extensions"""
    plugin = DefaultLanguagePlugin()

    assert plugin.is_applicable("test.txt") is True
    assert plugin.is_applicable("README.md") is True
    assert plugin.is_applicable("test.py") is False
    assert plugin.is_applicable("test.java") is False
    # Case-insensitive matching
    assert plugin.is_applicable("TEST.TXT") is True
    assert plugin.is_applicable("readme.MD") is True


def test_default_language_plugin_info_and_types():
    """Test get_plugin_info, get_supported_element_types, get_queries, and related methods"""
    plugin = DefaultLanguagePlugin()

    info = plugin.get_plugin_info()
    assert isinstance(info, dict)
    assert info["language"] == "generic"
    assert info["extensions"] == [".txt", ".md"]
    assert info["class_name"] == "DefaultLanguagePlugin"

    types = plugin.get_supported_element_types()
    assert "function" in types
    assert "class" in types
    assert "variable" in types
    assert "import" in types

    assert plugin.get_queries() == {}
    assert plugin.execute_query_strategy("methods", "generic") is None
    assert plugin.get_formatter_map() == {}
    assert plugin.get_element_categories() == {}


def test_default_extractor_node_type_checks():
    """Test DefaultExtractor _is_function_node, _is_class_node, _is_variable_node, _is_import_node"""
    extractor = DefaultExtractor()

    # Function node types
    assert extractor._is_function_node("function_definition") is True
    assert extractor._is_function_node("method_definition") is True
    assert extractor._is_function_node("function") is True
    assert extractor._is_function_node("class_definition") is False

    # Class node types
    assert extractor._is_class_node("class_definition") is True
    assert extractor._is_class_node("interface_definition") is True
    assert extractor._is_class_node("struct") is True
    assert extractor._is_class_node("function_definition") is False

    # Variable node types
    assert extractor._is_variable_node("variable_declaration") is True
    assert extractor._is_variable_node("field_declaration") is True
    assert extractor._is_variable_node("assignment") is True
    assert extractor._is_variable_node("function_definition") is False

    # Import node types
    assert extractor._is_import_node("import_statement") is True
    assert extractor._is_import_node("import_declaration") is True
    assert extractor._is_import_node("include_statement") is True
    assert extractor._is_import_node("function_definition") is False


def test_default_extractor_extract_node_text():
    """Test DefaultExtractor._extract_node_text including error handling"""
    extractor = DefaultExtractor()

    mock_node = Mock()
    mock_node.start_byte = 0
    mock_node.end_byte = 5
    assert extractor._extract_node_text(mock_node, "hello world") == "hello"

    # Error handling: missing attributes
    bad_node = Mock()
    del bad_node.start_byte
    assert extractor._extract_node_text(bad_node, "source") == ""


def test_default_extractor_extract_node_name():
    """Test DefaultExtractor._extract_node_name with and without identifier children"""
    extractor = DefaultExtractor()

    # With identifier child
    mock_identifier = Mock()
    mock_identifier.type = "identifier"
    mock_identifier.start_byte = 4
    mock_identifier.end_byte = 8
    mock_node = Mock()
    mock_node.children = [mock_identifier]
    mock_node.start_point = (1, 0)
    result = extractor._extract_node_name(mock_node, "def test():")
    assert isinstance(result, str)
    assert len(result) > 0

    # Without identifier child -- fallback name
    mock_node_empty = Mock()
    mock_node_empty.children = []
    mock_node_empty.start_point = (1, 0)
    assert extractor._extract_node_name(mock_node_empty, "source") == "element_1_0"

    # Error handling
    bad_node = Mock()
    del bad_node.children
    assert extractor._extract_node_name(bad_node, "source") is None


def test_default_extractor_get_language_hint():
    """Test DefaultExtractor._get_language_hint returns 'unknown'"""
    extractor = DefaultExtractor()
    assert extractor._get_language_hint() == "unknown"


def test_default_extractor_extract_all_elements():
    """Test DefaultExtractor.extract_all_elements with empty tree"""
    extractor = DefaultExtractor()
    mock_tree = Mock()
    mock_tree.root_node = Mock()
    mock_tree.root_node.children = []

    elements = extractor.extract_all_elements(mock_tree, "# empty file")
    assert isinstance(elements, list)


def test_default_extractor_extract_all_elements_with_exception():
    """Test DefaultExtractor.extract_all_elements gracefully handles exceptions"""
    extractor = DefaultExtractor()
    mock_tree = Mock()

    with patch.object(
        extractor, "extract_functions", side_effect=Exception("Test error")
    ):
        elements = extractor.extract_all_elements(mock_tree, "code")
        assert isinstance(elements, list)


def test_default_extractor_extraction_with_none_root():
    """Test extraction returns empty list when tree root_node is None"""
    extractor = DefaultExtractor()
    mock_tree = Mock()
    mock_tree.root_node = None

    assert extractor.extract_functions(mock_tree, "source") == []


def test_default_extractor_extraction_with_no_root_attr():
    """Test extraction returns empty list when tree has no root_node attribute"""
    extractor = DefaultExtractor()
    mock_tree = Mock()
    del mock_tree.root_node

    functions = extractor.extract_functions(mock_tree, "test code")
    assert isinstance(functions, list)
    assert len(functions) == 0


def test_register_plugin_with_exception(mocker):
    """Test plugin registration handles exceptions in get_language_name gracefully"""
    manager = PluginManager()
    mock_plugin = mocker.MagicMock()
    mock_plugin.get_language_name.side_effect = Exception("Test error")

    # Should not raise exception
    manager.register_plugin(mock_plugin)


def test_java_extract_method_optimized_with_valid_node(mocker):
    """Test Java _extract_method_optimized with a valid method_declaration node"""
    extractor = JavaElementExtractor()

    mock_node = mocker.MagicMock()
    mock_node.type = "method_declaration"
    mock_node.start_point = (0, 0)
    mock_node.end_point = (5, 10)
    mock_node.start_byte = 0
    mock_node.end_byte = 50

    mock_identifier = mocker.MagicMock()
    mock_identifier.type = "identifier"
    mock_return_type = mocker.MagicMock()
    mock_return_type.type = "void_type"
    mock_modifiers = mocker.MagicMock()
    mock_modifiers.type = "modifiers"
    mock_modifiers.children = []
    mock_params = mocker.MagicMock()
    mock_params.type = "formal_parameters"
    mock_params.children = []

    mock_node.children = [mock_modifiers, mock_return_type, mock_identifier, mock_params]

    extractor.source_code = "public void testMethod() {}"
    extractor.content_lines = ["public void testMethod() {}"]

    def mock_get_text(node):
        if node == mock_identifier:
            return "testMethod"
        elif node == mock_return_type:
            return "void"
        elif node == mock_modifiers:
            return "public"
        elif node == mock_params:
            return "()"
        return ""

    extractor._get_node_text_optimized = mock_get_text

    function = extractor._extract_method_optimized(mock_node)
    assert function is not None
    assert isinstance(function, Function)
    assert function.name == "testMethod"


def test_java_parse_method_signature_parameters(mocker):
    """Test Java _parse_method_signature_optimized extracts parameters"""
    extractor = JavaElementExtractor()

    mock_param_node = mocker.MagicMock()
    mock_param_node.type = "formal_parameter"
    mock_params_node = mocker.MagicMock()
    mock_params_node.type = "formal_parameters"
    mock_params_node.children = [mock_param_node]
    mock_identifier = mocker.MagicMock()
    mock_identifier.type = "identifier"

    mock_node = mocker.MagicMock()
    mock_node.type = "method_declaration"
    mock_node.children = [mock_identifier, mock_params_node]

    def mock_get_text(node):
        if node == mock_identifier:
            return "testMethod"
        elif node == mock_param_node:
            return "String param"
        elif node == mock_params_node:
            return "(String param)"
        return ""

    extractor._get_node_text_optimized = mock_get_text

    result = extractor._parse_method_signature_optimized(mock_node)
    assert result is not None
    method_name, return_type, parameters, modifiers, throws = result
    assert method_name == "testMethod"
    assert len(parameters) == 1
    assert parameters[0] == "String param"


def test_java_extract_class_with_superclass(mocker):
    """Test Java _extract_class_optimized with superclass inheritance"""
    extractor = JavaElementExtractor()

    mock_type_id = mocker.MagicMock()
    mock_type_id.type = "type_identifier"
    mock_superclass = mocker.MagicMock()
    mock_superclass.type = "superclass"
    mock_superclass.children = [mock_type_id]
    mock_identifier = mocker.MagicMock()
    mock_identifier.type = "identifier"

    mock_node = mocker.MagicMock()
    mock_node.type = "class_declaration"
    mock_node.start_point = (0, 0)
    mock_node.end_point = (2, 1)
    mock_node.children = [mock_identifier, mock_superclass]

    extractor.source_code = "class Test extends BaseClass {}"
    extractor.content_lines = ["class Test extends BaseClass {}"]
    extractor._extract_modifiers_optimized = mocker.MagicMock(return_value=[])
    extractor._determine_visibility = mocker.MagicMock(return_value="public")
    extractor._find_annotations_for_line_cached = mocker.MagicMock(return_value=[])
    extractor._is_nested_class = mocker.MagicMock(return_value=False)
    extractor._find_parent_class = mocker.MagicMock(return_value=None)

    def mock_get_text(node):
        if node == mock_identifier:
            return "Test"
        elif node == mock_type_id:
            return "BaseClass"
        elif node == mock_superclass:
            return "extends BaseClass"
        return ""

    extractor._get_node_text_optimized = mock_get_text

    class_obj = extractor._extract_class_optimized(mock_node)
    assert class_obj is not None
    assert isinstance(class_obj, Class)
    assert class_obj.name == "Test"
    assert class_obj.superclass == "BaseClass"


def test_java_extract_class_with_interfaces(mocker):
    """Test Java _extract_class_optimized with interface implementation"""
    extractor = JavaElementExtractor()

    mock_type_id1 = mocker.MagicMock()
    mock_type_id1.type = "type_identifier"
    mock_type_id2 = mocker.MagicMock()
    mock_type_id2.type = "type_identifier"
    mock_interfaces = mocker.MagicMock()
    mock_interfaces.type = "super_interfaces"
    mock_interfaces.children = [mock_type_id1, mock_type_id2]
    mock_identifier = mocker.MagicMock()
    mock_identifier.type = "identifier"

    mock_node = mocker.MagicMock()
    mock_node.type = "class_declaration"
    mock_node.start_point = (0, 0)
    mock_node.end_point = (2, 1)
    mock_node.children = [mock_identifier, mock_interfaces]

    extractor.source_code = "class Test implements Interface1, Interface2 {}"
    extractor.content_lines = ["class Test implements Interface1, Interface2 {}"]
    extractor._extract_modifiers_optimized = mocker.MagicMock(return_value=[])
    extractor._determine_visibility = mocker.MagicMock(return_value="public")
    extractor._find_annotations_for_line_cached = mocker.MagicMock(return_value=[])
    extractor._is_nested_class = mocker.MagicMock(return_value=False)
    extractor._find_parent_class = mocker.MagicMock(return_value=None)

    def mock_get_text(node):
        if node == mock_identifier:
            return "Test"
        elif node == mock_type_id1:
            return "Interface1"
        elif node == mock_type_id2:
            return "Interface2"
        elif node == mock_interfaces:
            return "implements Interface1, Interface2"
        return ""

    extractor._get_node_text_optimized = mock_get_text

    class_obj = extractor._extract_class_optimized(mock_node)
    assert class_obj is not None
    assert isinstance(class_obj, Class)
    assert class_obj.name == "Test"
    assert len(class_obj.interfaces) == 2
    assert "Interface1" in class_obj.interfaces
    assert "Interface2" in class_obj.interfaces
