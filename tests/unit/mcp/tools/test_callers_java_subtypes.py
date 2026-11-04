"""#1894: a Java method inherited by a subtype that implements another type.

.. code-block:: java

    interface I { void m(); default void run() { m(); } }
    class A { public void m() {} }        // no supertype
    class B extends A implements I {}     // B inherits A.m as I.m

``new B().run()`` calls ``A.m`` through ``I``. The call edge of ``m()`` in
``I.run`` is bound to ``I.m`` and ``A`` has no supertype, so the override proof
never ran for ``A.m``: it answered ``complete`` with 0 callers. (A typed call
``i.m()`` elsewhere was already ``NAME_ONLY_INBOUND``.) The
``supertype_dispatch`` check now also walks the project subtypes of the
declaring type.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_java_overrides import OVERRIDE_REASON
from tree_sitter_analyzer.mcp.tools.callers_java_subtypes import subtype_proof
from tree_sitter_analyzer.mcp.tools.callers_java_supertypes import (
    java_supertype_finding,
)
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

#: The issue's repro.
_REPRO = {
    "p/I.java": (
        "package p;\n"
        "public interface I {\n"
        "  void m();\n"
        "  default void run() { m(); }\n"
        "}\n"
    ),
    "p/A.java": "package p;\npublic class A {\n  public void m() {}\n}\n",
    "p/B.java": "package p;\npublic class B extends A implements I {}\n",
}
#: The unbound call edge of the repro (``m()`` in ``I.run``).
_UNBOUND = [("m", "p/I.java", 4, "local", "p/I.java", None)]

#: Negatives: subtypes that add no type declaring the name.
_PLAIN = {
    "q/J.java": "package q;\npublic interface J {\n  void other();\n}\n",
    "q/A.java": "package q;\npublic class A {\n  public void m() {}\n}\n",
    "q/B.java": (
        "package q;\n"
        "public class B extends A implements J {\n"
        "  public void other() { m(); }\n"
        "}\n"
    ),
    "q/C.java": "package q;\npublic class C extends B implements Cloneable {}\n",
}


async def _index(root, files: dict[str, str]) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    _write(root, files)
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 20}
    )
    assert indexed["published"] is True
    return str(root)


async def _callers(root: str, name: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "include_bodies": False}
    )


def _write(root, files: dict[str, str]) -> str:
    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return str(root)


def _line_of(text: str, needle: str) -> int:
    return next(i for i, line in enumerate(text.split("\n"), 1) if needle in line)


class _Cache:
    """A minimal index: Java classes, methods and call edges."""

    def __init__(self, classes=(), methods=(), edges=()) -> None:
        import sqlite3

        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE ast_symbol_rows (name TEXT, kind TEXT, file_path TEXT, "
            "language TEXT, line INTEGER)"
        )
        self.conn.execute(
            "CREATE TABLE edges (kind TEXT, callee_name TEXT, file_path TEXT, line "
            "INTEGER, callee_resolution TEXT, callee_resolved_file TEXT, metadata TEXT)"
        )
        for name, file in classes:
            self.conn.execute(
                "INSERT INTO ast_symbol_rows VALUES (?, 'class', ?, 'java', 1)",
                (name, file),
            )
        for name, file in methods:
            self.conn.execute(
                "INSERT INTO ast_symbol_rows VALUES (?, 'method', ?, 'java', 1)",
                (name, file),
            )
        for row in edges:
            self.conn.execute(
                "INSERT INTO edges VALUES ('calls', ?, ?, ?, ?, ?, ?)", row
            )

    def get_conn(self):
        return self.conn


def _classes(files: dict[str, str]) -> list[tuple[str, str]]:
    import re

    found = []
    for rel, text in files.items():
        for name in re.findall(r"(?:class|interface|enum|record)\s+(\w+)", text):
            found.append((name, rel))
    return found


def _finding(tmp_path, files, rel, needle, bare, edges=(), owner=""):
    root = _write(tmp_path, files)
    line = _line_of(files[rel], needle)
    cache = _Cache(classes=_classes(files), edges=edges)
    return java_supertype_finding(root, [(rel, line, "java")], bare, cache, owner)


# --- end to end ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_repro_inherited_implementation_is_not_complete(tmp_path) -> None:
    root = await _index(tmp_path, _REPRO)

    result = await _callers(root, "A.m")

    assert result["caller_count"] == 0
    assert result["completeness"] == "unknown", result
    assert result["completeness_reasons"] == [OVERRIDE_REASON]
    assert "p/I.java:4" in result["next_step"]
    assert "`B`" in result["next_step"]


@pytest.mark.asyncio
async def test_subtypes_adding_no_declaring_type_stay_complete(tmp_path) -> None:
    root = await _index(tmp_path, _PLAIN)

    result = await _callers(root, "A.m")

    assert result["completeness"] == "complete", result
    assert result["caller_count"] == 1


# --- the source-level finding -------------------------------------------------


def test_bound_call_edges_let_it_pass(tmp_path) -> None:
    edges = [("m", "p/I.java", 4, "external", "", None)]

    found = _finding(tmp_path, _REPRO, "p/A.java", "void m", "m", edges)

    assert found is None


def test_unbound_call_edge_is_found(tmp_path) -> None:
    found = _finding(tmp_path, _REPRO, "p/A.java", "void m", "m", _UNBOUND)

    assert found is not None
    assert found.reason == OVERRIDE_REASON
    assert "`B`" in found.describe()
    assert "`I.m`" in found.describe()
    assert "p/I.java:4" in found.describe()


def test_transitive_subtype_and_inherited_interface_are_found(tmp_path) -> None:
    files = {
        "p/I.java": "package p;\npublic interface I {\n  void m();\n}\n",
        "p/K.java": "package p;\npublic interface K extends I {}\n",
        "p/A.java": "package p;\npublic class A {\n  public void m() {}\n}\n",
        "p/B.java": "package p;\npublic class B extends A {}\n",
        "p/C.java": "package p;\npublic class C extends B implements K {}\n",
    }
    edges = [("m", "p/U.java", 3, "annotated_receiver", "p/I.java", None)]

    found = _finding(tmp_path, files, "p/A.java", "void m", "m", edges)

    assert found is not None
    assert "`C`" in found.describe()


def test_generic_and_nested_subtypes_are_found(tmp_path) -> None:
    files = {
        "p/I.java": "package p;\npublic interface I {\n  void m();\n}\n",
        "p/A.java": "package p;\npublic class A<T> {\n  public void m() {}\n}\n",
        "p/O.java": (
            "package p;\n"
            "public class O {\n"
            "  static class B extends A<String> implements I {}\n"
            "}\n"
        ),
    }
    edges = [("m", "p/U.java", 3, "unresolved", "", None)]

    found = _finding(tmp_path, files, "p/A.java", "void m", "m", edges)

    assert found is not None
    assert "`B`" in found.describe()


def test_jdk_interface_on_a_subtype_is_found(tmp_path) -> None:
    files = {
        "p/A.java": "package p;\npublic class A {\n  public void run() {}\n}\n",
        "p/B.java": "package p;\npublic class B extends A implements Runnable {}\n",
    }

    found = _finding(tmp_path, files, "p/A.java", "void run", "run")

    assert found is not None
    assert "java.lang.Runnable" in found.describe()


def test_unresolved_supertype_of_a_subtype_is_found(tmp_path) -> None:
    files = {
        "p/A.java": "package p;\npublic class A {\n  public void m() {}\n}\n",
        "p/B.java": (
            "package p;\nimport x.Ext;\npublic class B extends A implements Ext {}\n"
        ),
    }

    found = _finding(tmp_path, files, "p/A.java", "void m", "m")

    assert found is not None
    assert "Ext" in found.describe()


def test_qualified_reference_to_the_type_is_found(tmp_path) -> None:
    files = {
        "p/A.java": "package p;\npublic class A {\n  public void m() {}\n}\n",
        "r/B.java": "package r;\npublic class B extends p.A {}\n",
    }

    found = _finding(tmp_path, files, "p/A.java", "void m", "m")

    assert found is not None
    assert "p.A" in found.describe()


def test_other_type_of_the_same_name_is_not_a_subtype(tmp_path) -> None:
    files = {
        "p/A.java": "package p;\npublic class A {\n  public void m() {}\n}\n",
        "r/A.java": "package r;\npublic class A {}\n",
        "r/I.java": "package r;\npublic interface I {\n  void m();\n}\n",
        "r/B.java": "package r;\npublic class B extends A implements I {}\n",
    }
    edges = [("m", "p/U.java", 3, "unresolved", "", None)]

    found = _finding(tmp_path, files, "p/A.java", "void m", "m", edges)

    assert found is None


def test_abstract_and_interface_methods_are_skipped(tmp_path) -> None:
    files = {
        "p/I.java": "package p;\npublic interface I {\n  void m();\n}\n",
        "p/A.java": "package p;\npublic abstract class A {\n  public abstract void m();\n}\n",
        "p/B.java": "package p;\npublic abstract class B extends A implements I {}\n",
    }
    edges = [("m", "p/U.java", 3, "unresolved", "", None)]

    found = _finding(tmp_path, files, "p/A.java", "void m", "m", edges)

    assert found is None


def test_proof_without_index_fails(tmp_path) -> None:
    root = _write(tmp_path, _REPRO)
    text = _REPRO["p/A.java"]

    _subtype, proof = subtype_proof(
        None, root, "p/A.java", text, _line_of(text, "void m"), "m"
    )

    assert not proof.proved


# --- fail-closed paths ----------------------------------------------------------


def _proof(tmp_path, files, rel, needle, bare, cache):
    root = _write(tmp_path, files)
    text = files[rel]
    return subtype_proof(cache, root, rel, text, _line_of(text, needle), bare)


def test_unparsable_declaring_text_fails(tmp_path) -> None:
    root = _write(tmp_path, _REPRO)

    _subtype, proof = subtype_proof(_Cache(), root, "p/A.java", "class {", 1, "m")

    assert not proof.proved
    assert "parsed" in proof.detail


def test_unlocated_declaration_fails(tmp_path) -> None:
    _subtype, proof = _proof(tmp_path, _REPRO, "p/A.java", "class A", "zz", _Cache())

    assert not proof.proved
    assert "located" in proof.detail


@pytest.mark.parametrize(
    "text",
    [
        "package p;\npublic final class A implements Cloneable {\n  public void m() {}\n}\n",
        "package p;\npublic enum A {\n  X;\n  public void m() {}\n}\n",
    ],
)
def test_final_classes_and_enums_have_no_subtypes_to_walk(tmp_path, text) -> None:
    files = {**_REPRO, "p/A.java": text}

    _subtype, proof = _proof(tmp_path, files, "p/A.java", "void m", "m", _Cache())

    assert proof.proved


def test_unreadable_call_edges_fail(tmp_path) -> None:
    class _NoEdges(_Cache):
        def __init__(self) -> None:
            super().__init__(classes=_classes(_REPRO))
            self.conn.execute("DROP TABLE edges")

    _subtype, proof = _proof(tmp_path, _REPRO, "p/A.java", "void m", "m", _NoEdges())

    assert not proof.proved
    assert "call edges" in proof.detail


def test_unreadable_type_rows_fail(tmp_path) -> None:
    cache = _Cache()
    cache.conn.execute("DROP TABLE ast_symbol_rows")

    _subtype, proof = _proof(tmp_path, _REPRO, "p/A.java", "void m", "m", cache)

    assert not proof.proved
    assert "types could not be read" in proof.detail


def test_unreadable_candidate_file_fails(tmp_path) -> None:
    cache = _Cache(classes=[*_classes(_REPRO), ("Gone", "p/Gone.java")])

    _subtype, proof = _proof(tmp_path, _REPRO, "p/A.java", "void m", "m", cache)

    assert not proof.proved
    assert "p/Gone.java" in proof.detail


def test_unparsable_candidate_file_fails(tmp_path) -> None:
    files = {**_REPRO, "p/Bad.java": "package p;\nclass Bad extends A { void x( }\n"}

    found = _finding(tmp_path, files, "p/A.java", "void m", "m")

    assert found is not None
    assert "p/Bad.java" in found.describe()


def test_too_many_subtypes_fail(tmp_path, monkeypatch) -> None:
    from tree_sitter_analyzer.mcp.tools import callers_java_subtypes

    monkeypatch.setattr(callers_java_subtypes, "_MAX_SUBTYPES", 1)

    found = _finding(tmp_path, _PLAIN, "q/A.java", "void m", "m")

    assert found is not None
    assert "too many subtypes" in found.describe()


def test_nested_generic_arguments_are_stripped(tmp_path) -> None:
    files = {
        **_REPRO,
        "p/A.java": "package p;\npublic class A<T> {\n  public void m() {}\n}\n",
        "p/B.java": (
            "package p;\nimport java.util.List;\n"
            "public class B extends A<List<String>> implements I {}\n"
        ),
    }

    found = _finding(tmp_path, files, "p/A.java", "void m", "m", _UNBOUND)

    assert found is not None
    assert "`B`" in found.describe()


def test_import_of_another_type_of_the_name_is_not_a_subtype(tmp_path) -> None:
    files = {
        **_REPRO,
        "p/B.java": "package p;\nimport x.A;\npublic class B extends A implements I {}\n",
    }

    found = _finding(tmp_path, files, "p/A.java", "void m", "m", _UNBOUND)

    assert found is None


def test_import_of_the_name_from_the_target_package_still_fails(tmp_path) -> None:
    files = {
        **_REPRO,
        "r/B.java": (
            "package r;\nimport p.A;\nimport p.A;\npublic class B extends A {}\n"
        ),
        "r/A.java": "package r;\npublic class A {}\n",
        "s/A.java": "package p;\npublic class A {}\n",
    }

    found = _finding(tmp_path, files, "p/A.java", "void m", "m", _UNBOUND)

    assert found is not None
    assert "may extend it" in found.describe()
