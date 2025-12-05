from types import SimpleNamespace

from tree_sitter_analyzer.languages.cpp_plugin import CppElementExtractor, CppPlugin


class FakeNode:
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
        self.end_byte = (self.start_byte + len(text)) if end_byte is None else end_byte
        self._fields = fields or {}

    def child_by_field_name(self, name):
        return self._fields.get(name)


def make_tree(root):
    return SimpleNamespace(root_node=root)


def test_plugin_metadata():
    p = CppPlugin()
    assert p.get_language_name() == "cpp"
    assert ".cpp" in p.get_file_extensions()


def test_extractor_covers_elements():
    source = "#include <iostream>\nusing namespace std;\nstruct V {int x;};\nclass G {public: int m(int t){return t;}};\nint v=1;\n"
    extractor = CppElementExtractor()

    fn_text = "int m(int t){return t;}"
    fn_start = source.find(fn_text)
    ident_m = FakeNode("identifier", "m", start_byte=fn_start + fn_text.find("m"))
    params_text = "(int t)"
    params = FakeNode(
        "parameters",
        params_text,
        start_byte=fn_start + fn_text.find(params_text),
        children=[FakeNode("identifier", "t")],
    )
    decl = FakeNode(
        "declarator",
        "m(int t)",
        start_byte=fn_start + fn_text.find("m"),
        children=[ident_m, params],
        fields={"parameters": params},
    )
    type_node = FakeNode("type", "int", start_byte=fn_start)
    fn = FakeNode(
        "function_definition",
        fn_text,
        start_line=3,
        start_byte=fn_start,
        fields={"declarator": decl, "type": type_node},
    )

    class_text = "class G {public: int m(int t){return t;}};"
    class_start = source.find(class_text)
    class_name = FakeNode(
        "type_identifier", "G", start_byte=class_start + class_text.find("G")
    )
    class_node = FakeNode(
        "class_specifier",
        class_text,
        start_line=3,
        start_byte=class_start,
        children=[class_name],
    )

    struct_text = "struct V {int x;};"
    struct_start = source.find(struct_text)
    struct_name = FakeNode(
        "type_identifier", "V", start_byte=struct_start + struct_text.find("V")
    )
    struct_node = FakeNode(
        "struct_specifier",
        struct_text,
        start_line=2,
        start_byte=struct_start,
        children=[struct_name],
    )

    using_decl = FakeNode(
        "using_declaration",
        "using namespace std;",
        start_line=1,
        start_byte=source.find("using namespace std;"),
    )
    ns_def = FakeNode(
        "namespace_definition",
        "namespace demo {}",
        start_line=0,
        start_byte=source.find("namespace demo {}")
        if "namespace demo {}" in source
        else 0,
    )
    inc = FakeNode(
        "preproc_include",
        "#include <iostream>",
        start_line=0,
        start_byte=source.find("#include <iostream>"),
    )

    var_text = "int v=1;"
    var_start = source.find(var_text)
    decl_name = FakeNode("identifier", "v", start_byte=var_start + var_text.find("v"))
    init_decl = FakeNode(
        "init_declarator",
        "v=1",
        start_byte=var_start + var_text.find("v"),
        children=[decl_name],
    )
    decl_specs = FakeNode("declaration_specifiers", "int", start_byte=var_start)
    var_decl = FakeNode(
        "declaration",
        var_text,
        start_line=4,
        start_byte=var_start,
        children=[init_decl],
        fields={"declaration_specifiers": decl_specs},
    )

    root = FakeNode(
        "root",
        source,
        children=[ns_def, inc, using_decl, struct_node, class_node, fn, var_decl],
    )
    tree = make_tree(root)

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


def test_analyze_file_runs():
    p = CppPlugin()
    import asyncio
    import os

    path = os.path.join("examples", "sample.cpp")
    out = asyncio.run(p.analyze_file(path, SimpleNamespace()))
    assert out is not None
