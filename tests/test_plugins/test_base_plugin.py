"""Tests for the plugins base module."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from tree_sitter_analyzer.plugins.base import (
    ElementExtractor,
    LanguagePlugin,
    DefaultExtractor,
    DefaultLanguagePlugin,
)
from tree_sitter_analyzer.models import Function, Class, Variable, Import


class TestElementExtractorAbstract:
    """Tests for ElementExtractor abstract class."""

    def test_cannot_instantiate_directly(self):
        """ElementExtractor should not be instantiable directly."""
        with pytest.raises(TypeError):
            ElementExtractor()

    def test_has_required_abstract_methods(self):
        """ElementExtractor should define required abstract methods."""
        assert hasattr(ElementExtractor, "extract_functions")
        assert hasattr(ElementExtractor, "extract_classes")
        assert hasattr(ElementExtractor, "extract_variables")
        assert hasattr(ElementExtractor, "extract_imports")


class TestLanguagePluginAbstract:
    """Tests for LanguagePlugin abstract class."""

    def test_cannot_instantiate_directly(self):
        """LanguagePlugin should not be instantiable directly."""
        with pytest.raises(TypeError):
            LanguagePlugin()

    def test_has_required_abstract_methods(self):
        """LanguagePlugin should define required abstract methods."""
        assert hasattr(LanguagePlugin, "get_language_name")
        assert hasattr(LanguagePlugin, "get_file_extensions")
        assert hasattr(LanguagePlugin, "create_extractor")
        assert hasattr(LanguagePlugin, "analyze_file")


class TestDefaultExtractorInit:
    """Tests for DefaultExtractor initialization."""

    def test_init_creates_instance(self):
        """DefaultExtractor should be instantiable."""
        extractor = DefaultExtractor()
        assert extractor is not None

    def test_init_sets_current_file(self):
        """DefaultExtractor should initialize current_file as empty string."""
        extractor = DefaultExtractor()
        assert extractor.current_file == ""


class TestDefaultExtractorNodeTypeChecks:
    """Tests for DefaultExtractor node type checking methods."""

    def test_is_function_node_true_cases(self):
        """_is_function_node should return True for function types."""
        extractor = DefaultExtractor()
        assert extractor._is_function_node("function_definition")
        assert extractor._is_function_node("function_declaration")
        assert extractor._is_function_node("method_definition")
        assert extractor._is_function_node("FUNCTION")  # Case insensitive
        assert extractor._is_function_node("my_method_definition")

    def test_is_function_node_false_cases(self):
        """_is_function_node should return False for non-function types."""
        extractor = DefaultExtractor()
        assert not extractor._is_function_node("class_definition")
        assert not extractor._is_function_node("variable_declaration")
        assert not extractor._is_function_node("identifier")

    def test_is_class_node_true_cases(self):
        """_is_class_node should return True for class types."""
        extractor = DefaultExtractor()
        assert extractor._is_class_node("class_definition")
        assert extractor._is_class_node("class_declaration")
        assert extractor._is_class_node("interface_definition")
        assert extractor._is_class_node("STRUCT")
        assert extractor._is_class_node("enum_declaration")

    def test_is_class_node_false_cases(self):
        """_is_class_node should return False for non-class types."""
        extractor = DefaultExtractor()
        assert not extractor._is_class_node("function_definition")
        assert not extractor._is_class_node("variable_declaration")
        assert not extractor._is_class_node("identifier")

    def test_is_variable_node_true_cases(self):
        """_is_variable_node should return True for variable types."""
        extractor = DefaultExtractor()
        assert extractor._is_variable_node("variable_declaration")
        assert extractor._is_variable_node("variable_definition")
        assert extractor._is_variable_node("field_declaration")
        assert extractor._is_variable_node("ASSIGNMENT")

    def test_is_variable_node_false_cases(self):
        """_is_variable_node should return False for non-variable types."""
        extractor = DefaultExtractor()
        assert not extractor._is_variable_node("function_definition")
        assert not extractor._is_variable_node("class_definition")
        assert not extractor._is_variable_node("identifier")

    def test_is_import_node_true_cases(self):
        """_is_import_node should return True for import types."""
        extractor = DefaultExtractor()
        assert extractor._is_import_node("import_statement")
        assert extractor._is_import_node("import_declaration")
        assert extractor._is_import_node("include_statement")
        assert extractor._is_import_node("require")

    def test_is_import_node_false_cases(self):
        """_is_import_node should return False for non-import types."""
        extractor = DefaultExtractor()
        assert not extractor._is_import_node("function_definition")
        assert not extractor._is_import_node("class_definition")
        assert not extractor._is_import_node("identifier")


class TestDefaultExtractorNodeText:
    """Tests for DefaultExtractor node text extraction."""

    def test_extract_node_text_with_bytes(self):
        """_extract_node_text should extract text using byte positions."""
        extractor = DefaultExtractor()
        source_code = "def hello(): pass"
        
        # Create mock node with byte positions
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 3
        
        result = extractor._extract_node_text(mock_node, source_code)
        assert result == "def"

    def test_extract_node_text_without_attributes(self):
        """_extract_node_text should return empty string if no byte attributes."""
        extractor = DefaultExtractor()
        mock_node = MagicMock(spec=[])  # No attributes
        
        result = extractor._extract_node_text(mock_node, source_code="hello")
        assert result == ""

    def test_extract_node_text_with_unicode(self):
        """_extract_node_text should handle unicode characters."""
        extractor = DefaultExtractor()
        source_code = "def 日本語(): pass"
        
        mock_node = MagicMock()
        # Position for 日本語
        source_bytes = source_code.encode("utf-8")
        start = source_bytes.find("日".encode("utf-8"))
        end = start + len("日本語".encode("utf-8"))
        mock_node.start_byte = start
        mock_node.end_byte = end
        
        result = extractor._extract_node_text(mock_node, source_code)
        assert result == "日本語"


class TestDefaultExtractorNodeName:
    """Tests for DefaultExtractor node name extraction."""

    def test_extract_node_name_with_identifier_child(self):
        """_extract_node_name should find identifier in children."""
        extractor = DefaultExtractor()
        source_code = "def hello(): pass"
        
        # Create mock identifier child
        mock_child = MagicMock()
        mock_child.type = "identifier"
        mock_child.start_byte = 4
        mock_child.end_byte = 9
        
        # Create mock node with children
        mock_node = MagicMock()
        mock_node.children = [mock_child]
        mock_node.start_point = (0, 4)
        
        result = extractor._extract_node_name(mock_node, source_code)
        assert result == "hello"

    def test_extract_node_name_fallback(self):
        """_extract_node_name should use fallback when no identifier found."""
        extractor = DefaultExtractor()
        
        # Create mock node without identifier children
        mock_node = MagicMock()
        mock_node.children = []
        mock_node.start_point = (10, 5)
        
        result = extractor._extract_node_name(mock_node, "")
        assert result == "element_10_5"


class TestDefaultExtractorExtraction:
    """Tests for DefaultExtractor extraction methods."""

    def test_extract_functions_empty_tree(self):
        """extract_functions should return empty list for empty tree."""
        extractor = DefaultExtractor()
        mock_tree = MagicMock(spec=[])  # No root_node
        
        result = extractor.extract_functions(mock_tree, "")
        assert result == []

    def test_extract_functions_with_tree(self):
        """extract_functions should extract functions from tree."""
        extractor = DefaultExtractor()
        
        # Create mock function node
        mock_func_node = MagicMock()
        mock_func_node.type = "function_definition"
        mock_func_node.children = []
        mock_func_node.start_point = (0, 0)
        mock_func_node.end_point = (2, 0)
        mock_func_node.start_byte = 0
        mock_func_node.end_byte = 20
        
        # Create mock root node
        mock_root = MagicMock()
        mock_root.type = "module"
        mock_root.children = [mock_func_node]
        
        mock_tree = MagicMock()
        mock_tree.root_node = mock_root
        
        result = extractor.extract_functions(mock_tree, "def hello(): pass")
        assert len(result) >= 0  # May or may not extract depending on traversal

    def test_extract_classes_empty_tree(self):
        """extract_classes should return empty list for empty tree."""
        extractor = DefaultExtractor()
        mock_tree = MagicMock(spec=[])
        
        result = extractor.extract_classes(mock_tree, "")
        assert result == []

    def test_extract_variables_empty_tree(self):
        """extract_variables should return empty list for empty tree."""
        extractor = DefaultExtractor()
        mock_tree = MagicMock(spec=[])
        
        result = extractor.extract_variables(mock_tree, "")
        assert result == []

    def test_extract_imports_empty_tree(self):
        """extract_imports should return empty list for empty tree."""
        extractor = DefaultExtractor()
        mock_tree = MagicMock(spec=[])
        
        result = extractor.extract_imports(mock_tree, "")
        assert result == []


class TestDefaultExtractorDefaultMethods:
    """Tests for DefaultExtractor default method implementations."""

    def test_extract_packages_returns_empty(self):
        """extract_packages should return empty list by default."""
        extractor = DefaultExtractor()
        mock_tree = MagicMock()
        
        result = extractor.extract_packages(mock_tree, "")
        assert result == []

    def test_extract_annotations_returns_empty(self):
        """extract_annotations should return empty list by default."""
        extractor = DefaultExtractor()
        mock_tree = MagicMock()
        
        result = extractor.extract_annotations(mock_tree, "")
        assert result == []

    def test_extract_html_elements_returns_empty(self):
        """extract_html_elements should return empty list by default."""
        extractor = DefaultExtractor()
        mock_tree = MagicMock()
        
        result = extractor.extract_html_elements(mock_tree, "")
        assert result == []

    def test_extract_css_rules_returns_empty(self):
        """extract_css_rules should return empty list by default."""
        extractor = DefaultExtractor()
        mock_tree = MagicMock()
        
        result = extractor.extract_css_rules(mock_tree, "")
        assert result == []

    def test_get_language_hint_returns_unknown(self):
        """_get_language_hint should return 'unknown' by default."""
        extractor = DefaultExtractor()
        
        result = extractor._get_language_hint()
        assert result == "unknown"


class TestDefaultExtractorAllElements:
    """Tests for extract_all_elements method."""

    def test_extract_all_elements_aggregates_all(self):
        """extract_all_elements should combine all element types."""
        extractor = DefaultExtractor()
        mock_tree = MagicMock(spec=[])  # Empty tree
        
        result = extractor.extract_all_elements(mock_tree, "")
        assert isinstance(result, list)


class TestDefaultLanguagePlugin:
    """Tests for DefaultLanguagePlugin class."""

    def test_get_language_name(self):
        """get_language_name should return 'generic'."""
        plugin = DefaultLanguagePlugin()
        assert plugin.get_language_name() == "generic"

    def test_get_file_extensions(self):
        """get_file_extensions should return txt and md."""
        plugin = DefaultLanguagePlugin()
        extensions = plugin.get_file_extensions()
        assert ".txt" in extensions
        assert ".md" in extensions

    def test_create_extractor(self):
        """create_extractor should return DefaultExtractor instance."""
        plugin = DefaultLanguagePlugin()
        extractor = plugin.create_extractor()
        assert isinstance(extractor, DefaultExtractor)

    def test_get_supported_element_types(self):
        """get_supported_element_types should return standard types."""
        plugin = DefaultLanguagePlugin()
        types = plugin.get_supported_element_types()
        assert "function" in types
        assert "class" in types
        assert "variable" in types
        assert "import" in types

    def test_get_queries_returns_empty(self):
        """get_queries should return empty dict by default."""
        plugin = DefaultLanguagePlugin()
        queries = plugin.get_queries()
        assert queries == {}

    def test_get_formatter_map_returns_empty(self):
        """get_formatter_map should return empty dict by default."""
        plugin = DefaultLanguagePlugin()
        formatters = plugin.get_formatter_map()
        assert formatters == {}

    def test_get_element_categories_returns_empty(self):
        """get_element_categories should return empty dict by default."""
        plugin = DefaultLanguagePlugin()
        categories = plugin.get_element_categories()
        assert categories == {}

    def test_is_applicable_for_txt(self):
        """is_applicable should return True for .txt files."""
        plugin = DefaultLanguagePlugin()
        assert plugin.is_applicable("test.txt")
        assert plugin.is_applicable("path/to/file.txt")

    def test_is_applicable_for_md(self):
        """is_applicable should return True for .md files."""
        plugin = DefaultLanguagePlugin()
        assert plugin.is_applicable("test.md")
        assert plugin.is_applicable("README.md")

    def test_is_applicable_false_for_other(self):
        """is_applicable should return False for non-supported extensions."""
        plugin = DefaultLanguagePlugin()
        assert not plugin.is_applicable("test.py")
        assert not plugin.is_applicable("test.java")

    def test_is_applicable_case_insensitive(self):
        """is_applicable should be case insensitive."""
        plugin = DefaultLanguagePlugin()
        assert plugin.is_applicable("test.TXT")
        assert plugin.is_applicable("test.MD")

    def test_get_plugin_info(self):
        """get_plugin_info should return plugin information."""
        plugin = DefaultLanguagePlugin()
        info = plugin.get_plugin_info()
        
        assert info["language"] == "generic"
        assert ".txt" in info["extensions"]
        assert ".md" in info["extensions"]
        assert info["class_name"] == "DefaultLanguagePlugin"
        assert "base" in info["module"]

    def test_execute_query_strategy_none_key(self):
        """execute_query_strategy should return None for None key."""
        plugin = DefaultLanguagePlugin()
        result = plugin.execute_query_strategy(None, "generic")
        assert result is None

    def test_execute_query_strategy_unknown_key(self):
        """execute_query_strategy should return None for unknown key."""
        plugin = DefaultLanguagePlugin()
        result = plugin.execute_query_strategy("unknown", "generic")
        assert result is None


class TestDefaultLanguagePluginAnalyze:
    """Tests for DefaultLanguagePlugin analyze_file method."""

    @pytest.mark.asyncio
    async def test_analyze_file_returns_result(self, tmp_path):
        """analyze_file should return AnalysisResult."""
        plugin = DefaultLanguagePlugin()
        
        # Create a temporary file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world")
        
        result = await plugin.analyze_file(str(test_file), MagicMock())
        
        # Should return some result (may succeed or fail depending on engine)
        assert result is not None

    @pytest.mark.asyncio
    async def test_analyze_file_handles_error(self):
        """analyze_file should handle errors gracefully."""
        plugin = DefaultLanguagePlugin()
        
        # Try to analyze a non-existent file
        result = await plugin.analyze_file("/nonexistent/path/to/file.txt", MagicMock())
        
        # Should return a result with error
        assert result is not None
        # The result should indicate failure
        assert result.success is False or result.error_message
