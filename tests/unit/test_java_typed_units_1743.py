"""#1743：Java 声明类型解析、子类证据与范围回填依赖的分支单元测试（不建索引）。"""

from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from tree_sitter_analyzer.cache import backfill_scope as bs
from tree_sitter_analyzer.call_graph_self_dispatch import (
    SubclassIndex,
    override_candidates,
)
from tree_sitter_analyzer.synapse_resolver import _java_typed as jt
from tree_sitter_analyzer.synapse_resolver._java_context import JavaResolverContext


class _BrokenCache:
    def get_conn(self):
        raise sqlite3.OperationalError("no database")


# --------------------------------------------------------------------------- type index


def test_type_index_tolerates_unreadable_cache_and_bad_rows() -> None:
    broken = SimpleNamespace(cache=_BrokenCache())
    assert jt.java_type_index(broken).classes == {}
    # Cached on the context: the second call returns the same object.
    assert jt.java_type_index(broken) is jt.java_type_index(broken)

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_symbol_rows (id INTEGER, name TEXT, kind TEXT, file_path TEXT, line INTEGER)"
    )
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, language TEXT, symbols_json TEXT)"
    )
    conn.execute("INSERT INTO ast_symbol_rows VALUES (7, 'run', 'method', 'A.java', 3)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, 'java', ?)",
        [
            ("Bad.java", "{not json"),
            (
                "A.java",
                json.dumps(
                    {
                        "symbols": [
                            {"kind": "class", "name": "A", "parents": ["B"]},
                            {"kind": "method", "name": "run", "line": 3, "class": "A"},
                            {
                                "kind": "method",
                                "name": "ghost",
                                "line": 9,
                                "class": "A",
                            },
                            {"kind": "method", "name": "free", "line": 4},
                        ]
                    }
                ),
            ),
        ],
    )
    ctx = SimpleNamespace(cache=SimpleNamespace(get_conn=lambda: conn))
    index = jt.java_type_index(ctx)
    assert index.classes == {"A.java": {"A": ["B"]}}
    # ``ghost`` has no symbol row and ``free`` no class: neither is indexed.
    assert index.methods == {("A.java", "A"): {"run": [(3, 7)]}}


def _jctx(**kwargs) -> JavaResolverContext:
    return JavaResolverContext(**kwargs)


def test_resolve_type_edge_cases() -> None:
    index = jt.JavaTypeIndex(
        classes={"Use.java": {"Use": [], "Local": []}, "A.java": {"A": []}}
    )
    jctx = _jctx(fqn_to_file={"p.A": "A.java"})
    # A class declared in the caller file itself.
    assert jt.resolve_type("Local", "Use.java", jctx, index) == ("Use.java", "Local")
    # Two dots below an unresolvable head: not a project class.
    assert jt.resolve_type("Missing.B.C", "Use.java", jctx, index) is None
    # No package and no imports: nothing to search.
    assert jt.resolve_type("A", "Nowhere.java", jctx, index) is None
    # Ambiguous on-demand imports.
    index2 = jt.JavaTypeIndex(classes={"x/A.java": {"A": []}, "y/A.java": {"A": []}})
    jctx2 = _jctx(
        fqn_to_file={"x.A": "x/A.java", "y.A": "y/A.java"},
        wildcard_pkgs_by_file={"Use.java": ["x", "y"]},
    )
    assert jt.resolve_type("A", "Use.java", jctx2, index2) is None


def test_find_method_depth_limit_and_ambiguous_ancestor() -> None:
    jctx = _jctx(
        file_package={"C.java": "p", "P.java": "p", "Q.java": "p"},
        fqn_to_file={"p.P": "P.java", "p.Q": "Q.java"},
    )
    index = jt.JavaTypeIndex(
        classes={"C.java": {"C": ["P"]}, "P.java": {"P": ["Q"]}, "Q.java": {"Q": []}},
        methods={
            ("Q.java", "Q"): {"m": [(1, 1), (2, 2)]}
        },  # overloaded in the grandparent
    )
    assert (
        jt.find_method(("C.java", "C"), "m", jctx, index, depth=jt._MAX_DEPTH + 1)
        is None
    )
    # The grandparent declares ``m`` twice: the parent branch cannot decide, so nothing binds.
    assert jt.find_method(("C.java", "C"), "m", jctx, index) is None
    assert jt._declares_anywhere(("C.java", "C"), "m", jctx, index, 0) is True
    assert (
        jt._declares_anywhere(("C.java", "C"), "m", jctx, index, jt._MAX_DEPTH + 1)
        is True
    )
    assert jt._declares_anywhere(("Q.java", "Q"), "other", jctx, index, 0) is False
    external = jt.JavaTypeIndex(classes={"E.java": {"E": ["Outside"]}})
    assert jt._declares_anywhere(("E.java", "E"), "m", _jctx(), external, 0) is True


def test_resolve_java_typed_receiver_refusals() -> None:
    no_java = SimpleNamespace(lang_context=lambda _lang: None)
    assert (
        jt.resolve_java_typed_receiver({"type": "A"}, "m", "Use.java", no_java) is None
    )
    assert jt.resolve_java_typed_receiver(None, "m", "Use.java", no_java) is None
    assert (
        jt.resolve_java_typed_receiver({"type": ""}, "m", "Use.java", no_java) is None
    )
    assert (
        jt.resolve_java_typed_receiver({"type": "A"}, "", "Use.java", no_java) is None
    )
    ctx = SimpleNamespace(lang_context=lambda _lang: _jctx(), cache=None)
    ctx._java_type_index = jt.JavaTypeIndex(classes={"Use.java": {"A": []}})
    # The class resolves but declares no ``m``.
    assert jt.resolve_java_typed_receiver({"type": "A"}, "m", "Use.java", ctx) is None
    # The type does not resolve at all.
    assert jt.resolve_java_typed_receiver({"type": "Zed"}, "m", "Use.java", ctx) is None


# --------------------------------------------------------------------------- subclasses


def test_subclass_index_reads_java_placeholders_and_tolerates_failures() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE edges (kind TEXT, source_node_id TEXT, target_node_id TEXT)"
    )
    conn.executemany(
        "INSERT INTO edges VALUES (?, ?, ?)",
        [
            ("extends", "a/Circle.java:Circle:3", "class:com.ex.Shape<T>"),
            ("implements", "a/Square.java:Square:3", "class:Shape"),
            (
                "extends",
                "b/sub.py:Sub:1",
                "class:Base",
            ),  # Python placeholders stay ignored
        ],
    )
    index = SubclassIndex(SimpleNamespace(get_conn=lambda: conn))
    assert index.subclasses("Shape") == {"Circle", "Square"}
    assert index.subclasses("Base") == set()
    # No ast_index table: no anonymous evidence, no exception.
    assert index.anonymous_spans({"Shape"}) == []
    broken = SubclassIndex(_BrokenCache())
    assert broken.subclasses("Shape") == set()
    assert broken.anonymous_spans({"Shape"}) == []


def test_override_candidates_without_anonymous_support() -> None:
    ref = SimpleNamespace(receiver="Circle", file_path="a/Circle.java", start_line=5)
    fake = SimpleNamespace(subclasses=lambda _name: {"Circle"})
    assert override_candidates(fake, {"area": [ref]}, "area", "this", "Shape") == [ref]
    assert override_candidates(fake, {"area": [ref]}, "area", "x", "Shape") == []


# --------------------------------------------------------------------------- backfill scope


def test_java_typed_dependents_follow_subclasses_and_hints() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE edges (kind TEXT, file_path TEXT, source_node_id TEXT, target_node_id TEXT, metadata TEXT)"
    )
    conn.execute(
        f"CREATE TEMP TABLE {bs._EXTENDS} (path TEXT, source TEXT, target TEXT)"
    )
    conn.executemany(
        "INSERT INTO edges VALUES (?, ?, ?, ?, ?)",
        [
            ("extends", "Mid.java", "Mid.java:Mid:1", "Base.java:Base:1", "{}"),
            ("extends", "Leaf.java", "Leaf.java:Leaf:1", "class:Mid", "{}"),
            ("extends", "x.py", "x.py:X:1", "class:Base", "{}"),  # not Java: ignored
            ("extends", "Odd.java", "junk", "class:Base", "{}"),  # unparsable source
            (
                "calls",
                "UseLeaf.java",
                "",
                "",
                json.dumps({"receiver_hint": {"type": "com.ex.Leaf"}}),
            ),
            (
                "calls",
                "UseOther.java",
                "",
                "",
                json.dumps({"receiver_hint": {"type": "Other"}}),
            ),
            ("calls", "Broken.java", "", "", "{receiver_hint"),
        ],
    )
    conn.execute(
        f"INSERT INTO temp.{bs._EXTENDS} VALUES ('Gone.java', 'Gone.java:Gone:1', 'class:Base')"
    )

    found = bs._java_typed_dependents(conn, {"Base"})

    # Leaf reaches Base through Mid; an unreadable hint is re-resolved to be safe.
    assert found == {"UseLeaf.java", "Broken.java"}
    assert bs._java_typed_dependents(conn, set()) == set()
