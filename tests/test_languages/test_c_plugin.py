#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.languages.c_plugin module.

This module tests the CPlugin class which provides C language
support in the new plugin architecture.
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.c_plugin import CElementExtractor, CPlugin
from tree_sitter_analyzer.models import Class, Function, Import
from tree_sitter_analyzer.plugins.base import ElementExtractor, LanguagePlugin


class TestCElementExtractor:
    """Test cases for CElementExtractor class"""

    @pytest.fixture
    def extractor(self) -> CElementExtractor:
        """Create a CElementExtractor instance for testing"""
        return CElementExtractor()

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
    def sample_c_code(self) -> str:
        """Sample C code for testing"""
        return """
#include <stdio.h>
#include <stdlib.h>

/**
 * Calculator struct for basic arithmetic operations
 */
typedef struct {
    int value;
    char* name;
} Calculator;

/**
 * Initialize the calculator
 */
Calculator* calculator_init(int initialValue) {
    Calculator* calc = malloc(sizeof(Calculator));
    if (calc) {
        calc->value = initialValue;
        calc->name = "Calculator";
    }
    return calc;
}

/**
 * Add a number to the current value
 */
int calculator_add(Calculator* calc, int number) {
    if (calc) {
        return calc->value + number;
    }
    return 0;
}

/**
 * Get the current value
 */
int calculator_get_value(const Calculator* calc) {
    return calc ? calc->value : 0;
}

static void internal_function(void) {
    printf("Internal function\\n");
}
"""

    def test_extractor_initialization(self, extractor: CElementExtractor) -> None:
        """Test CElementExtractor initialization"""
        assert extractor is not None
        assert isinstance(extractor, ElementExtractor)
        assert hasattr(extractor, "extract_functions")
        assert hasattr(extractor, "extract_classes")
        assert hasattr(extractor, "extract_variables")
        assert hasattr(extractor, "extract_imports")

    def test_extract_functions_success(
        self, extractor: CElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful function extraction"""
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"function.definition": []}

        functions = extractor.extract_functions(mock_tree, "test code")

        assert isinstance(functions, list)

    def test_extract_functions_no_language(
        self, extractor: CElementExtractor
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
        self, extractor: CElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful class extraction (structs in C)"""
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"struct.specifier": []}

        classes = extractor.extract_classes(mock_tree, "test code")

        assert isinstance(classes, list)

    def test_extract_variables_success(
        self, extractor: CElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful variable extraction"""
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"field.declaration": []}

        variables = extractor.extract_variables(mock_tree, "test code")

        assert isinstance(variables, list)

    def test_extract_imports_success(
        self, extractor: CElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful import extraction"""
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"include": []}

        imports = extractor.extract_imports(mock_tree, "test code")

        assert isinstance(imports, list)

    def test_extract_function_optimized(
        self, extractor: CElementExtractor
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

        assert result is None or isinstance(result, Function)

    def test_extract_struct_optimized(self, extractor: CElementExtractor) -> None:
        """Test optimized struct extraction"""
        mock_node = Mock()
        mock_node.type = "struct_specifier"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.children = []

        result = extractor._extract_struct_optimized(mock_node)

        assert result is None or isinstance(result, Class)

    def test_extract_union_optimized(self, extractor: CElementExtractor) -> None:
        """Test optimized union extraction"""
        mock_node = Mock()
        mock_node.type = "union_specifier"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.children = []

        result = extractor._extract_union_optimized(mock_node)

        assert result is None or isinstance(result, Class)

    def test_extract_enum_optimized(self, extractor: CElementExtractor) -> None:
        """Test optimized enum extraction"""
        mock_node = Mock()
        mock_node.type = "enum_specifier"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.children = []

        result = extractor._extract_enum_optimized(mock_node)

        assert result is None or isinstance(result, Class)

    def test_extract_field_optimized(self, extractor: CElementExtractor) -> None:
        """Test field information extraction"""
        mock_node = Mock()
        mock_node.type = "field_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 20
        mock_node.children = []

        result = extractor._extract_field_optimized(mock_node)

        assert isinstance(result, list)

    def test_calculate_complexity_optimized(
        self, extractor: CElementExtractor
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


class TestCPlugin:
    """Test cases for CPlugin class"""

    @pytest.fixture
    def plugin(self) -> CPlugin:
        """Create a CPlugin instance for testing"""
        return CPlugin()

    def test_plugin_initialization(self, plugin: CPlugin) -> None:
        """Test CPlugin initialization"""
        assert plugin is not None
        assert isinstance(plugin, LanguagePlugin)
        assert hasattr(plugin, "get_language_name")
        assert hasattr(plugin, "get_file_extensions")
        assert hasattr(plugin, "create_extractor")

    def test_get_language_name(self, plugin: CPlugin) -> None:
        """Test getting language name"""
        language_name = plugin.get_language_name()

        assert language_name == "c"

    def test_get_file_extensions(self, plugin: CPlugin) -> None:
        """Test getting file extensions"""
        extensions = plugin.get_file_extensions()

        assert isinstance(extensions, list)
        assert ".c" in extensions
        assert ".h" in extensions

    def test_create_extractor(self, plugin: CPlugin) -> None:
        """Test creating element extractor"""
        extractor = plugin.create_extractor()

        assert isinstance(extractor, CElementExtractor)
        assert isinstance(extractor, ElementExtractor)

    def test_is_applicable_c_file(self, plugin: CPlugin) -> None:
        """Test applicability check for C file"""
        assert plugin.is_applicable("test.c") is True
        assert plugin.is_applicable("test.h") is True

    def test_is_applicable_non_c_file(self, plugin: CPlugin) -> None:
        """Test applicability check for non-C file"""
        assert plugin.is_applicable("test.py") is False
        assert plugin.is_applicable("test.java") is False
        assert plugin.is_applicable("test.cpp") is False

    def test_get_plugin_info(self, plugin: CPlugin) -> None:
        """Test getting plugin information"""
        info = plugin.get_plugin_info()

        assert isinstance(info, dict)
        assert "language" in info
        assert "extensions" in info
        assert info["language"] == "c"

    def test_get_tree_sitter_language(self, plugin: CPlugin) -> None:
        """Test getting tree-sitter language"""
        with (
            patch("tree_sitter_c.language") as mock_language,
            patch("tree_sitter.Language") as mock_language_constructor,
        ):
            mock_lang_obj = Mock()
            mock_language.return_value = mock_lang_obj
            mock_language_constructor.return_value = mock_lang_obj

            language = plugin.get_tree_sitter_language()

            assert language is mock_lang_obj

    def test_get_tree_sitter_language_caching(self, plugin: CPlugin) -> None:
        """Test tree-sitter language caching"""
        with (
            patch("tree_sitter_c.language") as mock_language,
            patch("tree_sitter.Language") as mock_language_constructor,
        ):
            mock_lang_obj = Mock()
            mock_language.return_value = mock_lang_obj
            mock_language_constructor.return_value = mock_lang_obj

            language1 = plugin.get_tree_sitter_language()
            language2 = plugin.get_tree_sitter_language()

            assert language1 is language2
            mock_language.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_file_success(self, plugin: CPlugin) -> None:
        """Test successful file analysis"""
        c_code = """
#include <stdio.h>

int main() {
    printf("Hello, World!\\n");
    return 0;
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".c", delete=False) as f:
            f.write(c_code)
            temp_path = f.name

        try:
            mock_request = Mock()
            mock_request.file_path = temp_path
            mock_request.language = "c"
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
    async def test_analyze_file_nonexistent(self, plugin: CPlugin) -> None:
        """Test analysis of non-existent file"""
        mock_request = Mock()
        mock_request.file_path = "/nonexistent/file.c"
        mock_request.language = "c"

        result = await plugin.analyze_file("/nonexistent/file.c", mock_request)

        assert result is not None
        assert hasattr(result, "success")
        assert result.success is False


class TestCPluginErrorHandling:
    """Test error handling in CPlugin"""

    @pytest.fixture
    def plugin(self) -> CPlugin:
        """Create a CPlugin instance for testing"""
        return CPlugin()

    @pytest.fixture
    def extractor(self) -> CElementExtractor:
        """Create a CElementExtractor instance for testing"""
        return CElementExtractor()

    def test_extract_functions_with_exception(
        self, extractor: CElementExtractor
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
        self, extractor: CElementExtractor
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

    def test_get_tree_sitter_language_failure(self, plugin: CPlugin) -> None:
        """Test tree-sitter language loading failure"""
        with patch("tree_sitter_c.language") as mock_language:
            mock_language.side_effect = ImportError("Module not found")

            language = plugin.get_tree_sitter_language()

            assert language is None

    @pytest.mark.asyncio
    async def test_analyze_file_with_exception(self, plugin: CPlugin) -> None:
        """Test file analysis with exception"""
        c_code = "int main() { return 0; }"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".c", delete=False) as f:
            f.write(c_code)
            temp_path = f.name

        try:
            mock_request = Mock()
            mock_request.file_path = temp_path
            mock_request.language = "c"

            with patch("builtins.open") as mock_open:
                mock_open.side_effect = Exception("Read error")

                result = await plugin.analyze_file(temp_path, mock_request)

                assert result is not None
                assert hasattr(result, "success")
                assert result.success is False

        finally:
            os.unlink(temp_path)


class TestCPluginIntegration:
    """Integration tests for CPlugin"""

    @pytest.fixture
    def plugin(self) -> CPlugin:
        """Create a CPlugin instance for testing"""
        return CPlugin()

    def test_full_extraction_workflow(self, plugin: CPlugin) -> None:
        """Test complete extraction workflow"""
        extractor = plugin.create_extractor()
        assert isinstance(extractor, CElementExtractor)

        # Test applicability
        assert plugin.is_applicable("main.c") is True
        assert plugin.is_applicable("calculator.py") is False

        # Test plugin info
        info = plugin.get_plugin_info()
        assert info["language"] == "c"
        assert ".c" in info["extensions"]

    def test_plugin_consistency(self, plugin: CPlugin) -> None:
        """Test plugin consistency across multiple calls"""
        for _ in range(5):
            assert plugin.get_language_name() == "c"
            assert ".c" in plugin.get_file_extensions()
            assert isinstance(plugin.create_extractor(), CElementExtractor)

    def test_extractor_consistency(self, plugin: CPlugin) -> None:
        """Test extractor consistency"""
        extractor1 = plugin.create_extractor()
        extractor2 = plugin.create_extractor()

        assert extractor1 is not extractor2
        assert isinstance(extractor1, CElementExtractor)
        assert isinstance(extractor2, CElementExtractor)

    def test_plugin_with_various_c_files(self, plugin: CPlugin) -> None:
        """Test plugin with various C file types"""
        c_files = [
            "test.c",
            "test.h",
            "src/main.c",
            "include/header.h",
            "TEST.C",
            "test.H",
        ]

        for c_file in c_files:
            assert plugin.is_applicable(c_file) is True

        non_c_files = [
            "test.py",
            "test.java",
            "test.cpp",  # C++ files should not match C plugin
            "test.hpp",
            "test.txt",
            "c.txt",
        ]

        for non_c_file in non_c_files:
            assert plugin.is_applicable(non_c_file) is False
