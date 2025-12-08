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


class TestCppPluginLegacyTests:
    """Legacy test cases using FakeNode from original test_cpp directory"""

    class FakeNode:
        """Fake node implementation for legacy tests"""

        def __init__(
            self,
            type_,
            text,
            start_line=0,
            start_col=0,
            end_line=None,
            end_col=None,
            children=None,
            fields=None,
            start_byte=None,
            end_byte=None,
        ):
            self.type = type_
            self._text = text
            self.children = children or []
            self.start_point = (start_line, start_col)
            end_line = end_line if end_line is not None else start_line
            end_col = end_col if end_col is not None else (start_col + len(text))
            self.end_point = (end_line, end_col)
            self.start_byte = 0 if start_byte is None else start_byte
            self.end_byte = (
                (self.start_byte + len(text)) if end_byte is None else end_byte
            )
            self._fields = fields or {}
            self.parent = None  # Add parent attribute

        def child_by_field_name(self, name):
            return self._fields.get(name)

    @staticmethod
    def make_tree(root):
        """Create a simple tree with root node"""
        from types import SimpleNamespace

        return SimpleNamespace(root_node=root)

    def test_plugin_metadata_legacy(self) -> None:
        """Test plugin metadata (legacy test)"""
        p = CppPlugin()
        assert p.get_language_name() == "cpp"
        assert ".cpp" in p.get_file_extensions()

    def test_extractor_covers_elements_legacy(self) -> None:
        """Test extractor covers all element types with FakeNode (legacy test)"""
        source = "#include <iostream>\nusing namespace std;\nstruct V {int x;};\nclass G {public: int m(int t){return t;}};\nint v=1;\n"
        extractor = CppElementExtractor()

        fn_text = "int m(int t){return t;}"
        fn_start = source.find(fn_text)
        ident_m = self.FakeNode(
            "identifier", "m", start_byte=fn_start + fn_text.find("m")
        )
        params_text = "(int t)"
        params = self.FakeNode(
            "parameters",
            params_text,
            start_byte=fn_start + fn_text.find(params_text),
            children=[self.FakeNode("identifier", "t")],
        )
        decl = self.FakeNode(
            "declarator",
            "m(int t)",
            start_byte=fn_start + fn_text.find("m"),
            children=[ident_m, params],
            fields={"parameters": params},
        )
        type_node = self.FakeNode("type", "int", start_byte=fn_start)
        fn = self.FakeNode(
            "function_definition",
            fn_text,
            start_line=3,
            start_byte=fn_start,
            fields={"declarator": decl, "type": type_node},
        )

        class_text = "class G {public: int m(int t){return t;}};"
        class_start = source.find(class_text)
        class_name = self.FakeNode(
            "type_identifier", "G", start_byte=class_start + class_text.find("G")
        )
        class_node = self.FakeNode(
            "class_specifier",
            class_text,
            start_line=3,
            start_byte=class_start,
            children=[class_name],
        )

        struct_text = "struct V {int x;};"
        struct_start = source.find(struct_text)
        struct_name = self.FakeNode(
            "type_identifier", "V", start_byte=struct_start + struct_text.find("V")
        )
        struct_node = self.FakeNode(
            "struct_specifier",
            struct_text,
            start_line=2,
            start_byte=struct_start,
            children=[struct_name],
        )

        using_decl = self.FakeNode(
            "using_declaration",
            "using namespace std;",
            start_line=1,
            start_byte=source.find("using namespace std;"),
        )
        ns_def = self.FakeNode(
            "namespace_definition",
            "namespace demo {}",
            start_line=0,
            start_byte=source.find("namespace demo {}")
            if "namespace demo {}" in source
            else 0,
        )
        inc = self.FakeNode(
            "preproc_include",
            "#include <iostream>",
            start_line=0,
            start_byte=source.find("#include <iostream>"),
        )

        var_text = "int v=1;"
        var_start = source.find(var_text)
        decl_name = self.FakeNode(
            "identifier", "v", start_byte=var_start + var_text.find("v")
        )
        init_decl = self.FakeNode(
            "init_declarator",
            "v=1",
            start_byte=var_start + var_text.find("v"),
            children=[decl_name],
        )
        decl_specs = self.FakeNode(
            "declaration_specifiers", "int", start_byte=var_start
        )
        var_decl = self.FakeNode(
            "declaration",
            var_text,
            start_line=4,
            start_byte=var_start,
            children=[init_decl],
            fields={"declaration_specifiers": decl_specs},
        )

        root = self.FakeNode(
            "root",
            source,
            children=[ns_def, inc, using_decl, struct_node, class_node, fn, var_decl],
        )
        tree = self.make_tree(root)

        funcs = extractor.extract_functions(tree, source)
        assert isinstance(funcs, list)

        classes = extractor.extract_classes(tree, source)
        assert isinstance(classes, list)

        vars_ = extractor.extract_variables(tree, source)
        assert isinstance(vars_, list)

        imps = extractor.extract_imports(tree, source)
        texts = [i.import_statement for i in imps if hasattr(i, "import_statement")]
        assert (
            any(x.startswith("#include") for x in texts)
            or any("using" in x for x in texts)
            or any("namespace" in x for x in texts)
        )

    @pytest.mark.asyncio
    async def test_analyze_file_runs_legacy(self) -> None:
        """Test analyze_file runs successfully on example file (legacy test)"""
        from types import SimpleNamespace

        p = CppPlugin()
        path = os.path.join("examples", "sample.cpp")
        out = await p.analyze_file(path, SimpleNamespace())
        assert out is not None
