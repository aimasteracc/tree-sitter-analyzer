"""#1880: Java supertypes with type arguments get an ``extends`` / ``implements`` edge.

``_java_parents`` kept only bare ``type_identifier`` children of the
``extends`` / ``implements`` clauses. A generic supertype (``A<String>``) is a
``generic_type`` node, a qualified one (``pkg.A``) a ``scoped_type_identifier``
and an annotated one (``@Ann A``) an ``annotated_type``, so all of them were
dropped: gson had no ``extends`` edge for any ``TypeAdapter<T>`` subclass.
Interfaces extending other interfaces (``extends_interfaces``) were dropped too.

The parent is recorded as written, with type arguments and type annotations
removed (``pkg.A<T>`` -> ``pkg.A``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tree_sitter_analyzer.cache.extraction import _worker_index_file


def _parents(tmp_path: Path, source: str, name: str) -> list[str]:
    path = tmp_path / "Shapes.java"
    path.write_text(source, encoding="utf-8")
    result = _worker_index_file((str(path), str(tmp_path), "java"))
    assert result["status"] == "ok"
    symbols = json.loads(result["symbols_json"])["symbols"]
    found = [s for s in symbols if s.get("name") == name and s.get("kind") == "class"]
    assert len(found) == 1, found
    return list(found[0].get("parents") or [])


@pytest.mark.parametrize(
    ("source", "name", "expected"),
    [
        pytest.param(
            "class A {}\nclass B extends A {}\n", "B", ["A"], id="plain-extends"
        ),
        pytest.param(
            "class A<T> {}\nclass B extends A<String> {}\n",
            "B",
            ["A"],
            id="generic-extends",
        ),
        pytest.param(
            "class B implements Comparable<B> {}\n",
            "B",
            ["Comparable"],
            id="generic-implements",
        ),
        pytest.param(
            "class B extends A<Map<K, List<V>>> implements I<Map<K, V>>, J {}\n",
            "B",
            ["A", "I", "J"],
            id="nested-generics",
        ),
        pytest.param(
            "class B extends pkg.A<T> implements java.util.List<T>, Outer.In {}\n",
            "B",
            ["pkg.A", "java.util.List", "Outer.In"],
            id="qualified",
        ),
        pytest.param(
            "class B extends @Ann A<T> implements @Ann I, pkg.@Ann J<T> {}\n",
            "B",
            ["A", "I", "pkg.J"],
            id="type-annotations",
        ),
        pytest.param(
            "class B implements I<@NonNull String> {}\n",
            "B",
            ["I"],
            id="annotated-type-argument",
        ),
        pytest.param(
            "interface J extends K<T>, pkg.L<T>, M {}\n",
            "J",
            ["K", "pkg.L", "M"],
            id="interface-extends",
        ),
        pytest.param("record R(int x) implements I<R> {}\n", "R", ["I"], id="record"),
    ],
)
def test_java_supertype_shapes(
    tmp_path: Path, source: str, name: str, expected: list[str]
) -> None:
    assert _parents(tmp_path, source, name) == expected


def test_class_without_supertype_has_no_parents(tmp_path: Path) -> None:
    assert (
        _parents(tmp_path, "class A<T> { A<T> self() { return this; } }\n", "A") == []
    )


#: The #1884 repro: ``B`` and ``C`` override ``A.make`` through ``A<String>``.
_REPRO = {
    "p/A.java": (
        "package p;\n"
        "public abstract class A<T> {\n"
        "  public T run() { return make(); }\n"
        "  protected abstract T make();\n"
        "}\n"
    ),
    "p/B.java": (
        "package p;\n"
        "public class B extends A<String> implements Comparable<B> {\n"
        '  protected String make() { return "b"; }\n'
        "  public int compareTo(B o) { return 0; }\n"
        "}\n"
    ),
}


def test_index_records_generic_supertype_edges(tmp_path: Path) -> None:
    """The persisted index has the edges, and dispatch sees ``B`` as ``A``'s child."""
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.call_graph_self_dispatch import SubclassIndex

    for rel_path, text in _REPRO.items():
        path = tmp_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project(workers=0)
        rows = cache.get_conn().execute(
            "SELECT target_node_id FROM edges "
            "WHERE kind IN ('extends', 'implements') AND file_path = 'p/B.java'"
        )
        targets = sorted(str(row[0]) for row in rows)
        children = SubclassIndex(cache).evidence()
    finally:
        cache.close()
    # Java supertype edges keep the ``class:Name`` placeholder (#1743).
    assert targets == ["class:A", "class:Comparable"]
    assert "B" in children.get("A", set())
