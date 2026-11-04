"""#1884: a Java method that overrides a supertype method without ``@Override``.

``@Override`` is optional. The override gate of PR-2 ran only on annotated
methods, so ``B.make`` (``class B extends A<String>``, no annotation) answered
``complete`` with 0 callers, although ``make()`` in ``A.run`` dispatches to it.
The ``supertype_dispatch`` check now runs the same proof for every non-static,
non-private Java method whose declaring type (named or anonymous) has a
supertype, and for every method named like a ``java.lang.Object`` method.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_java_overrides import OVERRIDE_REASON
from tree_sitter_analyzer.mcp.tools.callers_java_supertypes import (
    java_supertype_finding,
)
from tree_sitter_analyzer.mcp.tools.callers_outcomes import Checked, NotChecked
from tree_sitter_analyzer.mcp.tools.callers_supertypes import (
    DYNAMIC_SUPERTYPE_REASON,
    dynamic_supertype_hint,
    supertype_outcome,
)
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

#: The issue's repro.
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
        "public class B extends A<String> {\n"
        '  protected String make() { return "b"; }\n'
        "}\n"
    ),
    "p/C.java": (
        "package p;\n"
        "public class C extends A<String> {\n"
        "  @Override\n"
        '  protected String make() { return "c"; }\n'
        "}\n"
    ),
    "p/D.java": (
        "package p;\n"
        "public class D {\n"
        "  A<String> x = new A<String>() {\n"
        '    protected String make() { return "d"; }\n'
        "  };\n"
        "}\n"
    ),
}

#: Negatives: methods that override nothing stay provable.
_PLAIN = {
    "q/Root.java": (
        "package q;\n"
        "public class Root {\n"
        "  public int rootOnly() { return 1; }\n"
        "  public int use() { return rootOnly(); }\n"
        "}\n"
    ),
    "q/Sub.java": (
        "package q;\n"
        "public class Sub extends Root {\n"
        "  public int subOnly() { return 2; }\n"
        "  public static int helper() { return 3; }\n"
        "  private int secret() { return 4; }\n"
        "  public int useAll() { return secret() + helper(); }\n"
        "}\n"
    ),
}


async def _index(root, files: dict[str, str]) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
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
    """A minimal index for the source-level finding (classes and call edges)."""

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


def _finding(tmp_path, files, rel, needle, bare, cache=None, owner=""):
    root = _write(tmp_path, files)
    line = _line_of(files[rel], needle)
    return java_supertype_finding(
        root, [(rel, line, "java")], bare, cache if cache else _Cache(), owner
    )


# --- end to end ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_unannotated_override_of_a_generic_supertype_is_not_complete(
    tmp_path,
) -> None:
    root = await _index(tmp_path, _REPRO)

    result = await _callers(root, "B.make")

    assert result["caller_count"] == 0
    assert result["completeness"] == "unknown"
    assert result["completeness_reasons"] == [OVERRIDE_REASON]
    assert "p/A.java:3" in result["next_step"]
    assert "carries `@Override`" not in result["next_step"]


@pytest.mark.asyncio
async def test_repro_annotated_override_and_the_base_are_unchanged(tmp_path) -> None:
    root = await _index(tmp_path, _REPRO)

    annotated = await _callers(root, "C.make")
    base = await _callers(root, "A.make")

    assert annotated["completeness"] == "unknown"
    assert annotated["completeness_reasons"] == [OVERRIDE_REASON]
    assert base["completeness"] == "complete"
    assert base["caller_count"] == 1


@pytest.mark.asyncio
async def test_methods_that_override_nothing_stay_complete(tmp_path) -> None:
    root = await _index(tmp_path, _PLAIN)

    for name in ("Root.rootOnly", "Sub.subOnly", "Sub.helper", "Sub.secret"):
        result = await _callers(root, name)
        assert result["completeness"] == "complete", (name, result)


# --- the source-level finding -------------------------------------------------


def test_anonymous_class_method_without_override_is_found(tmp_path) -> None:
    cache = _Cache(
        classes=[("A", "p/A.java"), ("D", "p/D.java")],
        edges=[("make", "p/A.java", 3, "local", "p/A.java", None)],
    )

    found = _finding(tmp_path, _REPRO, "p/D.java", '"d"', "make", cache)

    assert found is not None
    assert found.reason == OVERRIDE_REASON
    assert "p/A.java:3" in found.describe()


def test_object_method_name_without_supertype_is_found(tmp_path) -> None:
    files = {
        "p/V.java": (
            "package p;\n"
            "public class V {\n"
            '  public String toString() { return "v"; }\n'
            "}\n"
        )
    }

    found = _finding(tmp_path, files, "p/V.java", "toString", "toString")

    assert found is not None
    assert "java.lang.Object" in found.describe()


def test_external_supertype_is_found(tmp_path) -> None:
    files = {
        "p/R.java": (
            "package p;\n"
            "public class R implements Runnable {\n"
            "  public void run() {}\n"
            "}\n"
        )
    }

    found = _finding(tmp_path, files, "p/R.java", "void run", "run")

    assert found is not None
    assert "Runnable" in found.describe()


def test_new_method_under_closed_supertype_passes(tmp_path) -> None:
    cache = _Cache(classes=[("Root", "q/Root.java"), ("Sub", "q/Sub.java")])

    found = _finding(tmp_path, _PLAIN, "q/Sub.java", "subOnly", "subOnly", cache)

    assert found is None


@pytest.mark.parametrize("needle", ["static int helper", "private int secret"])
def test_static_and_private_methods_pass(tmp_path, needle) -> None:
    files = {
        "p/S.java": (
            "package p;\n"
            "public class S implements Runnable {\n"
            "  public static int helper() { return 3; }\n"
            "  private int secret() { return 4; }\n"
            "  public void run() {}\n"
            "}\n"
        )
    }
    bare = "helper" if "helper" in needle else "secret"

    assert _finding(tmp_path, files, "p/S.java", needle, bare) is None


def test_constructor_and_field_rows_pass(tmp_path) -> None:
    files = {
        "p/K.java": (
            "package p;\n"
            "public class K implements Runnable {\n"
            "  int K = 1;\n"
            "  K() {}\n"
            "  public void run() {}\n"
            "}\n"
        )
    }
    root = _write(tmp_path, files)

    assert (
        java_supertype_finding(root, [("p/K.java", 4, "java")], "K", _Cache()) is None
    )
    assert (
        java_supertype_finding(root, [("p/K.java", 3, "java")], "K", _Cache()) is None
    )


def test_unparsable_file_is_unchecked(tmp_path) -> None:
    files = {"p/E.java": "package p;\npublic class E extends A {\n  void m( {}\n"}
    root = _write(tmp_path, files)

    found = java_supertype_finding(root, [("p/E.java", 3, "java")], "m", _Cache())

    assert found is not None
    assert found.unchecked is True


def test_missing_file_is_unchecked(tmp_path) -> None:
    found = java_supertype_finding(
        str(tmp_path), [("p/Gone.java", 3, "java")], "m", _Cache()
    )

    assert found is not None
    assert found.unchecked is True


def test_no_index_is_found(tmp_path) -> None:
    root = _write(tmp_path, _PLAIN)
    line = _line_of(_PLAIN["q/Sub.java"], "subOnly")

    found = java_supertype_finding(
        root, [("q/Sub.java", line, "java")], "subOnly", None
    )

    assert found is not None
    assert found.reason == OVERRIDE_REASON


def test_rows_of_other_classes_are_skipped_for_a_qualified_target(tmp_path) -> None:
    files = {
        "p/N.java": (
            "package p;\n"
            "public class N {\n"
            "  int go() { return 1; }\n"
            "  static class In implements java.util.EventListener {\n"
            "    public void run() {}\n"
            "    void go() {}\n"
            "  }\n"
            "}\n"
        )
    }
    root = _write(tmp_path, files)
    rows = [("p/N.java", 3, "java"), ("p/N.java", 6, "java")]

    assert java_supertype_finding(root, rows, "go", _Cache(), "N") is None
    assert java_supertype_finding(root, rows, "go", _Cache(), "In") is not None
    assert java_supertype_finding(root, rows, "go", _Cache(), "") is not None


def test_supertype_outcome_reports_override_dispatch(tmp_path) -> None:
    root = _write(tmp_path, _REPRO)
    line = _line_of(_REPRO["p/B.java"], '"b"')
    cache = _Cache(
        classes=[("A", "p/A.java"), ("B", "p/B.java")],
        edges=[("make", "p/A.java", 3, "local", "p/A.java", None)],
    )
    scope = ("B.make", None)

    outcome, finding = supertype_outcome(
        scope, root, [("p/B.java", line, "java")], "make", cache, "B"
    )

    assert isinstance(outcome, Checked)
    assert outcome.problems == (OVERRIDE_REASON,)
    assert finding is not None
    hint = dynamic_supertype_hint("B.make", finding)
    assert "p/A.java:3" in hint


def test_unchecked_java_finding_is_not_checked(tmp_path) -> None:
    outcome, finding = supertype_outcome(
        ("m", None), str(tmp_path), [("p/Gone.java", 3, "java")], "m", _Cache()
    )

    assert isinstance(outcome, NotChecked)
    assert outcome.reason == DYNAMIC_SUPERTYPE_REASON
    assert finding is not None


# --- known JDK supertypes -----------------------------------------------------

_JDK_FILES = {
    "p/X.java": (
        "package p;\n"
        "import java.io.Closeable;\n"
        "import java.io.Serializable;\n"
        "public class X implements Cloneable, Closeable, Serializable {\n"
        "  public X withVersion() { return this; }\n"
        "  public void close() {}\n"
        "  Object readResolve() { return this; }\n"
        "}\n"
    ),
}


def test_jdk_type_without_the_name_ends_the_walk(tmp_path) -> None:
    found = _finding(tmp_path, _JDK_FILES, "p/X.java", "withVersion", "withVersion")

    assert found is None


@pytest.mark.parametrize(
    ("needle", "bare", "qualified"),
    [
        ("void close", "close", "java.io.Closeable.close"),
        ("readResolve", "readResolve", "java.io.Serializable.readResolve"),
    ],
)
def test_jdk_type_with_the_name_is_found(tmp_path, needle, bare, qualified) -> None:
    found = _finding(tmp_path, _JDK_FILES, "p/X.java", needle, bare)

    assert found is not None
    assert f"`{qualified}`" in found.describe()


def test_project_type_shadowing_a_jdk_name_fails(tmp_path) -> None:
    cache = _Cache(classes=[("Cloneable", "z/Cloneable.java")])
    files = {
        **_JDK_FILES,
        "z/Cloneable.java": "package z;\npublic interface Cloneable {}\n",
    }

    found = _finding(tmp_path, files, "p/X.java", "withVersion", "withVersion", cache)

    assert found is not None
    assert "`Cloneable` is outside the project" in found.describe()


def test_jdk_name_outside_java_lang_needs_its_import(tmp_path) -> None:
    files = {
        "p/X.java": _JDK_FILES["p/X.java"].replace("import java.io.Closeable;\n", "")
    }

    found = _finding(tmp_path, files, "p/X.java", "withVersion", "withVersion")

    assert found is not None
    assert "`Closeable` is outside the project" in found.describe()
