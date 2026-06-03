"""RFC-0002: static assignment-based receiver-type inference in walk_tree."""

from __future__ import annotations

from tree_sitter_analyzer.core.parser import Parser
from tree_sitter_analyzer.function_extraction import walk_tree


def _calls(code: str):
    result = Parser().parse_code(code, "python")
    root = result.tree.root_node
    _defs, calls = walk_tree(root, code, "python")
    return {c["name"]: c for c in calls}


def test_var_constructed_from_class_infers_type():
    code = (
        "def handler():\n"
        "    pg = ProjectGraph(root)\n"
        "    pg.execute()\n"
        "    pg.all_edges()\n"
    )
    calls = _calls(code)
    assert calls["execute"]["full_name"] == "ProjectGraph.execute"
    assert calls["execute"]["receiver_type"] == "ProjectGraph"
    assert calls["all_edges"]["full_name"] == "ProjectGraph.all_edges"


def test_var_from_lowercase_func_not_inferred():
    # x = helper() — helper is a function (lowercase), not a class → no inference
    code = "def h():\n    x = helper()\n    x.foo()\n"
    calls = _calls(code)
    assert calls["foo"]["full_name"] == "x.foo"
    assert calls["foo"].get("receiver_type") is None


def test_inference_is_function_scoped():
    # pg is ProjectGraph in f, but a different var in g — no leak
    code = "def f():\n    pg = ProjectGraph()\n    pg.run()\ndef g():\n    pg.other()\n"
    calls = _calls(code)
    assert calls["run"]["full_name"] == "ProjectGraph.run"
    assert calls["other"]["full_name"] == "pg.other"  # g's pg untyped


def test_pytest_fixture_return_type_typed_param():
    # def tool(): return X(); def test(tool): tool.execute() → X.execute
    code = (
        "import pytest\n"
        "@pytest.fixture\n"
        "def tool(project):\n"
        "    return SearchContentTool(project)\n"
        "class TestX:\n"
        "    def test_execute(self, tool):\n"
        "        tool.execute(args)\n"
    )
    calls = _calls(code)
    assert calls["execute"]["full_name"] == "SearchContentTool.execute"
    assert calls["execute"]["receiver_type"] == "SearchContentTool"


def test_fixture_return_via_local_var():
    # def tool(): t = X(); return t
    code = (
        "def tool():\n    t = QueryTool()\n    return t\n"
        "def test_q(tool):\n    tool.run()\n"
    )
    calls = _calls(code)
    assert calls["run"]["full_name"] == "QueryTool.run"
