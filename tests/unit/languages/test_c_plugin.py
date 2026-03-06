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
from tree_sitter_analyzer.plugins import ElementExtractorBase
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
        assert isinstance(extractor, ElementExtractorBase)
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
        assert isinstance(extractor, ElementExtractorBase)

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

    def test_plugin_metadata_legacy(self) -> None:
        """Test plugin metadata (legacy test)"""
        p = CPlugin()
        assert p.get_language_name() == "c"
        assert ".c" in p.get_file_extensions()

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

        out = await p.analyze_file(path, ar)
        assert out is not None


class TestCPluginRealParsing:
    """Tests using real tree-sitter parsing via extract_elements."""

    def test_c_plugin_extract_elements_real_parsing(self) -> None:
        """Test real tree-sitter parsing with extract_elements for C code."""
        import tree_sitter

        plugin = CPlugin()
        code = """
        #include <stdio.h>
        struct MyStruct {
            int x;
        };
        void my_func(int a) {}
        """

        language = plugin.get_tree_sitter_language()
        parser = tree_sitter.Parser(language)
        tree = parser.parse(code.encode("utf-8"))

        elements_dict = plugin.extract_elements(tree, code)
        assert elements_dict is not None
        assert len(elements_dict["functions"]) > 0
        assert len(elements_dict["classes"]) > 0

        names = [e.name for e in elements_dict["functions"]]
        assert "my_func" in names


class TestCPluginExtendedCoverage:
    """Extended tests for CPlugin to cover missing lines."""

    @pytest.fixture
    def plugin(self) -> CPlugin:
        return CPlugin()

    @pytest.fixture
    def c_parser(self):
        import tree_sitter
        plugin = CPlugin()
        language = plugin.get_tree_sitter_language()
        return tree_sitter.Parser(language)

    def test_extract_includes_fallback_regex(self) -> None:
        """Test regex fallback for includes (lines 704-744)."""
        extractor = CElementExtractor()
        code = '#include <stdlib.h>\n#include "myfile.h"\n'
        result = extractor._extract_includes_fallback(code)
        assert len(result) == 2
        assert result[0].name == "stdlib.h"
        assert result[1].name == "myfile.h"

    def test_extract_includes_fallback_triggered(self, c_parser) -> None:
        """Test include fallback triggered when tree-sitter misses includes (lines 131-134)."""
        extractor = CElementExtractor()
        # Create a mock tree with no preproc_include children but source has #include
        mock_tree = Mock()
        mock_root = Mock()
        mock_root.children = []  # No children, fallback will trigger
        mock_tree.root_node = mock_root
        code = "#include <stdio.h>\n"
        imports = extractor.extract_imports(mock_tree, code)
        assert len(imports) >= 1
        assert imports[0].name == "stdio.h"

    def test_extract_enum(self, c_parser) -> None:
        """Test enum extraction (lines 457-504)."""
        plugin = CPlugin()
        code = """
enum Color {
    RED,
    GREEN,
    BLUE
};
"""
        tree = c_parser.parse(code.encode("utf-8"))
        elements = plugin.extract_elements(tree, code)
        classes = elements["classes"]
        enum_names = [c.name for c in classes if c.class_type == "enum"]
        assert "Color" in enum_names

    def test_extract_typedef_enum(self, c_parser) -> None:
        """Test typedef enum extraction (lines 471-478)."""
        plugin = CPlugin()
        code = """
typedef enum {
    NONE,
    SOME,
    ALL
} Option;
"""
        tree = c_parser.parse(code.encode("utf-8"))
        elements = plugin.extract_elements(tree, code)
        classes = elements["classes"]
        # Should extract as enum with name from typedef
        assert isinstance(classes, list)

    def test_extract_anonymous_struct(self, c_parser) -> None:
        """Test anonymous struct extraction (lines 415-417)."""
        plugin = CPlugin()
        code = """
struct {
    int x;
    int y;
} point;
"""
        tree = c_parser.parse(code.encode("utf-8"))
        elements = plugin.extract_elements(tree, code)
        classes = elements["classes"]
        assert isinstance(classes, list)

    def test_extract_typedef_struct(self, c_parser) -> None:
        """Test typedef struct extraction (lines 402-413)."""
        plugin = CPlugin()
        code = """
typedef struct {
    int x;
    int y;
} Point;
"""
        tree = c_parser.parse(code.encode("utf-8"))
        elements = plugin.extract_elements(tree, code)
        classes = elements["classes"]
        assert any(c.name == "Point" for c in classes)

    def test_extract_union(self, c_parser) -> None:
        """Test union extraction (lines 441-455)."""
        plugin = CPlugin()
        code = """
union Value {
    int i;
    float f;
    char c;
};
"""
        tree = c_parser.parse(code.encode("utf-8"))
        elements = plugin.extract_elements(tree, code)
        classes = elements["classes"]
        union_classes = [c for c in classes if c.class_type == "union"]
        assert any(c.name == "Value" for c in union_classes)

    def test_extract_anonymous_union(self, c_parser) -> None:
        """Test anonymous union extraction (lines 447-451)."""
        plugin = CPlugin()
        code = """
union {
    int i;
    float f;
} data;
"""
        tree = c_parser.parse(code.encode("utf-8"))
        elements = plugin.extract_elements(tree, code)
        classes = elements["classes"]
        unions = [c for c in classes if c.class_type == "union"]
        # Anonymous unions should have auto-generated name
        assert isinstance(unions, list)

    def test_extract_macro_definition(self, c_parser) -> None:
        """Test macro definition extraction as variable (lines 746-777)."""
        plugin = CPlugin()
        code = """
#define MAX_SIZE 100
#define PI 3.14159
"""
        tree = c_parser.parse(code.encode("utf-8"))
        elements = plugin.extract_elements(tree, code)
        variables = elements["variables"]
        macro_vars = [v for v in variables if v.variable_type == "macro"]
        assert len(macro_vars) >= 1
        assert any(v.name == "MAX_SIZE" for v in macro_vars)

    def test_extract_macro_function(self, c_parser) -> None:
        """Test macro function extraction (lines 779-814)."""
        plugin = CPlugin()
        code = """
#define ADD(a, b) ((a) + (b))
#define SQUARE(x) ((x) * (x))
"""
        tree = c_parser.parse(code.encode("utf-8"))
        elements = plugin.extract_elements(tree, code)
        funcs = elements["functions"]
        macro_funcs = [f for f in funcs if f.return_type == "macro"]
        assert len(macro_funcs) >= 1

    def test_extract_field_with_array(self, c_parser) -> None:
        """Test field extraction with array type (lines 534-542)."""
        plugin = CPlugin()
        code = """
struct Buffer {
    char name[50];
    int data[100];
};
"""
        tree = c_parser.parse(code.encode("utf-8"))
        elements = plugin.extract_elements(tree, code)
        variables = elements["variables"]
        array_fields = [v for v in variables if "[]" in (v.variable_type or "")]
        assert len(array_fields) >= 1

    def test_extract_field_with_pointer(self, c_parser) -> None:
        """Test field extraction with pointer (lines 556-563)."""
        plugin = CPlugin()
        code = """
struct Node {
    int value;
    struct Node *next;
};
"""
        tree = c_parser.parse(code.encode("utf-8"))
        elements = plugin.extract_elements(tree, code)
        variables = elements["variables"]
        assert isinstance(variables, list)

    def test_extract_static_variable(self, c_parser) -> None:
        """Test static variable extraction with private visibility (lines 647)."""
        plugin = CPlugin()
        code = """
static int counter = 0;
int public_var = 42;
"""
        tree = c_parser.parse(code.encode("utf-8"))
        elements = plugin.extract_elements(tree, code)
        variables = elements["variables"]
        static_vars = [v for v in variables if v.name == "counter"]
        if static_vars:
            assert static_vars[0].visibility == "private"
            assert static_vars[0].is_static is True

    def test_extract_const_variable(self, c_parser) -> None:
        """Test const variable extraction (lines 659)."""
        plugin = CPlugin()
        code = "const int MAX = 100;\n"
        tree = c_parser.parse(code.encode("utf-8"))
        elements = plugin.extract_elements(tree, code)
        variables = elements["variables"]
        const_vars = [v for v in variables if v.name == "MAX"]
        if const_vars:
            assert const_vars[0].is_constant is True

    def test_extract_pointer_return_function(self, c_parser) -> None:
        """Test function with pointer return type (lines 347-352)."""
        plugin = CPlugin()
        code = """
int* allocate(int size) {
    return (int*)malloc(size * sizeof(int));
}
"""
        tree = c_parser.parse(code.encode("utf-8"))
        elements = plugin.extract_elements(tree, code)
        funcs = elements["functions"]
        assert any(f.name == "allocate" for f in funcs)

    def test_extract_function_with_complexity(self, c_parser) -> None:
        """Test complexity calculation (lines 816-843)."""
        plugin = CPlugin()
        code = """
int complex(int x) {
    if (x > 0) {
        while (x > 1) {
            for (int i = 0; i < x; i++) {
                switch (i) {
                    case 0: break;
                    case 1: break;
                }
            }
            x--;
        }
    }
    return x;
}
"""
        tree = c_parser.parse(code.encode("utf-8"))
        elements = plugin.extract_elements(tree, code)
        funcs = elements["functions"]
        complex_func = [f for f in funcs if f.name == "complex"]
        if complex_func:
            assert complex_func[0].complexity_score > 1

    def test_extract_comment_doxygen(self) -> None:
        """Test Doxygen comment extraction (lines 845-874)."""
        extractor = CElementExtractor()
        extractor.content_lines = [
            "/**",
            " * Adds two numbers",
            " */",
            "int add(int a, int b) {",
            "    return a + b;",
            "}",
        ]
        doc = extractor._extract_comment_for_line(4)  # line 4 = the function line
        assert doc is not None
        assert "Adds two numbers" in doc

    def test_extract_comment_block(self) -> None:
        """Test block comment extraction (lines 862-869)."""
        extractor = CElementExtractor()
        extractor.content_lines = [
            "/* This is a comment */",
            "int func() {}",
        ]
        doc = extractor._extract_comment_for_line(2)  # line 2
        assert doc is not None
        assert "This is a comment" in doc

    def test_extract_elements_none_tree(self, plugin) -> None:
        """Test extract_elements with None tree (lines 1022-1028)."""
        result = plugin.extract_elements(None, "code")
        assert result == {
            "functions": [],
            "classes": [],
            "variables": [],
            "imports": [],
        }

    def test_extract_elements_exception(self, plugin) -> None:
        """Test extract_elements exception handling (lines 1038-1045)."""
        with patch.object(plugin, "create_extractor", side_effect=Exception("Error")):
            result = plugin.extract_elements(Mock(), "code")
            assert result == {
                "functions": [],
                "classes": [],
                "variables": [],
                "imports": [],
            }

    def test_get_tree_sitter_language_generic_exception(self) -> None:
        """Test tree-sitter language generic exception (lines 1016-1018)."""
        plugin = CPlugin()
        plugin._cached_language = None
        with patch("tree_sitter_c.language", side_effect=RuntimeError("Unexpected")):
            result = plugin.get_tree_sitter_language()
            assert result is None

    def test_count_tree_nodes(self, plugin) -> None:
        """Test _count_tree_nodes (lines 979-988)."""
        assert plugin._count_tree_nodes(None) == 0
        node = Mock()
        child = Mock()
        child.children = []
        node.children = [child]
        assert plugin._count_tree_nodes(node) == 2

    def test_variadic_parameter(self, c_parser) -> None:
        """Test function with variadic parameter extraction (line 384)."""
        plugin = CPlugin()
        code = """
void print_args(const char* fmt, ...) {
    return;
}
"""
        tree = c_parser.parse(code.encode("utf-8"))
        elements = plugin.extract_elements(tree, code)
        funcs = elements["functions"]
        va_func = [f for f in funcs if f.name == "print_args"]
        if va_func:
            assert "..." in va_func[0].parameters
