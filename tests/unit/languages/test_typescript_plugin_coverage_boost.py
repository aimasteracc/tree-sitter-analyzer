import pytest

from tree_sitter_analyzer.languages.typescript_plugin import TypeScriptPlugin


@pytest.fixture
def plugin():
    return TypeScriptPlugin()


def test_typescript_plugin_basic(plugin):
    code = """
    import { x } from './mod';
    export interface MyInterface {
        a: number;
    }
    export class MyClass {
        constructor(private b: string) {}
        myMethod(): void {}
    }
    enum MyEnum { A, B }
    type MyType = string | number;
    function myFunc<T>(arg: T): T { return arg; }
    """
    import tree_sitter

    language = plugin.get_tree_sitter_language()
    parser = tree_sitter.Parser(language)
    tree = parser.parse(code.encode("utf-8"))

    elements_dict = plugin.extract_elements(tree, code)
    assert elements_dict is not None
    assert len(elements_dict) > 0
