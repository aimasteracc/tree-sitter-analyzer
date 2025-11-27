#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.languages.cpp_plugin module.

This module tests the CppPlugin class which provides C++ language
support in the new plugin architecture.
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.cpp_plugin import CppElementExtractor, CppPlugin
from tree_sitter_analyzer.models import Class, Function, Import
from tree_sitter_analyzer.plugins.base import ElementExtractor, LanguagePlugin


class TestCppElementExtractor:
    """Test cases for CppElementExtractor class"""

    @pytest.fixture
    def extractor(self) -> CppElementExtractor:
        """Create a CppElementExtractor instance for testing"""
        return CppElementExtractor()

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
    def sample_cpp_code(self) -> str:
        """Sample C++ code for testing"""
        return """
#include <iostream>
#include <string>

namespace example {

/**
 * Calculator class for basic arithmetic operations
 */
class Calculator {
private:
    int value;
    static const std::string VERSION;

public:
    /**
     * Constructor
     */
    Calculator(int initialValue) : value(initialValue) {}

    /**
     * Add a number to the current value
     */
    int add(int number) {
        return value + number;
    }

    /**
     * Get the current value
     */
    int getValue() const {
        return value;
    }

    virtual void reset() {
        value = 0;
    }
};

const std::string Calculator::VERSION = "1.0";

}  // namespace example
"""

    def test_extractor_initialization(self, extractor: CppElementExtractor) -> None:
        """Test CppElementExtractor initialization"""
        assert extractor is not None
        assert isinstance(extractor, ElementExtractor)
        assert hasattr(extractor, "extract_functions")
        assert hasattr(extractor, "extract_classes")
        assert hasattr(extractor, "extract_variables")
        assert hasattr(extractor, "extract_imports")

    def test_extract_functions_success(
        self, extractor: CppElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful function extraction"""
        # Mock the language query
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"function.definition": []}

        functions = extractor.extract_functions(mock_tree, "test code")

        assert isinstance(functions, list)

    def test_extract_functions_no_language(
        self, extractor: CppElementExtractor
    ) -> None:
        """Test function extraction when language is not available"""
        mock_tree = Mock()
        mock_tree.language = None
        mock_root = Mock()
        mock_root.children = []
        mock_tree.root_node = mock_root

        functions = extractor.extract_functions(mock_tree, "test code")

        assert isinstance(functions, list)
        assert len(functions) == 0

    def test_extract_classes_success(
        self, extractor: CppElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful class extraction"""
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"class.specifier": []}

        classes = extractor.extract_classes(mock_tree, "test code")

        assert isinstance(classes, list)

    def test_extract_variables_success(
        self, extractor: CppElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful variable extraction"""
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"field.declaration": []}

        variables = extractor.extract_variables(mock_tree, "test code")

        assert isinstance(variables, list)

    def test_extract_imports_success(
        self, extractor: CppElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful import extraction"""
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"include": []}

        imports = extractor.extract_imports(mock_tree, "test code")

        assert isinstance(imports, list)

    def test_extract_function_optimized(
        self, extractor: CppElementExtractor
    ) -> None:
        """Test optimized function extraction"""
        mock_node = Mock()
        mock_node.type = "function_definition"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.children = []

        result = extractor._extract_function_optimized(mock_node)

        # The method should handle the mock gracefully
        assert result is None or isinstance(result, Function)

    def test_extract_class_optimized(self, extractor: CppElementExtractor) -> None:
        """Test optimized class extraction"""
        mock_node = Mock()
        mock_node.type = "class_specifier"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.children = []

        result = extractor._extract_class_optimized(mock_node)

        # The method should handle the mock gracefully
        assert result is None or isinstance(result, Class)

    def test_extract_field_optimized(self, extractor: CppElementExtractor) -> None:
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

    def test_calculate_complexity_optimized(
        self, extractor: CppElementExtractor
    ) -> None:
        """Test complexity calculation"""
        simple_node = Mock()
        simple_node.type = "return_statement"
        simple_node.children = []

        complex_node = Mock()
        complex_node.type = "if_statement"
        complex_node.children = [Mock(), Mock(), Mock()]

        simple_complexity = extractor._calculate_complexity_optimized(simple_node)
        complex_complexity = extractor._calculate_complexity_optimized(complex_node)

        assert isinstance(simple_complexity, int)
        assert isinstance(complex_complexity, int)
        assert simple_complexity >= 1
        assert complex_complexity >= 1


class TestCppPlugin:
    """Test cases for CppPlugin class"""

    @pytest.fixture
    def plugin(self) -> CppPlugin:
        """Create a CppPlugin instance for testing"""
        return CppPlugin()

    def test_plugin_initialization(self, plugin: CppPlugin) -> None:
        """Test CppPlugin initialization"""
        assert plugin is not None
        assert isinstance(plugin, LanguagePlugin)
        assert hasattr(plugin, "get_language_name")
        assert hasattr(plugin, "get_file_extensions")
        assert hasattr(plugin, "create_extractor")

    def test_get_language_name(self, plugin: CppPlugin) -> None:
        """Test getting language name"""
        language_name = plugin.get_language_name()

        assert language_name == "cpp"

    def test_get_file_extensions(self, plugin: CppPlugin) -> None:
        """Test getting file extensions"""
        extensions = plugin.get_file_extensions()

        assert isinstance(extensions, list)
        assert ".cpp" in extensions
        assert ".hpp" in extensions
        assert ".cc" in extensions
        assert ".cxx" in extensions

    def test_create_extractor(self, plugin: CppPlugin) -> None:
        """Test creating element extractor"""
        extractor = plugin.create_extractor()

        assert isinstance(extractor, CppElementExtractor)
        assert isinstance(extractor, ElementExtractor)

    def test_is_applicable_cpp_file(self, plugin: CppPlugin) -> None:
        """Test applicability check for C++ file"""
        assert plugin.is_applicable("test.cpp") is True
        assert plugin.is_applicable("test.hpp") is True
        assert plugin.is_applicable("test.cc") is True
        assert plugin.is_applicable("test.cxx") is True

    def test_is_applicable_non_cpp_file(self, plugin: CppPlugin) -> None:
        """Test applicability check for non-C++ file"""
        assert plugin.is_applicable("test.py") is False
        assert plugin.is_applicable("test.java") is False
        assert plugin.is_applicable("test.c") is False

    def test_get_plugin_info(self, plugin: CppPlugin) -> None:
        """Test getting plugin information"""
        info = plugin.get_plugin_info()

        assert isinstance(info, dict)
        assert "language" in info
        assert "extensions" in info
        assert info["language"] == "cpp"

    def test_get_tree_sitter_language(self, plugin: CppPlugin) -> None:
        """Test getting tree-sitter language"""
        with (
            patch("tree_sitter_cpp.language") as mock_language,
            patch("tree_sitter.Language") as mock_language_constructor,
        ):
            mock_lang_obj = Mock()
            mock_language.return_value = mock_lang_obj
            mock_language_constructor.return_value = mock_lang_obj

            language = plugin.get_tree_sitter_language()

            assert language is mock_lang_obj

    def test_get_tree_sitter_language_caching(self, plugin: CppPlugin) -> None:
        """Test tree-sitter language caching"""
        with (
            patch("tree_sitter_cpp.language") as mock_language,
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
            mock_language.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_file_success(self, plugin: CppPlugin) -> None:
        """Test successful file analysis"""
        cpp_code = """
class TestClass {
public:
    void testMethod() {
        std::cout << "Hello" << std::endl;
    }
};
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".cpp", delete=False) as f:
            f.write(cpp_code)
            temp_path = f.name

        try:
            mock_request = Mock()
            mock_request.file_path = temp_path
            mock_request.language = "cpp"
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
    async def test_analyze_file_nonexistent(self, plugin: CppPlugin) -> None:
        """Test analysis of non-existent file"""
        mock_request = Mock()
        mock_request.file_path = "/nonexistent/file.cpp"
        mock_request.language = "cpp"

        result = await plugin.analyze_file("/nonexistent/file.cpp", mock_request)

        assert result is not None
        assert hasattr(result, "success")
        assert result.success is False


class TestCppPluginErrorHandling:
    """Test error handling in CppPlugin"""

    @pytest.fixture
    def plugin(self) -> CppPlugin:
        """Create a CppPlugin instance for testing"""
        return CppPlugin()

    @pytest.fixture
    def extractor(self) -> CppElementExtractor:
        """Create a CppElementExtractor instance for testing"""
        return CppElementExtractor()

    def test_extract_functions_with_exception(
        self, extractor: CppElementExtractor
    ) -> None:
        """Test function extraction with exception"""
        mock_tree = Mock()
        mock_tree.language = None
        mock_root = Mock()
        mock_root.children = []
        mock_tree.root_node = mock_root

        functions = extractor.extract_functions(mock_tree, "test code")

        assert isinstance(functions, list)
        assert len(functions) == 0

    def test_extract_classes_with_exception(
        self, extractor: CppElementExtractor
    ) -> None:
        """Test class extraction with exception"""
        mock_tree = Mock()
        mock_tree.language = None
        mock_root = Mock()
        mock_root.children = []
        mock_tree.root_node = mock_root

        classes = extractor.extract_classes(mock_tree, "test code")

        assert isinstance(classes, list)
        assert len(classes) == 0

    def test_get_tree_sitter_language_failure(self, plugin: CppPlugin) -> None:
        """Test tree-sitter language loading failure"""
        with patch("tree_sitter_cpp.language") as mock_language:
            mock_language.side_effect = ImportError("Module not found")

            language = plugin.get_tree_sitter_language()

            assert language is None

    @pytest.mark.asyncio
    async def test_analyze_file_with_exception(self, plugin: CppPlugin) -> None:
        """Test file analysis with exception"""
        cpp_code = "class Test {};"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".cpp", delete=False) as f:
            f.write(cpp_code)
            temp_path = f.name

        try:
            mock_request = Mock()
            mock_request.file_path = temp_path
            mock_request.language = "cpp"

            with patch("builtins.open") as mock_open:
                mock_open.side_effect = Exception("Read error")

                result = await plugin.analyze_file(temp_path, mock_request)

                assert result is not None
                assert hasattr(result, "success")
                assert result.success is False

        finally:
            os.unlink(temp_path)


class TestCppPluginIntegration:
    """Integration tests for CppPlugin"""

    @pytest.fixture
    def plugin(self) -> CppPlugin:
        """Create a CppPlugin instance for testing"""
        return CppPlugin()

    def test_full_extraction_workflow(self, plugin: CppPlugin) -> None:
        """Test complete extraction workflow"""
        extractor = plugin.create_extractor()
        assert isinstance(extractor, CppElementExtractor)

        # Test applicability
        assert plugin.is_applicable("Calculator.cpp") is True
        assert plugin.is_applicable("calculator.py") is False

        # Test plugin info
        info = plugin.get_plugin_info()
        assert info["language"] == "cpp"
        assert ".cpp" in info["extensions"]

    def test_plugin_consistency(self, plugin: CppPlugin) -> None:
        """Test plugin consistency across multiple calls"""
        for _ in range(5):
            assert plugin.get_language_name() == "cpp"
            assert ".cpp" in plugin.get_file_extensions()
            assert isinstance(plugin.create_extractor(), CppElementExtractor)

    def test_extractor_consistency(self, plugin: CppPlugin) -> None:
        """Test extractor consistency"""
        extractor1 = plugin.create_extractor()
        extractor2 = plugin.create_extractor()

        assert extractor1 is not extractor2
        assert isinstance(extractor1, CppElementExtractor)
        assert isinstance(extractor2, CppElementExtractor)

    def test_plugin_with_various_cpp_files(self, plugin: CppPlugin) -> None:
        """Test plugin with various C++ file types"""
        cpp_files = [
            "test.cpp",
            "test.hpp",
            "test.cc",
            "test.cxx",
            "src/main.cpp",
            "include/header.hpp",
            "TEST.CPP",
            "test.Cpp",
        ]

        for cpp_file in cpp_files:
            assert plugin.is_applicable(cpp_file) is True

        non_cpp_files = [
            "test.py",
            "test.java",
            "test.c",  # C files should not match C++ plugin
            "test.txt",
            "cpp.txt",
        ]

        for non_cpp_file in non_cpp_files:
            assert plugin.is_applicable(non_cpp_file) is False
