"""#1880: a class method found through the superclass wins over external interfaces.

With generic supertypes indexed, ``class JsonArray extends JsonElement
implements Iterable<JsonElement>`` now lists ``Iterable`` among its parents.
``Iterable`` is outside the project, so ``find_method`` gave up on
``jsonArray.toString()`` although ``JsonElement.toString`` is the static target:
in Java a method inherited from the superclass chain takes precedence over any
interface method of the same signature, and an interface outside the project
cannot add a project method. A project interface that declares the name still
makes the binding ambiguous.
"""

from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from tree_sitter_analyzer.synapse_resolver import _java_typed as jt
from tree_sitter_analyzer.synapse_resolver._java_context import JavaResolverContext

_JCTX = JavaResolverContext(
    file_package={"Arr.java": "p", "Elem.java": "p", "I.java": "p", "Mid.java": "p"},
    fqn_to_file={
        "p.Arr": "Arr.java",
        "p.Elem": "Elem.java",
        "p.I": "I.java",
        "p.Mid": "Mid.java",
    },
)
_TO_STRING = {("Elem.java", "Elem"): {"toString": [(5, 50)]}}


def _index(parents: list[str], superclass: str | None = "Elem", **extra):
    superclasses = {("Arr.java", "Arr"): superclass} if superclass else {}
    superclasses.update(extra.pop("superclasses", {}))
    classes = {
        "Arr.java": {"Arr": parents},
        "Elem.java": {"Elem": extra.pop("elem_parents", [])},
        "I.java": {"I": []},
        "Mid.java": {"Mid": extra.pop("mid_parents", [])},
    }
    methods = dict(_TO_STRING)
    methods.update(extra.pop("methods", {}))
    return jt.JavaTypeIndex(classes=classes, methods=methods, superclasses=superclasses)


def test_superclass_method_wins_over_an_external_interface() -> None:
    index = _index(["Elem", "Iterable"])

    assert jt.find_method(("Arr.java", "Arr"), "toString", _JCTX, index) == (
        "Elem.java",
        50,
        "Elem",
        5,
    )


def test_without_a_known_superclass_an_external_parent_still_refuses() -> None:
    # The same parents, but nothing says which one is the superclass (an index
    # built before #1880): unchanged, nothing binds.
    index = _index(["Elem", "Iterable"], superclass=None)

    assert jt.find_method(("Arr.java", "Arr"), "toString", _JCTX, index) is None


def test_a_method_not_in_the_superclass_chain_still_refuses() -> None:
    # ``forEach`` may come from ``Iterable``: no class in the chain declares it.
    index = _index(["Elem", "Iterable"])

    assert jt.find_method(("Arr.java", "Arr"), "forEach", _JCTX, index) is None


def test_a_project_interface_declaring_the_name_stays_ambiguous() -> None:
    index = _index(
        ["Elem", "I", "Iterable"],
        methods={("I.java", "I"): {"toString": [(2, 20)]}},
    )

    assert jt.find_method(("Arr.java", "Arr"), "toString", _JCTX, index) is None


def test_an_external_superclass_refuses() -> None:
    index = _index(["Outside", "Iterable"], superclass="Outside")

    assert jt.find_method(("Arr.java", "Arr"), "toString", _JCTX, index) is None


def test_the_chain_is_walked_through_intermediate_classes() -> None:
    # Arr extends Mid extends Elem; Mid implements an external interface too.
    index = _index(
        ["Mid", "Iterable"],
        superclass="Mid",
        mid_parents=["Elem", "Comparable"],
        superclasses={("Mid.java", "Mid"): "Elem"},
    )

    assert jt.find_method(("Arr.java", "Arr"), "toString", _JCTX, index) == (
        "Elem.java",
        50,
        "Elem",
        5,
    )


def test_an_unresolved_superclass_above_the_chain_refuses() -> None:
    # Arr extends Mid extends Outside; neither project class declares the name.
    index = _index(
        ["Mid", "Iterable"],
        superclass="Mid",
        mid_parents=["Outside"],
        superclasses={("Mid.java", "Mid"): "Outside"},
        methods={},
    )

    assert jt.find_method(("Arr.java", "Arr"), "hashCode", _JCTX, index) is None


def test_an_overloaded_superclass_method_refuses() -> None:
    index = _index(
        ["Elem", "Iterable"],
        methods={("Elem.java", "Elem"): {"toString": [(5, 50), (6, 60)]}},
    )

    assert jt.find_method(("Arr.java", "Arr"), "toString", _JCTX, index) is None


def test_the_chain_respects_the_depth_limit() -> None:
    index = _index(["Elem", "Iterable"])

    assert (
        jt._superclass_hit(
            ("Arr.java", "Arr"), "toString", _JCTX, index, jt._MAX_DEPTH + 1
        )
        is None
    )


def test_the_type_index_reads_the_superclass() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_symbol_rows (id INTEGER, name TEXT, kind TEXT, "
        "file_path TEXT, line INTEGER)"
    )
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, language TEXT, symbols_json TEXT)"
    )
    symbols = [
        {
            "kind": "class",
            "name": "Arr",
            "parents": ["Elem", "Iterable"],
            "superclass": "Elem",
        },
        {"kind": "class", "name": "I", "parents": ["J"]},
    ]
    conn.execute(
        "INSERT INTO ast_index VALUES ('Arr.java', 'java', ?)",
        (json.dumps({"symbols": symbols}),),
    )
    ctx = SimpleNamespace(cache=SimpleNamespace(get_conn=lambda: conn))

    index = jt.java_type_index(ctx)

    assert index.superclasses == {("Arr.java", "Arr"): "Elem"}
