from types import SimpleNamespace

from tree_sitter_analyzer.languages.c_plugin import CElementExtractor, CPlugin


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
    p = CPlugin()
    assert p.get_language_name() == "c"
    assert ".c" in p.get_file_extensions()


def test_extractor_covers_elements():
    source = "#include <stdio.h>\nint add(int a,int b){return a+b;}\nstruct S {int x;};\nint v=0;\n"
    extractor = CElementExtractor()

    fn_text = "int add(int a,int b){return a+b;}"
    fn_start = source.find(fn_text)
    ident_add = FakeNode("identifier", "add", start_byte=fn_start + fn_text.find("add"))
    params_text = "(int a,int b)"
    params = FakeNode(
        "parameters",
        params_text,
        start_byte=fn_start + fn_text.find(params_text),
        children=[FakeNode("identifier", "a"), FakeNode("identifier", "b")],
    )
    decl = FakeNode(
        "declarator",
        "add(int a,int b)",
        start_byte=fn_start + fn_text.find("add"),
        children=[ident_add, params],
        fields={"parameters": params},
    )
    type_node = FakeNode("type", "int", start_byte=fn_start)
    fn = FakeNode(
        "function_definition",
        fn_text,
        start_line=1,
        start_byte=fn_start,
        fields={"declarator": decl, "type": type_node},
    )

    struct_text = "struct S {int x;};"
    struct_start = source.find(struct_text)
    struct_name = FakeNode(
        "type_identifier", "S", start_byte=struct_start + struct_text.find("S")
    )
    struct_node = FakeNode(
        "struct_specifier",
        struct_text,
        start_line=2,
        start_byte=struct_start,
        children=[struct_name],
    )

    var_text = "int v=0;"
    var_start = source.find(var_text)
    decl_name = FakeNode("identifier", "v", start_byte=var_start + var_text.find("v"))
    init_decl = FakeNode(
        "init_declarator",
        "v=0",
        start_byte=var_start + var_text.find("v"),
        children=[decl_name],
    )
    decl_specs = FakeNode("declaration_specifiers", "int", start_byte=var_start)
    var_decl = FakeNode(
        "declaration",
        var_text,
        start_line=3,
        start_byte=var_start,
        children=[init_decl],
        fields={"declaration_specifiers": decl_specs},
    )

    inc_text = "#include <stdio.h>"
    inc = FakeNode(
        "preproc_include", inc_text, start_line=0, start_byte=source.find(inc_text)
    )

    root = FakeNode("root", source, children=[inc, fn, struct_node, var_decl])
    tree = make_tree(root)

    funcs = extractor.extract_functions(tree, source)
    assert isinstance(funcs, list)

    classes = extractor.extract_classes(tree, source)
    assert isinstance(classes, list)

    vars_ = extractor.extract_variables(tree, source)
    assert isinstance(vars_, list)

    imps = extractor.extract_imports(tree, source)
    assert any(i.import_statement.startswith("#include") for i in imps)


def test_analyze_file_runs():
    import os

    p = CPlugin()
    path = os.path.join("examples", "sample.c")
    ar = SimpleNamespace()
    # call
    out = None
    try:
        out = __import__("asyncio").run(p.analyze_file(path, ar))
    except Exception:
        out = None
    assert out is not None
