import os
import tempfile

import pytest
import tree_sitter

from tree_sitter_analyzer.languages.python_plugin import (
    PythonElementExtractor,
    PythonPlugin,
)
from tree_sitter_analyzer.models import Class, Function, Import, Variable


@pytest.fixture
def plugin():
    return PythonPlugin()


@pytest.fixture
def extractor():
    return PythonElementExtractor()


def _parse(plugin, code):
    language = plugin.get_tree_sitter_language()
    parser = tree_sitter.Parser(language)
    return parser.parse(code.encode("utf-8"))


def test_python_plugin_basic(plugin):
    code = """
    import os
    from sys import path

    class MyClass:
        @property
        def my_prop(self):
            return 1

        @classmethod
        def my_class_method(cls):
            pass

    def my_func(a: int) -> str:
        return str(a)
    """
    tree = _parse(plugin, code)
    elements = plugin.extract_elements(tree, code)
    assert elements is not None
    assert len(elements) > 0


class TestExtractImportsManual:
    def test_simple_import(self, extractor, plugin):
        code = "import os\nimport sys\n"
        tree = _parse(plugin, code)
        imports = extractor._extract_imports_manual(tree.root_node, code)
        assert len(imports) >= 2
        names = [i.name for i in imports]
        assert "os" in names
        assert "sys" in names

    def test_from_import(self, extractor, plugin):
        code = "from os.path import join, exists\n"
        tree = _parse(plugin, code)
        imports = extractor._extract_imports_manual(tree.root_node, code)
        assert len(imports) >= 1
        imp = imports[0]
        assert imp.module_name == "os.path"
        assert "join" in imp.imported_names
        assert "exists" in imp.imported_names

    def test_from_import_single(self, extractor, plugin):
        code = "from collections import OrderedDict\n"
        tree = _parse(plugin, code)
        imports = extractor._extract_imports_manual(tree.root_node, code)
        assert len(imports) >= 1
        assert "collections" in imports[0].module_name

    def test_empty_code(self, extractor, plugin):
        code = ""
        tree = _parse(plugin, code)
        imports = extractor._extract_imports_manual(tree.root_node, code)
        assert imports == []

    def test_no_imports(self, extractor, plugin):
        code = "x = 1\ny = 2\n"
        tree = _parse(plugin, code)
        imports = extractor._extract_imports_manual(tree.root_node, code)
        assert imports == []


class TestExtractPackages:
    def test_with_init_file(self, extractor):
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = os.path.join(tmpdir, "mypkg")
            os.makedirs(pkg_dir)
            with open(os.path.join(pkg_dir, "__init__.py"), "w") as f:
                f.write("# package\n")
            with open(os.path.join(pkg_dir, "mod.py"), "w") as f:
                f.write("x = 1\n")

            extractor.current_file = os.path.join(pkg_dir, "mod.py")
            plugin = PythonPlugin()
            tree = _parse(plugin, "# test\n")
            packages = extractor.extract_packages(tree, "")
            assert len(packages) >= 1
            assert packages[0].name == "mypkg"

    def test_no_init_file(self, extractor):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor.current_file = os.path.join(tmpdir, "mod.py")
            plugin = PythonPlugin()
            tree = _parse(plugin, "# test\n")
            packages = extractor.extract_packages(tree, "")
            assert packages == []

    def test_no_current_file(self, extractor):
        extractor.current_file = ""
        plugin = PythonPlugin()
        tree = _parse(plugin, "# test\n")
        packages = extractor.extract_packages(tree, "")
        assert packages == []


class TestGetNodeTypeForElement:
    def test_function(self, plugin):
        assert (
            plugin._get_node_type_for_element(Function("f", 1, 1, "def f(): pass"))
            == "function_definition"
        )

    def test_class(self, plugin):
        assert (
            plugin._get_node_type_for_element(Class("C", 1, 1, "class C: pass"))
            == "class_definition"
        )

    def test_variable(self, plugin):
        assert (
            plugin._get_node_type_for_element(Variable("x", 1, 1, "x = 1"))
            == "assignment"
        )

    def test_import(self, plugin):
        assert (
            plugin._get_node_type_for_element(Import("os", 1, 1, "import os"))
            == "import_statement"
        )

    def test_unknown(self, plugin):
        assert plugin._get_node_type_for_element("not_an_element") == "unknown"


class TestExtractDecoratorsFromNode:
    def test_decorated_function(self, extractor, plugin):
        code = "class A:\n    @property\n    def x(self):\n        return 1\n"
        tree = _parse(plugin, code)

        # Find the function_definition node
        def find_nodes(node, node_type):
            result = []
            if node.type == node_type:
                result.append(node)
            for child in node.children:
                result.extend(find_nodes(child, node_type))
            return result

        func_nodes = find_nodes(tree.root_node, "function_definition")
        assert len(func_nodes) >= 1
        decorators = extractor._extract_decorators_from_node(func_nodes[0], code)
        assert "property" in decorators

    def test_no_decorators(self, extractor, plugin):
        code = "def plain():\n    pass\n"
        tree = _parse(plugin, code)

        def find_nodes(node, node_type):
            result = []
            if node.type == node_type:
                result.append(node)
            for child in node.children:
                result.extend(find_nodes(child, node_type))
            return result

        func_nodes = find_nodes(tree.root_node, "function_definition")
        if func_nodes:
            decorators = extractor._extract_decorators_from_node(func_nodes[0], code)
            assert decorators == []


class TestExtractReturnTypeFromNode:
    def test_with_return_type(self, extractor, plugin):
        code = "def f() -> str:\n    return 'x'\n"
        tree = _parse(plugin, code)

        def find_nodes(node, node_type):
            result = []
            if node.type == node_type:
                result.append(node)
            for child in node.children:
                result.extend(find_nodes(child, node_type))
            return result

        func_nodes = find_nodes(tree.root_node, "function_definition")
        assert len(func_nodes) >= 1
        ret = extractor._extract_return_type_from_node(func_nodes[0], code)
        assert ret is not None and "str" in ret

    def test_no_return_type(self, extractor, plugin):
        code = "def f():\n    pass\n"
        tree = _parse(plugin, code)

        def find_nodes(node, node_type):
            result = []
            if node.type == node_type:
                result.append(node)
            for child in node.children:
                result.extend(find_nodes(child, node_type))
            return result

        func_nodes = find_nodes(tree.root_node, "function_definition")
        if func_nodes:
            ret = extractor._extract_return_type_from_node(func_nodes[0], code)
            assert ret is None


class TestExtractDocstringFromNode:
    def test_function_docstring(self, extractor, plugin):
        code = 'def f():\n    """Hello."""\n    pass\n'
        tree = _parse(plugin, code)

        def find_nodes(node, node_type):
            result = []
            if node.type == node_type:
                result.append(node)
            for child in node.children:
                result.extend(find_nodes(child, node_type))
            return result

        func_nodes = find_nodes(tree.root_node, "function_definition")
        if func_nodes:
            doc = extractor._extract_docstring_from_node(func_nodes[0], code)
            if doc is not None:
                assert "Hello" in doc

    def test_class_docstring(self, extractor, plugin):
        code = 'class C:\n    """My class."""\n    pass\n'
        tree = _parse(plugin, code)

        def find_nodes(node, node_type):
            result = []
            if node.type == node_type:
                result.append(node)
            for child in node.children:
                result.extend(find_nodes(child, node_type))
            return result

        class_nodes = find_nodes(tree.root_node, "class_definition")
        if class_nodes:
            doc = extractor._extract_docstring_from_node(class_nodes[0], code)
            if doc is not None:
                assert "My class" in doc


class TestExtractFunctionBody:
    def test_simple_body(self, extractor, plugin):
        code = "def f():\n    x = 1\n    return x\n"
        tree = _parse(plugin, code)

        def find_nodes(node, node_type):
            result = []
            if node.type == node_type:
                result.append(node)
            for child in node.children:
                result.extend(find_nodes(child, node_type))
            return result

        func_nodes = find_nodes(tree.root_node, "function_definition")
        assert len(func_nodes) >= 1
        body = extractor._extract_function_body(func_nodes[0], code)
        assert "x = 1" in body


class TestExtractSuperclassesFromNode:
    def test_with_superclass(self, extractor, plugin):
        code = "class Child(Base):\n    pass\n"
        tree = _parse(plugin, code)

        def find_nodes(node, node_type):
            result = []
            if node.type == node_type:
                result.append(node)
            for child in node.children:
                result.extend(find_nodes(child, node_type))
            return result

        class_nodes = find_nodes(tree.root_node, "class_definition")
        assert len(class_nodes) >= 1
        supers = extractor._extract_superclasses_from_node(class_nodes[0], code)
        assert "Base" in supers

    def test_no_superclass(self, extractor, plugin):
        code = "class Plain:\n    pass\n"
        tree = _parse(plugin, code)

        def find_nodes(node, node_type):
            result = []
            if node.type == node_type:
                result.append(node)
            for child in node.children:
                result.extend(find_nodes(child, node_type))
            return result

        class_nodes = find_nodes(tree.root_node, "class_definition")
        if class_nodes:
            supers = extractor._extract_superclasses_from_node(class_nodes[0], code)
            assert supers == []


class TestCalculateComplexity:
    def test_simple(self, extractor):
        body = "x = 1"
        assert extractor._calculate_complexity(body) == 1

    def test_with_branches(self, extractor):
        body = "if x:\n    pass\nelif y:\n    pass\nfor i in range(10):\n    pass"
        c = extractor._calculate_complexity(body)
        assert c >= 3


class TestExecuteQuery:
    def test_function_query(self, plugin):
        code = "def hello():\n    pass\n"
        tree = _parse(plugin, code)
        result = plugin.execute_query(tree, "function")
        assert "captures" in result

    def test_class_query(self, plugin):
        code = "class Foo:\n    pass\n"
        tree = _parse(plugin, code)
        result = plugin.execute_query(tree, "class")
        assert "captures" in result

    def test_unknown_query(self, plugin):
        code = "x = 1\n"
        tree = _parse(plugin, code)
        result = plugin.execute_query(tree, "unknown_query_xyz")
        assert "error" in result


class TestExtractDetailedFunctionInfo:
    def test_async_function(self, extractor, plugin):
        code = "async def fetch():\n    return 1\n"
        tree = _parse(plugin, code)

        def find_nodes(node, node_type):
            result = []
            if node.type == node_type:
                result.append(node)
            for child in node.children:
                result.extend(find_nodes(child, node_type))
            return result

        func_nodes = find_nodes(tree.root_node, "function_definition")
        assert len(func_nodes) >= 1
        info = extractor._extract_detailed_function_info(
            func_nodes[0], code, is_async=True
        )
        assert info is not None
        assert info.name == "fetch"

    def test_dunder_method_is_public(self, extractor, plugin):
        code = "class C:\n    def __init__(self):\n        pass\n"
        tree = _parse(plugin, code)

        def find_nodes(node, node_type):
            result = []
            if node.type == node_type:
                result.append(node)
            for child in node.children:
                result.extend(find_nodes(child, node_type))
            return result

        func_nodes = find_nodes(tree.root_node, "function_definition")
        assert len(func_nodes) >= 1
        info = extractor._extract_detailed_function_info(func_nodes[0], code)
        assert info is not None
        assert info.name == "__init__"
        assert info.is_private is False

    def test_private_method(self, extractor, plugin):
        code = "class C:\n    def _internal(self):\n        pass\n"
        tree = _parse(plugin, code)

        def find_nodes(node, node_type):
            result = []
            if node.type == node_type:
                result.append(node)
            for child in node.children:
                result.extend(find_nodes(child, node_type))
            return result

        func_nodes = find_nodes(tree.root_node, "function_definition")
        assert len(func_nodes) >= 1
        info = extractor._extract_detailed_function_info(func_nodes[0], code)
        assert info is not None
        assert info.name == "_internal"
        assert info.is_private is True


class TestGetElementCategories:
    def test_returns_dict(self, plugin):
        cats = plugin.get_element_categories()
        assert isinstance(cats, dict)
        assert "function" in cats
        assert "class" in cats
        assert "import" in cats
        assert "lambda" in cats
        assert "decorator" in cats
        assert "comprehension" in cats

    def test_all_values_are_lists(self, plugin):
        cats = plugin.get_element_categories()
        for key, val in cats.items():
            assert isinstance(val, list), f"{key} value is not a list"


class TestPluginInfo:
    def test_get_plugin_info(self, plugin):
        info = plugin.get_plugin_info()
        assert info["name"] == "Python Plugin"
        assert info["language"] == "python"
        assert info["version"] == "2.0.0"
        assert ".py" in info["extensions"]
        assert len(info["supported_queries"]) > 0
        assert len(info["features"]) > 0


class TestExtractElementsErrorHandling:
    def test_with_bad_tree(self, plugin):
        result = plugin.extract_elements(None, "def f(): pass")
        assert isinstance(result, dict)


class TestSupportedQueries:
    def test_supported_queries_list(self, plugin):
        queries = plugin.get_supported_queries()
        assert "function" in queries
        assert "class" in queries
        assert "async_function" in queries
        assert "lambda" in queries
        assert "django_model" in queries
