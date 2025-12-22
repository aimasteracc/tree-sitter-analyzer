import pytest

from tree_sitter_analyzer.languages.python_plugin import PythonPlugin


@pytest.fixture
def plugin():
    return PythonPlugin()


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
    import tree_sitter

    language = plugin.get_tree_sitter_language()
    parser = tree_sitter.Parser(language)
    tree = parser.parse(code.encode("utf-8"))

    elements_dict = plugin.extract_elements(tree, code)
    assert elements_dict is not None
    assert len(elements_dict) > 0
