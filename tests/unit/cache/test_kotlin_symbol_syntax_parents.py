"""#1916: Kotlin classes get supertype edges.

There was no Kotlin parent extractor, so no Kotlin class recorded ``parents`` and
the index had no supertype edge for any of them. ``this.make()`` in ``A.run``
therefore never offered an override in ``class B : A<String>()`` as a possible
target, and ``B.make`` answered ``complete`` with 0 callers.

Supertypes are recorded as written, without type arguments, annotations or the
constructor call (``pkg.B<T>(1)`` -> ``pkg.B``). The superclass is recorded only
when Kotlin syntax identifies it: the one supertype called as a constructor.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tree_sitter_analyzer.cache._symbol_syntax import (
    _kotlin_parents,
    _kotlin_type_name,
    kotlin_superclass,
)
from tree_sitter_analyzer.cache.extraction import _worker_index_file


def _symbols(tmp_path: Path, source: str) -> list[dict]:
    path = tmp_path / "Shapes.kt"
    path.write_bytes(source.encode("utf-8"))
    result = _worker_index_file((str(path), str(tmp_path), "kotlin"))
    assert result["status"] == "ok"
    return list(json.loads(result["symbols_json"])["symbols"])


def _symbol(tmp_path: Path, source: str, name: str) -> dict:
    found = [
        s
        for s in _symbols(tmp_path, source)
        if s.get("name") == name and s.get("kind") == "class"
    ]
    assert len(found) == 1, found
    return dict(found[0])


def _parents(tmp_path: Path, source: str, name: str) -> list[str]:
    return list(_symbol(tmp_path, source, name).get("parents") or [])


@pytest.mark.parametrize(
    ("source", "name", "expected"),
    [
        pytest.param("class B : A()\n", "B", ["A"], id="constructor-call"),
        pytest.param(
            "class B<T> : A<Map<K, List<T>>>(1), I<T>, J\n",
            "B",
            ["A", "I", "J"],
            id="generic-and-interfaces",
        ),
        pytest.param(
            "class B : pkg.A<T>(), java.io.Serializable, Outer.In\n",
            "B",
            ["pkg.A", "java.io.Serializable", "Outer.In"],
            id="qualified",
        ),
        pytest.param(
            "class B : @Ann A(), @Ann pkg.I<T>\n",
            "B",
            ["A", "pkg.I"],
            id="annotated",
        ),
        pytest.param(
            "class B(d: I) : I by d, List<String> by emptyList()\n",
            "B",
            ["I", "List"],
            id="delegation",
        ),
        pytest.param(
            "interface I : J, pkg.K<T>\n", "I", ["J", "pkg.K"], id="interface"
        ),
        pytest.param(
            "fun interface F : Runnable\n", "F", ["Runnable"], id="fun-interface"
        ),
        pytest.param(
            "enum class E : I, J {\n    X, Y\n}\n", "E", ["I", "J"], id="enum-class"
        ),
        pytest.param(
            "data class D(val a: Int) : I, Comparable<D>\n",
            "D",
            ["I", "Comparable"],
            id="data-class",
        ),
        pytest.param("sealed class S : B()\n", "S", ["B"], id="sealed-class"),
        pytest.param(
            "abstract class S : B(), I\n", "S", ["B", "I"], id="abstract-class"
        ),
        pytest.param("open class S : B()\n", "S", ["B"], id="open-class"),
        pytest.param(
            "class S : B {\n    constructor() : super()\n}\n",
            "S",
            ["B"],
            id="secondary-constructor",
        ),
        pytest.param(
            "class O {\n    class In : O(), I\n}\n", "In", ["O", "I"], id="nested-class"
        ),
        pytest.param(
            "class O {\n    companion object Factory : F() {\n        fun make() = 1\n"
            "    }\n}\n",
            "Factory",
            ["F"],
            id="named-companion",
        ),
        pytest.param(
            "class F : (Int) -> Int, I {\n    override fun invoke(x: Int) = x\n}\n",
            "F",
            ["I"],
            id="function-type-skipped",
        ),
    ],
)
def test_kotlin_supertype_shapes(
    tmp_path: Path, source: str, name: str, expected: list[str]
) -> None:
    assert _parents(tmp_path, source, name) == expected


@pytest.mark.parametrize(
    ("source", "name", "expected"),
    [
        pytest.param("class B : A(), I\n", "B", "A", id="constructor-call"),
        pytest.param("class B : I, pkg.A<T>(1)\n", "B", "pkg.A", id="class-not-first"),
        pytest.param("class B : @Ann A()\n", "B", "A", id="annotated"),
        # Without a constructor call ``B`` may be a class (initialised by the
        # secondary constructor) or an interface: not recorded.
        pytest.param(
            "class S : B {\n    constructor() : super()\n}\n",
            "S",
            None,
            id="secondary-constructor",
        ),
        pytest.param("class B : I, J\n", "B", None, id="interfaces-only"),
        pytest.param("class B(d: I) : I by d\n", "B", None, id="delegation"),
        pytest.param("interface I : J\n", "I", None, id="interface"),
        pytest.param("enum class E : I {\n    X\n}\n", "E", None, id="enum-class"),
    ],
)
def test_kotlin_superclass_is_recorded_only_when_unambiguous(
    tmp_path: Path, source: str, name: str, expected: str | None
) -> None:
    assert _symbol(tmp_path, source, name).get("superclass") == expected


def test_class_without_supertype_has_no_parents(tmp_path: Path) -> None:
    symbol = _symbol(tmp_path, "class A<T> {\n    fun self(): A<T> = this\n}\n", "A")
    assert "parents" not in symbol
    assert "superclass" not in symbol


def test_object_declarations_are_not_class_symbols(tmp_path: Path) -> None:
    """An ``object`` has no class symbol, so there is nothing to attach an edge to.

    Its members are indexed as top-level functions; making ``object`` a class
    would change how their calls resolve, which is outside #1916.
    """
    symbols = _symbols(tmp_path, "object O : B(), I {\n    fun f() {}\n}\n")
    assert [s for s in symbols if s.get("name") == "O"] == []


def _node(type_: str, *children: object, text: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        type=type_,
        children=list(children),
        named_children=list(children),
        text=text.encode("utf-8"),
    )


def test_malformed_type_nodes_are_skipped() -> None:
    """Incomplete parser nodes give no parent instead of a wrong one."""
    ident = _node("identifier", text="A")
    assert _kotlin_type_name(_node("user_type"), "") is None
    assert _kotlin_type_name(_node("user_type", _node("identifier")), "") is None
    assert _kotlin_type_name(_node("nullable_type", ident), "") is None
    empty_spec = _node("delegation_specifier", _node("annotation"))
    bad_call = _node("constructor_invocation", _node("value_arguments"))
    good = _node("delegation_specifier", _node("user_type", ident))
    specifiers = _node(
        "delegation_specifiers",
        empty_spec,
        _node("delegation_specifier", bad_call),
        _node("delegation_specifier", _node("explicit_delegation")),
        good,
    )
    assert _kotlin_parents(_node("class_declaration", specifiers), "") == ["A"]
    assert (
        kotlin_superclass(
            _node(
                "class_declaration",
                _node("class"),
                _node("delegation_specifiers", _node("delegation_specifier", bad_call)),
            ),
            "",
        )
        is None
    )
    # An ``interface`` never has a superclass, even on a malformed tree.
    call = _node("constructor_invocation", _node("user_type", ident))
    interface = _node(
        "class_declaration",
        _node("interface"),
        _node("delegation_specifiers", _node("delegation_specifier", call)),
    )
    assert kotlin_superclass(interface, "") is None


#: ``this.make()`` in ``A.run`` dispatches to the overrides in ``B`` and ``C``.
_REPRO = {
    "p/A.kt": (
        "package p\n\n"
        "open class A<T> {\n"
        "    fun run(): String {\n"
        "        return this.make()\n"
        "    }\n\n"
        '    open fun make(): String = "a"\n'
        "}\n"
    ),
    "p/B.kt": (
        "package p\n\n"
        "class B : A<String>(), Comparable<B> {\n"
        '    override fun make(): String = "b"\n\n'
        "    override fun compareTo(other: B): Int = 0\n"
        "}\n"
    ),
}


def _write(root: Path, files: dict[str, str]) -> None:
    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))


def test_index_records_kotlin_supertype_edges(tmp_path: Path) -> None:
    """The persisted index has the edges, and dispatch sees ``B`` as ``A``'s child."""
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.call_graph_self_dispatch import SubclassIndex

    _write(tmp_path, _REPRO)
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project(workers=0)
        rows = cache.get_conn().execute(
            "SELECT target_node_id FROM edges "
            "WHERE kind IN ('extends', 'implements') AND file_path = 'p/B.kt'"
        )
        targets = sorted(str(row[0]) for row in rows)
        index = SubclassIndex(cache)
        children = index.evidence()
        subclasses = index.subclasses("A")
    finally:
        cache.close()
    # Cross-file Kotlin supertypes keep the ``class:Name`` placeholder (the
    # second resolution pass handles Python only), as Java's do.
    assert targets == ["class:A", "class:Comparable"]
    assert "B" in children.get("A", set())
    assert subclasses == {"B"}
