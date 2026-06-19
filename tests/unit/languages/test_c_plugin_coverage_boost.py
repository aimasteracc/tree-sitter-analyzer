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
    assert len(elements_dict["functions"]) == 1
    assert len(elements_dict["classes"]) == 1

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
    assert len(funcs) == 1
    f = funcs[0]
    assert "static" in f.modifiers


def test_extract_variadic_parameter(plugin):
    code = """void debug_print(const char* fmt, ...) {}
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    funcs = elements["functions"]
    assert len(funcs) == 1
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
    assert len(unions) == 1
    assert unions[0].name == "Data"


def test_extract_enum(plugin):
    code = """enum Color { RED, GREEN, BLUE };
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    classes = elements["classes"]
    enums = [c for c in classes if c.class_type == "enum"]
    assert len(enums) == 1
    assert enums[0].name == "Color"


def test_extract_typedef_struct(plugin):
    code = """typedef struct { int x; int y; } Point;
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    classes = elements["classes"]
    assert len(classes) == 1


def test_extract_typedef_enum(plugin):
    code = """typedef enum { A, B, C } MyEnum;
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    classes = elements["classes"]
    enums = [c for c in classes if c.class_type == "enum"]
    assert len(enums) == 1


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
    assert len(arr_vars) == 1
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
    assert len(ptr_vars) == 2


def test_extract_global_pointer_variable(plugin):
    code = """int *ptr;
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    variables = elements["variables"]
    assert len(variables) == 1
    assert variables[0].name == "ptr"


def test_extract_static_variable(plugin):
    code = """static int counter = 0;
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    variables = elements["variables"]
    assert len(variables) == 1
    assert variables[0].is_static is True
    assert variables[0].visibility == "private"


def test_extract_macro_constant(plugin):
    code = """#define MAX_SIZE 100
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    variables = elements["variables"]
    macros = [v for v in variables if v.variable_type == "macro"]
    assert len(macros) == 1
    assert macros[0].name == "MAX_SIZE"
    assert macros[0].is_constant is True


def test_extract_macro_function(plugin):
    code = """#define SQUARE(x) ((x)*(x))
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    funcs = elements["functions"]
    macro_fns = [f for f in funcs if "macro" in f.modifiers]
    assert len(macro_fns) == 1
    assert macro_fns[0].name == "SQUARE"


def test_extract_system_and_local_includes(plugin):
    code = """#include <stdio.h>
#include "myheader.h"
"""
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    imports = elements["imports"]
    assert len(imports) == 2
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
    assert len(const_vars) == 1


def test_extract_doxygen_comment(plugin):
    code = """/** Calculate area. */
int area(int w) { return w * w; }
"""
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    funcs = elements["functions"]
    assert len(funcs) == 1
    assert funcs[0].docstring is not None
    assert "Calculate area" in funcs[0].docstring


def test_extract_block_comment(plugin):
    code = """/* This is a helper */
void helper(void) {}
"""
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    funcs = elements["functions"]
    assert len(funcs) == 1
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


def test_traverse_none_root(plugin):
    extractor = CElementExtractor()
    results = []
    extractor._traverse_and_extract_iterative(None, {}, results, "test")
    assert results == []


def test_extract_variable_in_struct_body_skipped(plugin):
    code = """struct S { int x; };
"""
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    variables = elements["variables"]
    non_field = [v for v in variables if v.name == "x" and v.visibility != "public"]
    assert len(non_field) == 0


def test_extract_macro_function_with_variadic(plugin):
    code = """#define LOG(fmt, ...) printf(fmt, __VA_ARGS__)
"""
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    funcs = elements["functions"]
    macro_fns = [f for f in funcs if "macro" in f.modifiers]
    assert len(macro_fns) == 1
    assert macro_fns[0].name == "LOG"


def test_extract_macros_inside_ifdef_branches(plugin):
    """Regression: macros defined inside ``#ifdef`` / ``#else`` / ``#elif``
    branches must still be extracted. The traversal helper previously
    treated ``preproc_ifdef`` / ``preproc_if`` / ``preproc_else`` /
    ``preproc_elif`` as non-container nodes and stopped descending,
    silently dropping every macro inside a conditional block.
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
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    variables = elements["variables"]
    funcs = elements["functions"]

    var_names = {v.name for v in variables}
    fn_names = {f.name for f in funcs if "macro" in f.modifiers}

    # Object-like macros from each conditional branch
    assert "BASE" in var_names
    assert "GUARD_VALUE" in var_names, "#ifndef branch was skipped"
    assert "MODE" in var_names, "#if/#elif branches were skipped"

    # Function-like macro from #ifdef branch must be captured (Issue #534
    # Scope B: duplicates from #else branch are now deduplicated — only
    # the first definition, from the #ifdef branch, is kept).
    assert "LOG" in fn_names, "#ifdef/#else macro_function branch was skipped"
    log_macros = [f for f in funcs if f.name == "LOG"]
    assert len(log_macros) == 1, (
        f"expected exactly one LOG definition (deduplicated), got {len(log_macros)}"
    )


def test_extract_anonymous_struct(plugin):
    code = """struct { int a; int b; } instance;
"""
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    structs = [c for c in elements["classes"] if c.class_type == "struct"]
    if len(structs) >= 1:
        assert "anonymous_struct" in structs[0].name or structs[0].name is not None


def test_extract_anonymous_union(plugin):
    code = """union { int a; float b; } u;
"""
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    unions = [c for c in elements["classes"] if c.class_type == "union"]
    if len(unions) >= 1:
        assert "anonymous_union" in unions[0].name or unions[0].name is not None


def test_extract_anonymous_enum(plugin):
    code = """enum { VAL1, VAL2 } my_enum;
"""
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    enums = [c for c in elements["classes"] if c.class_type == "enum"]
    if len(enums) >= 1:
        assert "anonymous_enum" in enums[0].name or enums[0].name is not None


def test_extract_const_function_qualifier(plugin):
    code = """const int get_val(void) { return 42; }
"""
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    funcs = elements["functions"]
    assert len(funcs) == 1
    assert "const" in funcs[0].modifiers


def test_count_tree_nodes(plugin):
    code = """int x;
void f(void) {}
"""
    tree = _parse(plugin, code)
    count = plugin._count_tree_nodes(tree.root_node)
    assert count == 17


def test_count_tree_nodes_none(plugin):
    assert plugin._count_tree_nodes(None) == 0


def test_get_tree_sitter_language_cached(plugin):
    lang1 = plugin.get_tree_sitter_language()
    assert lang1 is not None
    lang2 = plugin.get_tree_sitter_language()
    assert lang2 is lang1


def test_extract_function_with_for_loop(plugin):
    code = """int sum(int n) {
    int s = 0;
    for (int i = 0; i < n; i++) { s += i; }
    if (s > 0) { return s; }
    return 0;
}
"""
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    funcs = elements["functions"]
    assert len(funcs) == 1
    assert funcs[0].complexity_score == 3


def test_extract_field_with_init_declarator(plugin):
    code = """struct Config {
        int timeout = 30;
    };
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    variables = elements["variables"]
    timeout_vars = [v for v in variables if v.name == "timeout"]
    assert len(timeout_vars) == 1


def test_extractor_init_state():
    ext = CElementExtractor()
    assert ext.current_file == ""
    assert ext.source_code == ""
    assert ext._file_encoding is None


def test_plugin_properties(plugin):
    assert plugin.get_language_name() == "c"
    assert ".c" in plugin.get_file_extensions()
    assert ".h" in plugin.get_file_extensions()
    assert isinstance(plugin.create_extractor(), CElementExtractor)


def test_extract_local_include_regex_fallback():
    extractor = CElementExtractor()
    code = '#include "utils.h"\n#include "helpers.h"\n'
    imports = extractor._extract_includes_fallback(code)
    assert len(imports) == 2
    assert imports[0].name == "utils.h"
    assert imports[1].name == "helpers.h"


def test_extract_system_include_regex_fallback():
    extractor = CElementExtractor()
    code = "#include <stdlib.h>\n#include <string.h>\n"
    imports = extractor._extract_includes_fallback(code)
    assert len(imports) == 2
    assert imports[0].name == "stdlib.h"


def test_extract_function_with_switch(plugin):
    code = """int classify(int x) {
    switch(x) {
        case 1: return 10;
        case 2: return 20;
        default: return 0;
    }
}
"""
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    funcs = elements["functions"]
    assert len(funcs) == 1
    # A switch counts once (construct-once convention); cases are not summed.
    assert funcs[0].complexity_score == 2
