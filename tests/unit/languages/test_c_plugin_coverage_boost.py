import pytest
import tree_sitter

from tree_sitter_analyzer.languages.c_plugin import CElementExtractor, CPlugin


@pytest.fixture
def plugin():
    return CPlugin()


def _parse(plugin, code):
    language = plugin.get_tree_sitter_language()
    parser = tree_sitter.Parser(language)
    return parser.parse(code.encode("utf-8"))


def test_c_plugin_basic(plugin):
    code = """
    #include <stdio.h>
    struct MyStruct {
        int x;
    };
    void my_func(int a) {}
    """
    tree = _parse(plugin, code)
    elements_dict = plugin.extract_elements(tree, code)
    assert elements_dict is not None
    assert len(elements_dict["functions"]) > 0
    assert len(elements_dict["classes"]) > 0

    names = [e.name for e in elements_dict["functions"]]
    assert "my_func" in names


def test_extract_pointer_return_function(plugin):
    code = """int* get_ptr(void) { return NULL; }
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    fnames = [f.name for f in elements["functions"]]
    assert "get_ptr" in fnames


def test_extract_static_function(plugin):
    code = """static void helper(void) {}
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    funcs = elements["functions"]
    assert len(funcs) >= 1
    f = funcs[0]
    assert "static" in f.modifiers


def test_extract_variadic_parameter(plugin):
    code = """void debug_print(const char* fmt, ...) {}
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    funcs = elements["functions"]
    assert len(funcs) >= 1
    assert "..." in funcs[0].parameters


def test_extract_union(plugin):
    code = """union Data {
        int i;
        float f;
    };
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    classes = elements["classes"]
    unions = [c for c in classes if c.class_type == "union"]
    assert len(unions) >= 1
    assert unions[0].name == "Data"


def test_extract_enum(plugin):
    code = """enum Color { RED, GREEN, BLUE };
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    classes = elements["classes"]
    enums = [c for c in classes if c.class_type == "enum"]
    assert len(enums) >= 1
    assert enums[0].name == "Color"


def test_extract_typedef_struct(plugin):
    code = """typedef struct { int x; int y; } Point;
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    classes = elements["classes"]
    assert len(classes) >= 1


def test_extract_typedef_enum(plugin):
    code = """typedef enum { A, B, C } MyEnum;
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    classes = elements["classes"]
    enums = [c for c in classes if c.class_type == "enum"]
    assert len(enums) >= 1


def test_extract_array_field(plugin):
    code = """struct Record {
        char name[50];
        int value;
    };
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    variables = elements["variables"]
    arr_vars = [v for v in variables if v.variable_type and "[]" in v.variable_type]
    assert len(arr_vars) >= 1
    assert arr_vars[0].name == "name"


def test_extract_pointer_field(plugin):
    code = """struct Node {
        int* data;
        struct Node* next;
    };
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    variables = elements["variables"]
    ptr_vars = [v for v in variables if v.variable_type and "*" in v.variable_type]
    assert len(ptr_vars) >= 1


def test_extract_global_pointer_variable(plugin):
    code = """int* ptr = NULL;
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    variables = elements["variables"]
    assert len(variables) >= 1
    assert "*" in variables[0].variable_type


def test_extract_static_variable(plugin):
    code = """static int counter = 0;
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    variables = elements["variables"]
    assert len(variables) >= 1
    assert variables[0].is_static is True
    assert variables[0].visibility == "private"


def test_extract_macro_constant(plugin):
    code = """#define MAX_SIZE 100
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    variables = elements["variables"]
    macros = [v for v in variables if v.variable_type == "macro"]
    assert len(macros) >= 1
    assert macros[0].name == "MAX_SIZE"
    assert macros[0].is_constant is True


def test_extract_macro_function(plugin):
    code = """#define SQUARE(x) ((x)*(x))
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    funcs = elements["functions"]
    macro_fns = [f for f in funcs if "macro" in f.modifiers]
    assert len(macro_fns) >= 1
    assert macro_fns[0].name == "SQUARE"


def test_extract_system_and_local_includes(plugin):
    code = """#include <stdio.h>
#include "myheader.h"
"""
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    imports = elements["imports"]
    assert len(imports) >= 2
    names = [imp.name for imp in imports]
    assert "stdio.h" in names
    assert "myheader.h" in names


def test_extract_const_field(plugin):
    code = """struct Config {
        const int max_retries;
    };
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    variables = elements["variables"]
    const_vars = [v for v in variables if v.is_constant]
    assert len(const_vars) >= 1


def test_extract_doxygen_comment(plugin):
    code = """/**
 * Calculate area.
 * @param w width
 * @return area
 */
int area(int w) { return w * w; }
"""
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    funcs = elements["functions"]
    assert len(funcs) >= 1
    assert funcs[0].docstring is not None
    assert "Calculate area" in funcs[0].docstring


def test_extract_block_comment(plugin):
    code = """/* This is a helper */
void helper(void) {}
"""
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    funcs = elements["functions"]
    assert len(funcs) >= 1
    assert funcs[0].docstring is not None


def test_analyze_file_with_real_file(plugin, tmp_path):
    c_file = tmp_path / "test.c"
    c_file.write_text("""#include <stdio.h>
int main(void) { printf("hello"); return 0; }
""")
    import asyncio

    from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

    request = AnalysisRequest(file_path=str(c_file))
    result = asyncio.run(plugin.analyze_file(str(c_file), request))
    assert result.language == "c"
    assert result.success is not False


def test_extract_elements_with_none_tree(plugin):
    elements = plugin.extract_elements(None, "int x;")
    assert elements == {"functions": [], "classes": [], "variables": [], "imports": []}


def test_traverse_max_depth(plugin):
    extractor = CElementExtractor()
    extractor.source_code = "x"
    extractor.content_lines = ["x"]

    class FakeNode:
        def __init__(self, depth=0):
            self.type = "translation_unit"
            self.children = [FakeNode(depth + 1)] if depth < 52 else []
            self.start_byte = 0
            self.end_byte = 1

    results = []
    extractor._traverse_and_extract_iterative(
        FakeNode(), {"translation_unit": lambda n: None}, results, "test"
    )
    assert isinstance(results, list)
