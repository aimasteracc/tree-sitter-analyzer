import pytest

from tree_sitter_analyzer.languages.cpp_plugin import CppPlugin


@pytest.fixture
def plugin():
    return CppPlugin()


def test_cpp_plugin_basic(plugin):
    code = """
    #include <iostream>
    namespace my_ns {
        class MyClass {
            public:
                void my_method() {}
        };
    }
    void global_func() {}
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
    assert "my_method" in names
    assert "global_func" in names
