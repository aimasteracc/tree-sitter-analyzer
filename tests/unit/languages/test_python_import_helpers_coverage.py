"""Coverage boost tests for languages/python_plugin/_import.py."""

from unittest.mock import MagicMock

from tree_sitter_analyzer.languages.python_plugin._import import (
    ClassBodyQueryRuntime,
    ImportExtractionRuntime,
    ImportNodeContext,
    extract_imports_from_tree,
    import_node_context,
    parse_from_import,
    parse_simple_import,
    query_class_body_nodes,
)


def _mock_node(
    source_code: str,
    node_type="import_statement",
    start_point=(0, 0),
    end_point=None,
    children=None,
):
    if end_point is None:
        end_point = (0, len(source_code))
    node = MagicMock()
    node.type = node_type
    node.start_byte = 0
    node.end_byte = len(source_code)
    node.start_point = start_point
    node.end_point = end_point
    node.children = children or []
    return node


def _child_from_source(source_code: str, text: str, node_type="identifier"):
    start = source_code.index(text)
    end = start + len(text)
    child = MagicMock()
    child.type = node_type
    child.start_byte = start
    child.end_byte = end
    child.start_point = (0, start)
    child.end_point = (0, end)
    return child


class TestImportNodeContext:
    def test_creates_context(self):
        node = _mock_node("import os")
        ctx = import_node_context(node, "import os\n")
        assert ctx.start_line == 1
        assert ctx.end_line == 1
        assert ctx.raw_text == "import os"

    def test_node_without_start_byte(self):
        node = MagicMock(spec=[])
        node.start_point = (0, 0)
        node.end_point = (0, 5)
        ctx = import_node_context(node, "hello")
        assert ctx.raw_text == ""


class TestParseSimpleImport:
    def test_single_import(self):
        source = "import os"
        child = _child_from_source(source, "os", "identifier")
        node = _mock_node(source, children=[child])
        ctx = ImportNodeContext(source, 1, 1, source)
        imports = []
        parse_simple_import(node, ctx, imports)
        assert len(imports) == 1
        assert imports[0].name == "os"

    def test_dotted_name_import(self):
        source = "import os.path"
        child = _child_from_source(source, "os.path", "dotted_name")
        node = _mock_node(source, children=[child])
        ctx = ImportNodeContext(source, 1, 1, source)
        imports = []
        parse_simple_import(node, ctx, imports)
        assert len(imports) == 1
        assert imports[0].name == "os.path"

    def test_skips_import_keyword(self):
        source = "import import"
        child = _child_from_source(source, "import", "import")
        node = _mock_node(source, children=[child])
        ctx = ImportNodeContext(source, 1, 1, source)
        imports = []
        parse_simple_import(node, ctx, imports)
        assert len(imports) == 0

    def test_skips_other_types(self):
        source = "import ("
        child = MagicMock()
        child.type = "lparen"
        node = _mock_node(source, children=[child])
        ctx = ImportNodeContext(source, 1, 1, source)
        imports = []
        parse_simple_import(node, ctx, imports)
        assert len(imports) == 0

    def test_multiple_children(self):
        source = "import os, sys"
        c1 = _child_from_source(source, "os", "identifier")
        c2 = _child_from_source(source, "sys", "identifier")
        node = _mock_node(source, children=[c1, c2])
        ctx = ImportNodeContext(source, 1, 1, source)
        imports = []
        parse_simple_import(node, ctx, imports)
        assert len(imports) == 2
        names = [i.name for i in imports]
        assert "os" in names
        assert "sys" in names


class TestParseFromImport:
    def test_from_import_with_import_list(self):
        source = "from abc import ABC, abstractmethod"
        dotted = _child_from_source(source, "abc", "dotted_name")
        id1 = _child_from_source(source, "ABC", "identifier")
        id2 = _child_from_source(source, "abstractmethod", "identifier")
        import_list = MagicMock()
        import_list.children = [id1, id2]
        import_list.type = "import_list"
        node = _mock_node(source, children=[dotted, import_list])
        ctx = ImportNodeContext(source, 1, 1, source)
        imports = []
        parse_from_import(node, ctx, imports)
        assert len(imports) == 1
        assert imports[0].module_name == "abc"
        assert "ABC" in imports[0].imported_names
        assert "abstractmethod" in imports[0].imported_names

    def test_from_import_no_module(self):
        source = "from import x"
        node = _mock_node(source, children=[])
        ctx = ImportNodeContext(source, 1, 1, source)
        imports = []
        parse_from_import(node, ctx, imports)
        assert len(imports) == 0

    def test_from_import_with_dotted_name_as_item(self):
        source = "from os import path"
        d1 = _child_from_source(source, "os", "dotted_name")
        d2 = _child_from_source(source, "path", "dotted_name")
        node = _mock_node(source, children=[d1, d2])
        ctx = ImportNodeContext(source, 1, 1, source)
        imports = []
        parse_from_import(node, ctx, imports)
        assert len(imports) == 1
        assert imports[0].module_name == "os"
        assert "path" in imports[0].imported_names


class TestQueryClassBodyNodes:
    def test_no_language_returns_empty(self):
        tree = MagicMock(spec=[])
        runtime = ClassBodyQueryRuntime(
            tree=tree,
            class_query="(class_definition body: (_) @class.body)",
            log_debug_fn=lambda _: None,
            log_warning_fn=lambda _: None,
        )
        result = query_class_body_nodes(runtime)
        assert result == []

    def test_query_exception_returns_empty(self):
        tree = MagicMock()
        tree.language = MagicMock()
        tree.language.query.side_effect = Exception("query failed")
        runtime = ClassBodyQueryRuntime(
            tree=tree,
            class_query="(invalid query",
            log_debug_fn=lambda _: None,
            log_warning_fn=lambda _: None,
        )
        result = query_class_body_nodes(runtime)
        assert result == []


class TestExtractImportsFromTree:
    def test_no_language_returns_empty(self):
        tree = MagicMock(spec=[])
        runtime = ImportExtractionRuntime(
            tree=tree,
            source_code="import os\n",
            import_query="(import_statement) @imp",
            extract_import_info=lambda n, s, t: None,
            extract_imports_manual=lambda n, s: [],
            log_debug_fn=lambda _: None,
            log_warning_fn=lambda _: None,
        )
        imports = extract_imports_from_tree(runtime)
        assert imports == []

    def test_query_returns_empty_on_bad_language(self):
        tree = MagicMock()
        tree.language = MagicMock()
        tree.root_node = MagicMock()
        runtime = ImportExtractionRuntime(
            tree=tree,
            source_code="import os\n",
            import_query="(import_statement) @imp",
            extract_import_info=lambda n, s, t: None,
            extract_imports_manual=lambda n, s: [],
            log_debug_fn=lambda _: None,
            log_warning_fn=lambda _: None,
        )
        imports = extract_imports_from_tree(runtime)
        assert isinstance(imports, list)
