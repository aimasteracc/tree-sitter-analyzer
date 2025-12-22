import pytest

from tree_sitter_analyzer.languages.c_plugin import CPlugin


@pytest.fixture
def plugin():
    return CPlugin()


def test_c_plugin_basic(plugin):
    code = """
    #include <stdio.h>
    struct MyStruct {
        int x;
    };
    void my_func(int a) {}
    """
    import tree_sitter

    language = plugin.get_tree_sitter_language()
    parser = tree_sitter.Parser(language)
    tree = parser.parse(code.encode("utf-8"))

    elements_dict = plugin.extract_elements(tree, code)
    assert elements_dict is not None
    assert len(elements_dict["functions"]) > 0
    assert len(elements_dict["classes"]) > 0

    names = [e.name for e in elements_dict["functions"]]
    assert "my_func" in names
