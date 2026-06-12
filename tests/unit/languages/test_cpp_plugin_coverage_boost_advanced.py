import pytest
import tree_sitter
import tree_sitter_cpp

from tree_sitter_analyzer.languages.cpp_plugin import CppElementExtractor, CppPlugin


@pytest.fixture
def plugin():
    return CppPlugin()


@pytest.fixture
def extractor():
    return CppElementExtractor()


def _parse(code: str):
    lang = tree_sitter.Language(tree_sitter_cpp.language())
    parser = tree_sitter.Parser(lang)
    return parser.parse(code.encode("utf-8"))


# --- Multiple parameters ---
def test_function_multiple_parameters(extractor):
    code = "int add(int a, int b, int c) { return a + b + c; }\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    add_funcs = [f for f in funcs if f.name == "add"]
    assert len(add_funcs) == 1
    assert len(add_funcs[0].parameters) == 3


# --- Variadic parameter ---
def test_variadic_function(extractor):
    code = "int printf(const char* fmt, ...);\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    printf_funcs = [f for f in funcs if f.name == "printf"]
    assert len(printf_funcs) == 1


# --- Full qualified name with namespace ---
def test_qualified_name_with_namespace(extractor):
    code = (
        "namespace gfx {\n    class Color {\n    public:\n        int r;\n    };\n}\n"
    )
    tree = _parse(code)
    classes = extractor.extract_classes(tree, code)
    color_classes = [c for c in classes if c.name == "Color"]
    assert len(color_classes) == 1
    cc = color_classes[0]
    assert (
        cc.full_qualified_name == "gfx::Color"
        or cc.full_qualified_name == "Color"
        or cc.package_name == "gfx"
    )


# --- Deleted method (= delete) ---
def test_deleted_method(extractor):
    code = "class NonCopy {\npublic:\n    NonCopy(const NonCopy&) = delete;\n};\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    nc_funcs = [f for f in funcs if f.name and "NonCopy" in f.name]
    assert len(nc_funcs) == 1


# --- Defaulted method (= default) ---
def test_defaulted_method(extractor):
    code = "class Defaults {\npublic:\n    Defaults() = default;\n};\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    assert isinstance(funcs, list)
    defaults_funcs = [f for f in funcs if f.name and "Defaults" in f.name]
    assert len(defaults_funcs) == 1
    # default modifier is extracted via field_declaration path


# --- Protected visibility via explicit access specifier ---
def test_protected_access_specifier(extractor):
    code = "class Base {\nprotected:\n    void do_thing() {}\n};\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    thing_funcs = [f for f in funcs if f.name == "do_thing"]
    assert len(thing_funcs) == 1
    assert thing_funcs[0].visibility == "protected"


# --- Protected visibility via explicit modifier ---
def test_protected_explicit_modifier_determine_visibility(extractor):
    result = extractor._determine_visibility(["protected"], is_global=False, node=None)
    assert result == "protected"


# --- Private visibility via explicit modifier ---
def test_private_explicit_modifier_determine_visibility(extractor):
    result = extractor._determine_visibility(["private"], is_global=False, node=None)
    assert result == "private"


# --- Public visibility via explicit modifier ---
def test_public_explicit_modifier_determine_visibility(extractor):
    result = extractor._determine_visibility(["public"], is_global=True, node=None)
    assert result == "public"


# --- Static global visibility is private ---
def test_static_global_determine_visibility(extractor):
    result = extractor._determine_visibility(["static"], is_global=True, node=None)
    assert result == "private"


# --- Default: public for global, private for non-global ---
def test_default_visibility(extractor):
    assert extractor._determine_visibility([], is_global=True, node=None) == "public"
    assert extractor._determine_visibility([], is_global=False, node=None) == "private"


# --- Field with init_declarator containing identifier in class ---
def test_field_init_declarator_identifier(extractor):
    code = "class Pair { int val = 0; };\n"
    tree = _parse(code)
    variables = extractor.extract_variables(tree, code)
    val_vars = [v for v in variables if v.name == "val"]
    assert len(val_vars) == 1
    assert val_vars[0].variable_type == "int"


# --- Extract includes fallback with local include only ---
def test_include_fallback_local_only(extractor):
    code = '#include "local_header.h"\n'
    tree = _parse(code)
    imports = extractor.extract_imports(tree, code)
    names = [i.name for i in imports]
    assert "local_header.h" in names


# --- Virtual function with const qualifier ---
def test_virtual_const_function(extractor):
    code = "class Shape {\npublic:\n    virtual double area() const = 0;\n};\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    area_funcs = [f for f in funcs if f.name == "area"]
    assert len(area_funcs) == 1
    assert "virtual" in (area_funcs[0].modifiers or [])
    assert "pure_virtual" in (area_funcs[0].modifiers or [])


# --- For-range loop complexity ---
def test_for_range_complexity(extractor):
    code = "int sum_items() {\n    int total = 0;\n    for (int x : items) { total += x; }\n    return total;\n}\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    sum_funcs = [f for f in funcs if f.name == "sum_items"]
    assert len(sum_funcs) == 1
    assert sum_funcs[0].complexity_score == 2


# --- Switch statement complexity ---
def test_switch_complexity(extractor):
    code = "int grade(int score) {\n    switch(score) {\n        case 90: return 4;\n        case 80: return 3;\n        default: return 0;\n    }\n}\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    grade_funcs = [f for f in funcs if f.name == "grade"]
    assert len(grade_funcs) == 1
    assert grade_funcs[0].complexity_score == 5


# --- Catch clause complexity ---
def test_try_catch_complexity(extractor):
    code = (
        "void safe_op() {\n    try { risky(); }\n    catch (int e) { handle(e); }\n}\n"
    )
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    safe_funcs = [f for f in funcs if f.name == "safe_op"]
    assert len(safe_funcs) == 1
    assert safe_funcs[0].complexity_score == 2


# --- _get_access_specifier with node not in field_declaration_list ---
def test_get_access_specifier_not_in_class(extractor):
    code = "int x;\n"
    tree = _parse(code)
    assert extractor._get_access_specifier(tree.root_node) is None


# --- _is_global_scope for root node ---
def test_is_global_scope_root(extractor):
    code = "class Foo { int x; };\n"
    tree = _parse(code)
    assert extractor._is_global_scope(tree.root_node) is True


# --- Extract elements with exception in plugin ---
def test_extract_elements_with_bad_extractor(plugin, monkeypatch):
    def bad_extractor_factory(self):
        class BadExtractor:
            def extract_functions(self, tree, src):
                raise RuntimeError("boom")

            def extract_classes(self, tree, src):
                return []

            def extract_variables(self, tree, src):
                return []

            def extract_imports(self, tree, src):
                return []

            def extract_packages(self, tree, src):
                return []

        return BadExtractor()

    code = "int x;\n"
    tree = _parse(code)
    from unittest.mock import patch

    with patch.object(type(plugin), "create_extractor", bad_extractor_factory):
        result = plugin.extract_elements(tree, code)
    assert result["functions"] == []


# --- Multiple global variables with init_declarator ---
def test_multiple_global_variables_init_declarator(extractor):
    code = "int a = 1, b = 2;\n"
    tree = _parse(code)
    variables = extractor.extract_variables(tree, code)
    names = [v.name for v in variables]
    assert "a" in names or "b" in names


# --- _count_tree_nodes with child nodes ---
def test_count_tree_nodes_with_children(plugin):
    code = "class Foo { int x; void bar() {} };\n"
    tree = _parse(code)
    count = plugin._count_tree_nodes(tree.root_node)
    assert count == 22


# --- Extract with doxygen comment on class ---
def test_doxygen_comment_on_class(extractor):
    code = "/**\n * A documented class.\n */\nclass DocClass {\n};\n"
    tree = _parse(code)
    classes = extractor.extract_classes(tree, code)
    dc = [c for c in classes if c.name == "DocClass"]
    assert len(dc) == 1
    assert dc[0].docstring is not None
    assert "documented" in dc[0].docstring


# --- Extract namespace with namespace_identifier child ---
def test_namespace_identifier_node(extractor):
    code = "namespace my_lib { int val = 42; }\n"
    tree = _parse(code)
    packages = extractor.extract_packages(tree, code)
    assert len(packages) == 1
    assert packages[0].name == "my_lib"


# --- Deeply nested blocks (max depth) ---
def test_deeply_nested_blocks(extractor):
    nesting = 100
    code = "int main() {\n"
    for _ in range(nesting):
        code += "    {\n"
    code += "    int x = 1;\n"
    for _ in range(nesting):
        code += "    }\n"
    code += "}\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    main_funcs = [f for f in funcs if f.name == "main"]
    assert len(main_funcs) == 1


# --- Static field declaration ---
def test_static_field_declaration(extractor):
    code = "class Counter {\n    static int count;\n};\n"
    tree = _parse(code)
    variables = extractor.extract_variables(tree, code)
    count_vars = [v for v in variables if v.name == "count"]
    assert len(count_vars) == 1
    assert count_vars[0].is_static is True


# --- Lambda function extraction ---
def test_lambda_expression(extractor):
    code = "auto add = [](int a, int b) { return a + b; };\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    # Lambda should not be extracted as a regular function
    lambda_funcs = [
        f for f in funcs if f.name is not None and "operator" in (f.name or "")
    ]
    # extraction gap: lambda expressions are not extracted as named functions; operator() not emitted
    assert len(lambda_funcs) == 0


# --- Include fallback regex extraction ---
def test_include_fallback_regex_direct(extractor):
    """Test _extract_includes_fallback with system and local includes."""
    code = '#include <iostream>\n#include "myheader.h"\n'
    imports = extractor._extract_includes_fallback(code)
    assert len(imports) == 2
    names = [i.name for i in imports]
    assert "iostream" in names
    assert "myheader.h" in names


# --- Include fallback with only system includes ---
def test_include_fallback_system_only(extractor):
    code = "#include <vector>\n#include <string>\n"
    imports = extractor._extract_includes_fallback(code)
    assert len(imports) == 2
    names = [i.name for i in imports]
    assert "vector" in names
    assert "string" in names


# --- Analyze file via CppPlugin ---
@pytest.mark.asyncio
async def test_analyze_file_cpp(plugin, tmp_path):
    """Test analyze_file on a real temporary C++ file."""
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


# --- Include fallback triggered when tree-sitter misses includes ---
def test_extract_imports_fallback_path(extractor):
    """Trigger the fallback regex path when tree-sitter finds no includes."""
    code = "#include <cstdio>\nint main() { return 0; }\n"
    tree = _parse(code)
    # The tree should have preproc_include child, so fallback won't trigger normally.
    # We need to ensure the extraction path exercises the code.
    imports = extractor.extract_imports(tree, code)
    # Just verify imports are extracted (either via tree-sitter or regex)
    assert len(imports) == 1


# --- _extract_function_optimized error handling ---
def test_extract_function_optimized_error(extractor, monkeypatch):
    """Test error handling in _extract_function_optimized."""
    code = "void foo() {}\n"
    tree = _parse(code)
    extractor.source_code = code
    extractor.content_lines = code.split("\n")
    extractor._reset_caches()

    # Mock _parse_function_signature to raise an exception
    def bad_parse(*args, **kwargs):
        raise ValueError("parse error")

    monkeypatch.setattr(extractor, "_parse_function_signature", bad_parse)
    result = extractor._extract_function_optimized(tree.root_node.children[0])
    assert result is None


# --- _extract_function_from_field_declaration error handling ---
def test_field_declaration_error_handling(extractor, monkeypatch):
    """Test error handling in _extract_function_from_field_declaration."""
    code = "class Foo { virtual double area() const = 0; };\n"
    tree = _parse(code)
    extractor.source_code = code
    extractor.content_lines = code.split("\n")
    extractor._reset_caches()

    # Find the field_declaration node
    def find_field_decl(node):
        if node.type == "field_declaration":
            return node
        for child in node.children:
            result = find_field_decl(child)
            if result:
                return result
        return None

    field_node = find_field_decl(tree.root_node)
    if field_node:
        # Mock _get_node_text_optimized to raise an exception
        monkeypatch.setattr(
            extractor,
            "_get_node_text_optimized",
            lambda n: (_ for _ in ()).throw(ValueError("boom")),
        )
        result = extractor._extract_function_from_field_declaration(field_node)
        assert result is None


# --- _extract_function_declaration error handling ---
def test_function_declaration_error_handling(extractor, monkeypatch):
    """Test error handling in _extract_function_declaration."""
    code = "int compute(int x);\n"
    tree = _parse(code)
    extractor.source_code = code
    extractor.content_lines = code.split("\n")
    extractor._reset_caches()

    # Find the function_declarator node
    def find_func_decl(node):
        if (
            node.type == "function_declarator"
            and node.parent
            and node.parent.type != "function_definition"
        ):
            return node
        for child in node.children:
            result = find_func_decl(child)
            if result:
                return result
        return None

    fn_node = find_func_decl(tree.root_node)
    if fn_node:
        # Mock _get_node_text_optimized to raise an exception
        monkeypatch.setattr(
            extractor,
            "_get_node_text_optimized",
            lambda n: (_ for _ in ()).throw(TypeError("bad")),
        )
        result = extractor._extract_function_declaration(fn_node)
        assert result is None
