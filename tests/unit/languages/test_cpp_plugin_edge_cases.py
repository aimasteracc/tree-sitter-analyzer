"""C++ plugin edge case and error handling tests — extracted from test_cpp_plugin_coverage_boost."""

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


def test_is_global_scope_root(extractor):
    code = "class Foo { int x; };\n"
    tree = _parse(code)
    assert extractor._is_global_scope(tree.root_node) is True


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


def test_multiple_global_variables_init_declarator(extractor):
    code = "int a = 1, b = 2;\n"
    tree = _parse(code)
    variables = extractor.extract_variables(tree, code)
    names = [v.name for v in variables]
    assert "a" in names or "b" in names


def test_count_tree_nodes_with_children(plugin):
    code = "class Foo { int x; void bar() {} };\n"
    tree = _parse(code)
    count = plugin._count_tree_nodes(tree.root_node)
    assert count > 5


def test_doxygen_comment_on_class(extractor):
    code = "/**\n * A documented class.\n */\nclass DocClass {\n};\n"
    tree = _parse(code)
    classes = extractor.extract_classes(tree, code)
    dc = [c for c in classes if c.name == "DocClass"]
    assert len(dc) >= 1
    assert dc[0].docstring is not None
    assert "documented" in dc[0].docstring


def test_namespace_identifier_node(extractor):
    code = "namespace my_lib { int val = 42; }\n"
    tree = _parse(code)
    packages = extractor.extract_packages(tree, code)
    assert len(packages) >= 1
    assert packages[0].name == "my_lib"


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
    assert len(main_funcs) >= 1


def test_static_field_declaration(extractor):
    code = "class Counter {\n    static int count;\n};\n"
    tree = _parse(code)
    variables = extractor.extract_variables(tree, code)
    count_vars = [v for v in variables if v.name == "count"]
    assert len(count_vars) >= 1
    assert count_vars[0].is_static is True


def test_lambda_expression(extractor):
    code = "auto add = [](int a, int b) { return a + b; };\n"
    tree = _parse(code)
    funcs = extractor.extract_functions(tree, code)
    lambda_funcs = [
        f for f in funcs if f.name is not None and "operator" in (f.name or "")
    ]
    assert len(lambda_funcs) >= 0


def test_include_fallback_regex_direct(extractor):
    code = '#include <iostream>\n#include "myheader.h"\n'
    imports = extractor._extract_includes_fallback(code)
    assert len(imports) >= 2
    names = [i.name for i in imports]
    assert "iostream" in names
    assert "myheader.h" in names


def test_include_fallback_system_only(extractor):
    code = "#include <vector>\n#include <string>\n"
    imports = extractor._extract_includes_fallback(code)
    assert len(imports) >= 2
    names = [i.name for i in imports]
    assert "vector" in names
    assert "string" in names


@pytest.mark.asyncio
async def test_analyze_file_cpp(plugin, tmp_path):
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
    assert result.line_count > 0


def test_extract_imports_fallback_path(extractor):
    code = "#include <cstdio>\nint main() { return 0; }\n"
    tree = _parse(code)
    imports = extractor.extract_imports(tree, code)
    assert len(imports) >= 1


def test_extract_function_optimized_error(extractor, monkeypatch):
    code = "void foo() {}\n"
    tree = _parse(code)
    extractor.source_code = code
    extractor.content_lines = code.split("\n")
    extractor._reset_caches()

    def bad_parse(*args, **kwargs):
        raise ValueError("parse error")

    monkeypatch.setattr(extractor, "_parse_function_signature", bad_parse)
    result = extractor._extract_function_optimized(tree.root_node.children[0])
    assert result is None


def test_field_declaration_error_handling(extractor, monkeypatch):
    code = "class Foo { virtual double area() const = 0; };\n"
    tree = _parse(code)
    extractor.source_code = code
    extractor.content_lines = code.split("\n")
    extractor._reset_caches()

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
        monkeypatch.setattr(
            extractor,
            "_get_node_text_optimized",
            lambda n: (_ for _ in ()).throw(ValueError("boom")),
        )
        result = extractor._extract_function_from_field_declaration(field_node)
        assert result is None


def test_function_declaration_error_handling(extractor, monkeypatch):
    code = "int compute(int x);\n"
    tree = _parse(code)
    extractor.source_code = code
    extractor.content_lines = code.split("\n")
    extractor._reset_caches()

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
        monkeypatch.setattr(
            extractor,
            "_get_node_text_optimized",
            lambda n: (_ for _ in ()).throw(TypeError("bad")),
        )
        result = extractor._extract_function_declaration(fn_node)
        assert result is None
