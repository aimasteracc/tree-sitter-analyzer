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
from tree_sitter_analyzer.models import Class, Function
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

    def test_extract_core_elements_success(
        self, extractor: CElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful extraction of the core C element families."""
        cases = (
            ("functions", {"function.definition": []}, extractor.extract_functions),
            ("classes", {"struct.specifier": []}, extractor.extract_classes),
            ("variables", {"field.declaration": []}, extractor.extract_variables),
            ("imports", {"include": []}, extractor.extract_imports),
        )
        for label, captures, extract in cases:
            mock_query = Mock()
            mock_tree.language.query.return_value = mock_query
            mock_query.captures.return_value = captures

            result = extract(mock_tree, "test code")

            assert isinstance(result, list), label

    def test_extract_functions_no_language(self, extractor: CElementExtractor) -> None:
        """Test function extraction when language is not available"""
        mock_tree = Mock()
        mock_tree.language = None
        mock_root = Mock()
        mock_root.children = []
        mock_tree.root_node = mock_root

        functions = extractor.extract_functions(mock_tree, "test code")

        assert isinstance(functions, list)
        assert len(functions) == 0

    def test_extract_function_optimized(self, extractor: CElementExtractor) -> None:
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

    def test_calculate_complexity_optimized(self, extractor: CElementExtractor) -> None:
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

    def test_extract_classes_with_exception(self, extractor: CElementExtractor) -> None:
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


class TestCPluginLegacyTests:
    """Legacy test cases using FakeNode from original test_c directory"""

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
        source = "#include <stdio.h>\nint add(int a,int b){return a+b;}\nstruct S {int x;};\nint v=0;\n"
        extractor = CElementExtractor()

        fn_text = "int add(int a,int b){return a+b;}"
        fn_start = source.find(fn_text)
        ident_add = self.FakeNode(
            "identifier", "add", start_byte=fn_start + fn_text.find("add")
        )
        params_text = "(int a,int b)"
        params = self.FakeNode(
            "parameters",
            params_text,
            start_byte=fn_start + fn_text.find(params_text),
            children=[
                self.FakeNode("identifier", "a"),
                self.FakeNode("identifier", "b"),
            ],
        )
        decl = self.FakeNode(
            "declarator",
            "add(int a,int b)",
            start_byte=fn_start + fn_text.find("add"),
            children=[ident_add, params],
            fields={"parameters": params},
        )
        type_node = self.FakeNode("type", "int", start_byte=fn_start)
        fn = self.FakeNode(
            "function_definition",
            fn_text,
            start_line=1,
            start_byte=fn_start,
            fields={"declarator": decl, "type": type_node},
        )

        struct_text = "struct S {int x;};"
        struct_start = source.find(struct_text)
        struct_name = self.FakeNode(
            "type_identifier", "S", start_byte=struct_start + struct_text.find("S")
        )
        struct_node = self.FakeNode(
            "struct_specifier",
            struct_text,
            start_line=2,
            start_byte=struct_start,
            children=[struct_name],
        )

        var_text = "int v=0;"
        var_start = source.find(var_text)
        decl_name = self.FakeNode(
            "identifier", "v", start_byte=var_start + var_text.find("v")
        )
        init_decl = self.FakeNode(
            "init_declarator",
            "v=0",
            start_byte=var_start + var_text.find("v"),
            children=[decl_name],
        )
        decl_specs = self.FakeNode(
            "declaration_specifiers", "int", start_byte=var_start
        )
        var_decl = self.FakeNode(
            "declaration",
            var_text,
            start_line=3,
            start_byte=var_start,
            children=[init_decl],
            fields={"declaration_specifiers": decl_specs},
        )

        inc_text = "#include <stdio.h>"
        inc = self.FakeNode(
            "preproc_include", inc_text, start_line=0, start_byte=source.find(inc_text)
        )

        root = self.FakeNode("root", source, children=[inc, fn, struct_node, var_decl])
        tree = self.make_tree(root)

        funcs = extractor.extract_functions(tree, source)
        assert isinstance(funcs, list)

        classes = extractor.extract_classes(tree, source)
        assert isinstance(classes, list)

        vars_ = extractor.extract_variables(tree, source)
        assert isinstance(vars_, list)

        imps = extractor.extract_imports(tree, source)
        assert any(i.import_statement.startswith("#include") for i in imps)

    @pytest.mark.asyncio
    async def test_analyze_file_runs_legacy(self) -> None:
        """Test analyze_file runs successfully on example file (legacy test)"""
        from types import SimpleNamespace

        p = CPlugin()
        path = os.path.join("examples", "sample.c")
        ar = SimpleNamespace()

        from tree_sitter_analyzer.models.result import AnalysisResult

        out = await p.analyze_file(path, ar)
        assert isinstance(out, AnalysisResult)


# ---------------------------------------------------------------------------
# Issue #534 — C macro deduplication across #ifdef / #else branches (Scope B)
# ---------------------------------------------------------------------------


class TestCMacroDeduplication:
    """Macros defined identically in both #ifdef and #else branches appear once."""

    def test_macro_not_duplicated_across_ifdef_else(self) -> None:
        """SQUARE and LOG must appear exactly once even when defined in both
        #ifdef and #else branches (Issue #534 Scope B)."""
        import tree_sitter

        p = CPlugin()
        lang = p.get_tree_sitter_language()
        parser = tree_sitter.Parser(lang)
        code = (
            "#include <stdio.h>\n"
            "int add(int a, int b) { return a + b; }\n"
            "#ifdef DEBUG\n"
            "#define SQUARE(x) ((x) * (x))\n"
            "#define LOG(msg) printf(msg)\n"
            "#else\n"
            "#define SQUARE(x) ((x) * (x))\n"
            "#define LOG(msg) printf(msg)\n"
            "#endif\n"
        )
        tree = parser.parse(bytes(code, "utf-8"))
        extractor = p.extractor
        fns = extractor.extract_functions(tree, code)
        macro_names = [f.name for f in fns if f.return_type == "macro"]
        assert macro_names.count("SQUARE") == 1, f"SQUARE duplicated: {macro_names}"
        assert macro_names.count("LOG") == 1, f"LOG duplicated: {macro_names}"
        # Total: 1 real function + 2 macros = 3
        assert len(fns) == 3


class TestMacroRedefinitionSurvives:
    """Codex P2 on #566: same-name dedup must NOT swallow a legitimate
    #undef + #define redefinition outside any shared conditional."""

    CODE = """
#define SQUARE(x) ((x) * (x))
int use1(void) { return SQUARE(2); }
#undef SQUARE
#define SQUARE(x) ((x) + (x))
int use2(void) { return SQUARE(3); }
"""

    def test_both_definitions_extracted(self):
        import tree_sitter
        import tree_sitter_c

        from tree_sitter_analyzer.languages.c_plugin import CElementExtractor

        lang = tree_sitter.Language(tree_sitter_c.language())
        parser = tree_sitter.Parser(lang)
        tree = parser.parse(self.CODE.encode())
        extractor = CElementExtractor()
        functions = extractor.extract_functions(tree, self.CODE)
        squares = [f for f in functions if f.name == "SQUARE"]
        assert len(squares) == 2
        assert len(functions) == 4  # 2 macros + use1 + use2


# ---------------------------------------------------------------------------
# Tests migrated from test_c_plugin_coverage_boost.py
# ---------------------------------------------------------------------------


def _parse_c(plugin, code):
    import tree_sitter

    language = plugin.get_tree_sitter_language()
    parser = tree_sitter.Parser(language)
    return parser.parse(code.encode("utf-8"))


class TestCPluginBehavioral:
    """Concrete behavioral tests for C extraction."""

    @pytest.fixture
    def plugin(self):
        return CPlugin()

    def test_extract_static_function_modifier(self, plugin):
        code = """static void helper(void) {}
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        funcs = elements["functions"]
        assert len(funcs) == 1
        assert "static" in funcs[0].modifiers

    def test_extract_variadic_parameter(self, plugin):
        code = """void debug_print(const char* fmt, ...) {}
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        funcs = elements["functions"]
        assert len(funcs) == 1
        assert "..." in funcs[0].parameters

    def test_extract_union_type(self, plugin):
        code = """union Data {
    int i;
    float f;
};
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        classes = elements["classes"]
        unions = [c for c in classes if c.class_type == "union"]
        assert len(unions) == 1
        assert unions[0].name == "Data"

    def test_extract_enum_type(self, plugin):
        code = """enum Color { RED, GREEN, BLUE };
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        classes = elements["classes"]
        enums = [c for c in classes if c.class_type == "enum"]
        assert len(enums) == 1
        assert enums[0].name == "Color"

    def test_extract_array_field(self, plugin):
        code = """struct Record {
    char name[50];
    int value;
};
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        variables = elements["variables"]
        arr_vars = [v for v in variables if v.variable_type and "[]" in v.variable_type]
        assert len(arr_vars) == 1
        assert arr_vars[0].name == "name"

    def test_extract_pointer_field(self, plugin):
        code = """struct Node {
    int* data;
    struct Node* next;
};
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        variables = elements["variables"]
        ptr_vars = [v for v in variables if v.variable_type and "*" in v.variable_type]
        assert len(ptr_vars) == 2

    def test_extract_global_pointer_variable(self, plugin):
        code = """int *ptr;
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        variables = elements["variables"]
        assert len(variables) == 1
        assert variables[0].name == "ptr"

    def test_extract_static_variable(self, plugin):
        code = """static int counter = 0;
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        variables = elements["variables"]
        assert len(variables) == 1
        assert variables[0].is_static is True
        assert variables[0].visibility == "private"

    def test_extract_macro_constant(self, plugin):
        code = """#define MAX_SIZE 100
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        variables = elements["variables"]
        macros = [v for v in variables if v.variable_type == "macro"]
        assert len(macros) == 1
        assert macros[0].name == "MAX_SIZE"
        assert macros[0].is_constant is True

    def test_extract_macro_function(self, plugin):
        code = """#define SQUARE(x) ((x)*(x))
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        funcs = elements["functions"]
        macro_fns = [f for f in funcs if "macro" in f.modifiers]
        assert len(macro_fns) == 1
        assert macro_fns[0].name == "SQUARE"

    def test_extract_macro_function_with_variadic(self, plugin):
        code = """#define LOG(fmt, ...) printf(fmt, __VA_ARGS__)
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        funcs = elements["functions"]
        macro_fns = [f for f in funcs if "macro" in f.modifiers]
        assert len(macro_fns) == 1
        assert macro_fns[0].name == "LOG"

    def test_extract_system_and_local_includes(self, plugin):
        code = """#include <stdio.h>
#include "myheader.h"
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        imports = elements["imports"]
        assert len(imports) == 2
        names = [imp.name for imp in imports]
        assert "stdio.h" in names
        assert "myheader.h" in names

    def test_extract_doxygen_comment(self, plugin):
        code = """/** Calculate area. */
int area(int w) { return w * w; }
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        funcs = elements["functions"]
        assert len(funcs) == 1
        assert funcs[0].docstring is not None
        assert "Calculate area" in funcs[0].docstring

    def test_extract_elements_with_none_tree(self, plugin):
        elements = plugin.extract_elements(None, "int x;")
        assert elements == {
            "functions": [],
            "classes": [],
            "variables": [],
            "imports": [],
        }

    def test_traverse_none_root(self):
        extractor = CElementExtractor()
        results = []
        extractor._traverse_and_extract_iterative(None, {}, results, "test")
        assert results == []

    def test_count_tree_nodes(self, plugin):
        code = """int x;
void f(void) {}
"""
        tree = _parse_c(plugin, code)
        count = plugin._count_tree_nodes(tree.root_node)
        assert count == 17

    def test_count_tree_nodes_none(self, plugin):
        assert plugin._count_tree_nodes(None) == 0

    def test_get_tree_sitter_language_cached(self, plugin):
        lang1 = plugin.get_tree_sitter_language()
        assert lang1 is not None
        lang2 = plugin.get_tree_sitter_language()
        assert lang2 is lang1

    def test_extract_function_with_for_loop_complexity(self, plugin):
        code = """int sum(int n) {
    int s = 0;
    for (int i = 0; i < n; i++) { s += i; }
    if (s > 0) { return s; }
    return 0;
}
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        funcs = elements["functions"]
        assert len(funcs) == 1
        assert funcs[0].complexity_score == 3

    def test_extract_function_with_switch_complexity(self, plugin):
        code = """int classify(int x) {
    switch(x) {
        case 1: return 10;
        case 2: return 20;
        default: return 0;
    }
}
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        funcs = elements["functions"]
        assert len(funcs) == 1
        # A switch counts once (construct-once convention); cases are not summed.
        assert funcs[0].complexity_score == 2

    def test_extract_const_function_qualifier(self, plugin):
        code = """const int get_val(void) { return 42; }
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        funcs = elements["functions"]
        assert len(funcs) == 1
        assert "const" in funcs[0].modifiers

    def test_extractor_init_state(self):
        ext = CElementExtractor()
        assert ext.current_file == ""
        assert ext.source_code == ""
        assert ext._file_encoding is None

    def test_plugin_properties(self, plugin):
        assert plugin.get_language_name() == "c"
        assert ".c" in plugin.get_file_extensions()
        assert ".h" in plugin.get_file_extensions()
        assert isinstance(plugin.create_extractor(), CElementExtractor)

    def test_extract_local_include_regex_fallback(self):
        extractor = CElementExtractor()
        code = '#include "utils.h"\n#include "helpers.h"\n'
        imports = extractor._extract_includes_fallback(code)
        assert len(imports) == 2
        assert imports[0].name == "utils.h"
        assert imports[1].name == "helpers.h"

    def test_extract_system_include_regex_fallback(self):
        extractor = CElementExtractor()
        code = "#include <stdlib.h>\n#include <string.h>\n"
        imports = extractor._extract_includes_fallback(code)
        assert len(imports) == 2
        assert imports[0].name == "stdlib.h"

    def test_extract_macros_inside_ifdef_branches(self, plugin):
        """Regression: macros defined inside #ifdef / #else / #elif
        branches must still be extracted. The traversal helper previously
        treated preproc_ifdef / preproc_if / preproc_else / preproc_elif
        as non-container nodes and stopped descending.
        """
        code = """
#define BASE 1

#ifdef DEBUG
#define LOG(msg) printf("[DEBUG] %s\\n", msg)
#else
#define LOG(msg)
#endif

#ifndef GUARD
#define GUARD_VALUE 42
#endif

#if defined(FAST)
#define MODE 1
#elif defined(SLOW)
#define MODE 0
#endif
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        variables = elements["variables"]
        funcs = elements["functions"]

        var_names = {v.name for v in variables}
        fn_names = {f.name for f in funcs if "macro" in f.modifiers}

        assert "BASE" in var_names
        assert "GUARD_VALUE" in var_names, "#ifndef branch was skipped"
        assert "MODE" in var_names, "#if/#elif branches were skipped"
        assert "LOG" in fn_names, "#ifdef/#else macro_function branch was skipped"
        log_macros = [f for f in funcs if f.name == "LOG"]
        assert len(log_macros) == 1, (
            f"expected exactly one LOG definition (deduplicated), got {len(log_macros)}"
        )

    def test_extract_field_with_init_declarator(self, plugin):
        code = """struct Config {
    int timeout = 30;
};
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        variables = elements["variables"]
        timeout_vars = [v for v in variables if v.name == "timeout"]
        assert len(timeout_vars) == 1

    def test_extract_variable_in_struct_body_not_private(self, plugin):
        code = """struct S { int x; };
"""
        tree = _parse_c(plugin, code)
        elements = plugin.extract_elements(tree, code)
        variables = elements["variables"]
        non_field = [v for v in variables if v.name == "x" and v.visibility != "public"]
        assert len(non_field) == 0
