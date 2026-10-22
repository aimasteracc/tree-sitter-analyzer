"""#1743：Java 接收者声明类型线索与类型解析的单元测试（不建索引）。"""

from __future__ import annotations

import pytest
import tree_sitter
import tree_sitter_java

from tree_sitter_analyzer.java_receiver_hints import (
    JavaReceiverHintScope,
    anonymous_subclasses,
    method_variables,
)
from tree_sitter_analyzer.synapse_resolver._java_context import JavaResolverContext
from tree_sitter_analyzer.synapse_resolver._java_typed import (
    JavaTypeIndex,
    find_method,
    resolve_type,
)

_PARSER = tree_sitter.Parser(tree_sitter.Language(tree_sitter_java.language()))


def _methods(source: str) -> dict[str, object]:
    tree = _PARSER.parse(source.encode("utf-8"))
    found: dict[str, object] = {}
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type in ("method_declaration", "constructor_declaration"):
            name = node.child_by_field_name("name")
            found[name.text.decode()] = node
        stack.extend(node.children)
    return found


_SOURCE = """
class Outer {
  private Gson gson;
  private int count;
  private Map<String, List<X>> map;
  private Foo dup, dup2;
  private Bar dup;

  void m(Gson a, int n, String[] arr, TypeAdapter<T> ta, Object... rest, java.util.List<X> full) {
    Square sq = new Square();
    var v = make();
    int[] xs = null;
    for (Shape s : shapes) { s.area(); }
    try { } catch (IOException e) { } catch (IllegalStateException | IllegalArgumentException multi) { }
    Runnable r = () -> { Local inLambda = null; };
    java.util.function.Function<String, Integer> f = (String typed) -> 1;
    java.util.function.Function<String, Integer> g = untyped -> 2;
    Circle same = null;
    { Square same = null; }
    Object anon = new Adapter<String>() {
      long[] values(String s) { Hidden hidden = null; return null; }
    };
  }

  class Inner {
    private Inner2 gson;
    void n() { gson.run(); }
  }
}
"""


def test_method_variables_records_declared_types() -> None:
    method = _methods(_SOURCE)["m"]
    params, locals_ = method_variables(method)
    assert params == {
        "a": "Gson",
        "n": "",
        "arr": "",
        "ta": "TypeAdapter",
        "rest": "",
        "full": "java.util.List",
    }
    assert locals_["sq"] == "Square"
    assert locals_["v"] == ""  # var: unknown
    assert locals_["xs"] == ""  # array
    assert locals_["s"] == "Shape"  # enhanced for
    assert locals_["e"] == "IOException"
    assert locals_["multi"] == ""  # multi-catch
    assert locals_["inLambda"] == "Local"
    assert locals_["typed"] == "String"
    assert locals_["untyped"] == ""
    assert locals_["same"] == ""  # Circle vs Square: conflict
    assert "hidden" not in locals_  # anonymous class body is its own scope


def test_scope_prefers_locals_and_resolves_fields() -> None:
    methods = _methods(_SOURCE)
    scope = JavaReceiverHintScope().for_function(methods["m"])
    assert scope.hint_for("sq", None) == {"type": "Square", "source": "local"}
    assert scope.hint_for("a", None) == {"type": "Gson", "source": "param"}
    assert scope.hint_for("gson", None) == {"type": "Gson", "source": "field"}
    assert scope.hint_for("this.gson", None) == {"type": "Gson", "source": "field"}
    assert scope.hint_for("map", None) == {"type": "Map", "source": "field"}
    assert scope.hint_for("count", None) is None  # primitive field
    assert scope.hint_for("dup", None) is None  # Foo vs Bar field: conflict
    assert scope.hint_for("v", None) is None
    assert scope.hint_for("missing", None) is None
    assert scope.hint_for("a.b", None) is None
    assert scope.hint_for("make()", None) is None
    assert scope.hint_for(None, None) is None
    inner = JavaReceiverHintScope().for_function(methods["n"])
    # The inner class field shadows the outer one.
    assert inner.hint_for("gson", None) == {"type": "Inner2", "source": "field"}


def test_local_shadowing_a_field_with_another_type_is_not_recorded() -> None:
    source = "class A {\n  private Printer shadow;\n  void h() { shadow.size(); Square shadow = null; }\n}\n"
    scope = JavaReceiverHintScope().for_function(_methods(source)["h"])
    assert scope.hint_for("shadow", None) is None
    assert scope.hint_for("this.shadow", None) == {"type": "Printer", "source": "field"}


def test_anonymous_subclasses_are_listed_with_their_body_span() -> None:
    tree = _PARSER.parse(_SOURCE.encode("utf-8"))
    assert anonymous_subclasses(tree.root_node) == [
        {"base": "Adapter", "line": 20, "end_line": 22}
    ]


# --------------------------------------------------------------------------- resolution


def _ctx() -> tuple[JavaResolverContext, JavaTypeIndex]:
    jctx = JavaResolverContext(
        fqn_to_file={
            "com.ex.Shape": "Shape.java",
            "com.ex.Circle": "Circle.java",
            "com.ex.Outer": "Outer.java",
            "com.other.Thing": "Thing.java",
            "com.ex.Ext": "Ext.java",
            "com.ex.Diamond": "Diamond.java",
            "com.ex.Left": "Left.java",
            "com.ex.Right": "Right.java",
        },
        simple_to_fqn_by_file={
            "Use.java": {"List": "java.util.List", "Thing": "com.other.Thing"}
        },
        wildcard_pkgs_by_file={"Use.java": ["com.other"]},
        file_package={
            "Use.java": "com.ex",
            "Circle.java": "com.ex",
            "Ext.java": "com.ex",
            "Diamond.java": "com.ex",
        },
    )
    index = JavaTypeIndex(
        classes={
            "Shape.java": {"Shape": []},
            "Circle.java": {"Circle": ["Shape"]},
            "Outer.java": {"Outer": [], "Inner": []},
            "Thing.java": {"Thing": []},
            "Ext.java": {"Ext": ["ExternalBase"]},
            "Diamond.java": {"Diamond": ["Left", "Right"]},
            "Left.java": {"Left": []},
            "Right.java": {"Right": []},
        },
        methods={
            ("Shape.java", "Shape"): {"area": [(4, 1)]},
            ("Circle.java", "Circle"): {"print": [(5, 2), (7, 3)]},
            ("Outer.java", "Inner"): {"run": [(9, 4)]},
            ("Left.java", "Left"): {"go": [(2, 5)]},
            ("Right.java", "Right"): {"go": [(2, 6)]},
        },
    )
    return jctx, index


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Circle", ("Circle.java", "Circle")),  # same package
        ("Thing", ("Thing.java", "Thing")),  # single-type import
        ("List", None),  # imported, outside the project
        ("com.ex.Shape", ("Shape.java", "Shape")),  # fully qualified
        ("Outer.Inner", ("Outer.java", "Inner")),  # nested through the outer class
        ("Outer.Missing", None),
        ("Circle<T>", ("Circle.java", "Circle")),
        ("T", None),  # type variable
        ("", None),
    ],
)
def test_resolve_type(name: str, expected) -> None:
    jctx, index = _ctx()
    assert resolve_type(name, "Use.java", jctx, index) == expected


def test_find_method_through_ancestors_and_refusals() -> None:
    jctx, index = _ctx()
    # Inherited from the project interface.
    assert find_method(("Circle.java", "Circle"), "area", jctx, index) == (
        "Shape.java",
        1,
        "Shape",
        4,
    )
    # Overloads are not bound.
    assert find_method(("Circle.java", "Circle"), "print", jctx, index) is None
    # Unresolvable base type: the method may come from it.
    assert find_method(("Ext.java", "Ext"), "area", jctx, index) is None
    # Two branches each declare it: ambiguous.
    assert find_method(("Diamond.java", "Diamond"), "go", jctx, index) is None
    assert find_method(("Shape.java", "Shape"), "nothing", jctx, index) is None
