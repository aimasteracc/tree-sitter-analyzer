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
from tree_sitter_analyzer.models import Class, Function
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

    def test_extract_core_elements_success(
        self, extractor: CppElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful extraction of the core C++ element families."""
        cases = (
            ("functions", {"function.definition": []}, extractor.extract_functions),
            ("classes", {"class.specifier": []}, extractor.extract_classes),
            ("variables", {"field.declaration": []}, extractor.extract_variables),
            ("imports", {"include": []}, extractor.extract_imports),
        )
        for label, captures, extract in cases:
            mock_query = Mock()
            mock_tree.language.query.return_value = mock_query
            mock_query.captures.return_value = captures

            result = extract(mock_tree, "test code")

            assert isinstance(result, list), label

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

    def test_extract_function_optimized(self, extractor: CppElementExtractor) -> None:
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
        assert simple_complexity == 1
        assert complex_complexity == 2


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
        from tree_sitter_analyzer.models.result import AnalysisResult

        out = await p.analyze_file(path, SimpleNamespace())
        assert isinstance(out, AnalysisResult)


# ---------------------------------------------------------------------------
# Tests migrated from test_cpp_plugin_coverage_boost_core.py
# ---------------------------------------------------------------------------


def _parse_cpp(code: str):
    import tree_sitter
    import tree_sitter_cpp

    lang = tree_sitter.Language(tree_sitter_cpp.language())
    parser = tree_sitter.Parser(lang)
    return parser.parse(code.encode("utf-8"))


class TestCppPluginCore:
    """Core behavioral tests for C++ extraction."""

    @pytest.fixture
    def extractor(self):
        return CppElementExtractor()

    @pytest.fixture
    def plugin(self):
        return CppPlugin()

    def test_template_function(self, extractor):
        code = "template <typename T> T max_val(T a, T b) { return a > b ? a : b; }\n"
        tree = _parse_cpp(code)
        funcs = extractor.extract_functions(tree, code)
        names = [f.name for f in funcs]
        assert "max_val" in names
        tfunc = next(f for f in funcs if f.name == "max_val")
        assert "template" in (tfunc.modifiers or [])

    def test_template_class(self, extractor):
        code = "template <typename T> class Stack { T data[100]; int top; };\n"
        tree = _parse_cpp(code)
        classes = extractor.extract_classes(tree, code)
        names = [c.name for c in classes]
        assert "Stack" in names
        tcls = next(c for c in classes if c.name == "Stack")
        assert "template" in (tcls.modifiers or [])

    def test_union_extraction(self, extractor):
        code = "union Data { int i; float f; char c; };\n"
        tree = _parse_cpp(code)
        classes = extractor.extract_classes(tree, code)
        assert len(classes) == 1
        unions = [c for c in classes if c.class_type == "union"]
        assert len(unions) == 1
        assert unions[0].name == "Data"

    def test_namespace_extraction(self, extractor):
        code = "namespace physics { double gravity = 9.8; }\n"
        tree = _parse_cpp(code)
        packages = extractor.extract_packages(tree, code)
        assert len(packages) == 1
        assert packages[0].name == "physics"

    def test_using_declaration_import(self, extractor):
        code = "using namespace std;\n"
        tree = _parse_cpp(code)
        imports = extractor.extract_imports(tree, code)
        assert len(imports) == 1
        assert any("using" in i.import_statement for i in imports)

    def test_alias_declaration_import(self, extractor):
        code = "using IntVec = vector<int>;\n"
        tree = _parse_cpp(code)
        imports = extractor.extract_imports(tree, code)
        assert len(imports) == 1
        assert any("IntVec" in i.name for i in imports)

    def test_system_include(self, extractor):
        code = "#include <iostream>\n#include <string>\n"
        tree = _parse_cpp(code)
        imports = extractor.extract_imports(tree, code)
        names = [i.name for i in imports]
        assert "iostream" in names
        assert "string" in names

    def test_class_inheritance(self, extractor):
        code = "class Base { public: virtual void foo() {} };\nclass Derived : public Base { public: void foo() override {} };\n"
        tree = _parse_cpp(code)
        classes = extractor.extract_classes(tree, code)
        derived = [c for c in classes if c.name == "Derived"]
        assert len(derived) == 1
        assert derived[0].superclass == "Base"

    def test_static_const_modifiers(self, extractor):
        code = "class Config { public: static const int MAX_SIZE = 100; };\n"
        tree = _parse_cpp(code)
        variables = extractor.extract_variables(tree, code)
        assert len(variables) == 1
        max_var = [v for v in variables if v.name == "MAX_SIZE"]
        assert len(max_var) == 1
        assert max_var[0].is_static is True
        assert max_var[0].is_constant is True

    def test_global_variable(self, extractor):
        code = "int counter = 0;\nstatic double pi = 3.14;\n"
        tree = _parse_cpp(code)
        variables = extractor.extract_variables(tree, code)
        assert len(variables) == 2
        names = [v.name for v in variables]
        assert "counter" in names

    def test_visibility_public_and_protected(self, extractor):
        code = (
            "class Widget {\n"
            "public:\n"
            "    void show() {}\n"
            "private:\n"
            "    int secret;\n"
            "protected:\n"
            "    void internal() {}\n"
            "};\n"
        )
        tree = _parse_cpp(code)
        funcs = extractor.extract_functions(tree, code)
        show_funcs = [f for f in funcs if f.name == "show"]
        assert len(show_funcs) == 1
        assert show_funcs[0].visibility == "public"
        internal_funcs = [f for f in funcs if f.name == "internal"]
        assert len(internal_funcs) == 1
        assert internal_funcs[0].visibility == "protected"

    def test_struct_default_visibility(self, extractor):
        code = "struct Point { int x; int y; };\n"
        tree = _parse_cpp(code)
        variables = extractor.extract_variables(tree, code)
        x_vars = [v for v in variables if v.name == "x"]
        assert len(x_vars) == 1
        assert x_vars[0].visibility == "public"

    def test_triple_slash_comment(self, extractor):
        code = "/// Computes sum\nint sum(int a, int b) { return a + b; }\n"
        tree = _parse_cpp(code)
        funcs = extractor.extract_functions(tree, code)
        sum_funcs = [f for f in funcs if f.name == "sum"]
        assert len(sum_funcs) == 1
        assert sum_funcs[0].docstring is not None
        assert "Computes" in sum_funcs[0].docstring

    def test_complexity_with_control_flow(self, extractor):
        code = (
            "int classify(int x) {\n"
            "    if (x > 0) return 1;\n"
            "    else if (x < 0) return -1;\n"
            "    for (int i = 0; i < x; i++) {}\n"
            "    while (x > 10) { x--; }\n"
            "    return 0;\n"
            "}\n"
        )
        tree = _parse_cpp(code)
        funcs = extractor.extract_functions(tree, code)
        classify = [f for f in funcs if f.name == "classify"]
        assert len(classify) == 1
        assert classify[0].complexity_score == 5

    def test_extract_elements_none_tree(self, plugin):
        result = plugin.extract_elements(None, "code")
        assert result["functions"] == []
        assert result["classes"] == []
        assert result["variables"] == []
        assert result["imports"] == []
        assert result["packages"] == []

    def test_count_tree_nodes_cpp(self, plugin):
        code = "int main() { return 0; }\n"
        tree = _parse_cpp(code)
        count = plugin._count_tree_nodes(tree.root_node)
        assert count == 15

    def test_count_tree_nodes_none(self, plugin):
        assert plugin._count_tree_nodes(None) == 0

    def test_variable_with_init_declarator(self, extractor):
        code = "int x = 42;\n"
        tree = _parse_cpp(code)
        variables = extractor.extract_variables(tree, code)
        assert len(variables) == 1
        assert variables[0].name == "x"
        assert variables[0].variable_type == "int"

    def test_destructor_extraction(self, extractor):
        code = "class Resource { public: ~Resource() {} };\n"
        tree = _parse_cpp(code)
        funcs = extractor.extract_functions(tree, code)
        dtor_funcs = [f for f in funcs if f.name and "~" in f.name]
        assert len(dtor_funcs) == 1

    def test_static_global_private_visibility(self, extractor):
        code = "static int internal_counter = 0;\n"
        tree = _parse_cpp(code)
        variables = extractor.extract_variables(tree, code)
        ctr_vars = [v for v in variables if v.name == "internal_counter"]
        assert len(ctr_vars) == 1
        assert ctr_vars[0].visibility == "private"

    def test_function_declaration_return_type(self, extractor):
        code = "void initialize(int argc, char** argv);\n"
        tree = _parse_cpp(code)
        funcs = extractor.extract_functions(tree, code)
        init_funcs = [f for f in funcs if f.name == "initialize"]
        assert len(init_funcs) == 1
        assert init_funcs[0].return_type == "void"

    def test_method_declaration_in_class(self, extractor):
        code = "class Engine { public: void start(); void stop(); };\n"
        tree = _parse_cpp(code)
        funcs = extractor.extract_functions(tree, code)
        names = [f.name for f in funcs]
        assert "start" in names
        assert "stop" in names

    def test_mixed_includes_count(self, extractor):
        code = '#include <iostream>\n#include "utils.h"\n'
        tree = _parse_cpp(code)
        imports = extractor.extract_imports(tree, code)
        assert len(imports) == 2

    def test_class_default_visibility_private(self, extractor):
        code = "class Secret { int value; };\n"
        tree = _parse_cpp(code)
        variables = extractor.extract_variables(tree, code)
        val_vars = [v for v in variables if v.name == "value"]
        assert len(val_vars) == 1
        assert val_vars[0].visibility == "private"

    def test_variable_template_type(self, extractor):
        code = "vector<int> nums;\n"
        tree = _parse_cpp(code)
        variables = extractor.extract_variables(tree, code)
        assert len(variables) == 1
        assert "vector" in (variables[0].variable_type or "")

    def test_function_with_static_modifier(self, extractor):
        code = "static void helper() {}\n"
        tree = _parse_cpp(code)
        funcs = extractor.extract_functions(tree, code)
        helper_funcs = [f for f in funcs if f.name == "helper"]
        assert len(helper_funcs) == 1
        assert helper_funcs[0].is_static is True

    def test_template_struct(self, extractor):
        code = "template <typename T> struct Holder { T value; };\n"
        tree = _parse_cpp(code)
        classes = extractor.extract_classes(tree, code)
        holders = [c for c in classes if c.name == "Holder"]
        assert len(holders) == 1
        assert "template" in (holders[0].modifiers or [])


class TestCppPluginAdvanced:
    """Advanced behavioral tests for C++ extraction."""

    @pytest.fixture
    def extractor(self):
        return CppElementExtractor()

    @pytest.fixture
    def plugin(self):
        return CppPlugin()

    def test_function_multiple_parameters(self, extractor):
        code = "int add(int a, int b, int c) { return a + b + c; }\n"
        tree = _parse_cpp(code)
        funcs = extractor.extract_functions(tree, code)
        add_funcs = [f for f in funcs if f.name == "add"]
        assert len(add_funcs) == 1
        assert len(add_funcs[0].parameters) == 3

    def test_protected_access_specifier(self, extractor):
        code = "class Base {\nprotected:\n    void do_thing() {}\n};\n"
        tree = _parse_cpp(code)
        funcs = extractor.extract_functions(tree, code)
        thing_funcs = [f for f in funcs if f.name == "do_thing"]
        assert len(thing_funcs) == 1
        assert thing_funcs[0].visibility == "protected"

    def test_protected_explicit_modifier_determine_visibility(self, extractor):
        result = extractor._determine_visibility(
            ["protected"], is_global=False, node=None
        )
        assert result == "protected"

    def test_private_explicit_modifier_determine_visibility(self, extractor):
        result = extractor._determine_visibility(
            ["private"], is_global=False, node=None
        )
        assert result == "private"

    def test_public_explicit_modifier_determine_visibility(self, extractor):
        result = extractor._determine_visibility(["public"], is_global=True, node=None)
        assert result == "public"

    def test_static_global_determine_visibility(self, extractor):
        result = extractor._determine_visibility(["static"], is_global=True, node=None)
        assert result == "private"

    def test_default_visibility_global_vs_local(self, extractor):
        assert (
            extractor._determine_visibility([], is_global=True, node=None) == "public"
        )
        assert (
            extractor._determine_visibility([], is_global=False, node=None) == "private"
        )

    def test_field_init_declarator_type(self, extractor):
        code = "class Pair { int val = 0; };\n"
        tree = _parse_cpp(code)
        variables = extractor.extract_variables(tree, code)
        val_vars = [v for v in variables if v.name == "val"]
        assert len(val_vars) == 1
        assert val_vars[0].variable_type == "int"

    def test_include_fallback_local_only(self, extractor):
        code = '#include "local_header.h"\n'
        tree = _parse_cpp(code)
        imports = extractor.extract_imports(tree, code)
        names = [i.name for i in imports]
        assert "local_header.h" in names

    def test_virtual_const_function_modifiers(self, extractor):
        code = "class Shape {\npublic:\n    virtual double area() const = 0;\n};\n"
        tree = _parse_cpp(code)
        funcs = extractor.extract_functions(tree, code)
        area_funcs = [f for f in funcs if f.name == "area"]
        assert len(area_funcs) == 1
        assert "virtual" in (area_funcs[0].modifiers or [])
        assert "pure_virtual" in (area_funcs[0].modifiers or [])

    def test_for_range_complexity(self, extractor):
        code = "int sum_items() {\n    int total = 0;\n    for (int x : items) { total += x; }\n    return total;\n}\n"
        tree = _parse_cpp(code)
        funcs = extractor.extract_functions(tree, code)
        sum_funcs = [f for f in funcs if f.name == "sum_items"]
        assert len(sum_funcs) == 1
        assert sum_funcs[0].complexity_score == 2

    def test_switch_complexity(self, extractor):
        code = "int grade(int score) {\n    switch(score) {\n        case 90: return 4;\n        case 80: return 3;\n        default: return 0;\n    }\n}\n"
        tree = _parse_cpp(code)
        funcs = extractor.extract_functions(tree, code)
        grade_funcs = [f for f in funcs if f.name == "grade"]
        assert len(grade_funcs) == 1
        # A switch counts once (construct-once convention); cases are not summed.
        assert grade_funcs[0].complexity_score == 2

    def test_try_catch_complexity(self, extractor):
        code = "void safe_op() {\n    try { risky(); }\n    catch (int e) { handle(e); }\n}\n"
        tree = _parse_cpp(code)
        funcs = extractor.extract_functions(tree, code)
        safe_funcs = [f for f in funcs if f.name == "safe_op"]
        assert len(safe_funcs) == 1
        assert safe_funcs[0].complexity_score == 2

    def test_is_global_scope_root(self, extractor):
        code = "class Foo { int x; };\n"
        tree = _parse_cpp(code)
        assert extractor._is_global_scope(tree.root_node) is True

    def test_count_tree_nodes_with_children(self, plugin):
        code = "class Foo { int x; void bar() {} };\n"
        tree = _parse_cpp(code)
        count = plugin._count_tree_nodes(tree.root_node)
        assert count == 22

    def test_doxygen_comment_on_class(self, extractor):
        code = "/**\n * A documented class.\n */\nclass DocClass {\n};\n"
        tree = _parse_cpp(code)
        classes = extractor.extract_classes(tree, code)
        dc = [c for c in classes if c.name == "DocClass"]
        assert len(dc) == 1
        assert dc[0].docstring is not None
        assert "documented" in dc[0].docstring

    def test_namespace_identifier_node(self, extractor):
        code = "namespace my_lib { int val = 42; }\n"
        tree = _parse_cpp(code)
        packages = extractor.extract_packages(tree, code)
        assert len(packages) == 1
        assert packages[0].name == "my_lib"

    def test_static_field_declaration(self, extractor):
        code = "class Counter {\n    static int count;\n};\n"
        tree = _parse_cpp(code)
        variables = extractor.extract_variables(tree, code)
        count_vars = [v for v in variables if v.name == "count"]
        assert len(count_vars) == 1
        assert count_vars[0].is_static is True

    def test_include_fallback_regex_direct(self, extractor):
        code = '#include <iostream>\n#include "myheader.h"\n'
        imports = extractor._extract_includes_fallback(code)
        assert len(imports) == 2
        names = [i.name for i in imports]
        assert "iostream" in names
        assert "myheader.h" in names

    def test_include_fallback_system_only(self, extractor):
        code = "#include <vector>\n#include <string>\n"
        imports = extractor._extract_includes_fallback(code)
        assert len(imports) == 2
        names = [i.name for i in imports]
        assert "vector" in names
        assert "string" in names

    @pytest.mark.asyncio
    async def test_analyze_file_cpp_line_count(self, plugin, tmp_path):
        from types import SimpleNamespace

        cpp_file = tmp_path / "test.cpp"
        cpp_file.write_text(
            "#include <iostream>\n"
            "namespace demo {\n"
            "class Widget {\n"
            "public:\n"
            "    int value;\n"
            "    void work() {}\n"
            "};\n"
            "}  // namespace demo\n"
        )
        result = await plugin.analyze_file(str(cpp_file), SimpleNamespace())
        assert result is not None
        assert result.language == "cpp"
        assert result.line_count == 8
