"""RFC-0008 RED-first: Java stdlib/external method names classify as
stdlib/external, not unknown — mirroring RFC-0004/0005 for Python.

The cascade's stdlib/external method tiers, generalized to dispatch on the
caller's language, classify a bare Java method name that survives every
project-binding rule (``add``, ``get``, ``split``, ``verify``, …) as
``stdlib``/``external`` — but ONLY when the project defines no
compatible-language method of that name (shadowing preserved; ambiguous
project names stay ``unknown``).

The mandatory cross-language gate: a name that lives ONLY in Python's table
must NOT classify a Java caller, and a name in Java's table must NOT classify
a Python caller, because ``languages_compatible('java', 'python')`` is False.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tree_sitter_analyzer.ast_cache import ASTCache


def _index(tmp_path: Path, files: dict[str, str]) -> Path:
    """Index a mixed-language project rooted at ``tmp_path``.

    Files are written verbatim at the project root (Java has no ``__init__``
    package convention), so ``.java`` and ``.py`` files coexist exactly as a
    polyglot repository would have them.
    """
    for name, body in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()
    return tmp_path


def _resolution_for(db_path: str, callee_name: str) -> list[str]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT callee_resolution FROM edges "
            "WHERE kind = 'calls' AND callee_name = ?",
            (callee_name,),
        ).fetchall()
        return [r["callee_resolution"] for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# stdlib method tier
# ---------------------------------------------------------------------------
def test_java_stdlib_method_classifies_as_stdlib(tmp_path: Path) -> None:
    """``list.add(x)`` with no project ``add`` → stdlib, not unknown."""
    _index(
        tmp_path,
        {
            "Service.java": (
                "import java.util.List;\n"
                "class Service {\n"
                "    void caller(List<String> list) {\n"
                '        list.add("x");\n'
                "    }\n"
                "}\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "add")
    assert res, "expected an add() edge"
    assert "stdlib" in res, (
        f"Java list.add must classify as stdlib (RFC-0008 tier); got {res}"
    )
    assert "unknown" not in res


def test_java_project_method_shadows_stdlib_name(tmp_path: Path) -> None:
    """A Java class defining ``add`` → ``adder.add()`` resolves project, not
    stdlib (shadowing preserved)."""
    _index(
        tmp_path,
        {
            "Adder.java": (
                "class Adder {\n"
                "    int add() { return 1; }\n"
                "    void caller() {\n"
                "        Adder adder = new Adder();\n"
                "        adder.add();\n"
                "    }\n"
                "}\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "add")
    assert res, "expected an add() edge"
    assert "stdlib" not in res, (
        f"project-defined Java add must NOT be classified stdlib; got {res}"
    )


def test_java_ambiguous_project_method_stays_unknown(tmp_path: Path) -> None:
    """Two Java classes define ``add`` → a bare ``add()`` stays unknown,
    never falsely claimed stdlib."""
    _index(
        tmp_path,
        {
            "Pair.java": (
                "class A {\n"
                "    int add() { return 1; }\n"
                "}\n"
                "class B {\n"
                "    int add() { return 2; }\n"
                "}\n"
                "class Caller {\n"
                "    void caller(Object obj) {\n"
                "        obj.add();\n"
                "    }\n"
                "}\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "add")
    assert res, "expected an add() edge"
    assert "stdlib" not in res, (
        f"ambiguous project method add must stay unknown, not stdlib; got {res}"
    )


def test_cross_language_python_table_does_not_classify_java_caller(
    tmp_path: Path,
) -> None:
    """CRITICAL cross-language gate: a Java ``str.split()`` must still resolve
    to (Java) stdlib even though a Python file defines a method ``split`` — the
    Python symbol does NOT suppress Java's stdlib table because
    ``languages_compatible('java', 'python')`` is False."""
    _index(
        tmp_path,
        {
            "Service.java": (
                "class Service {\n"
                "    void caller(String str) {\n"
                '        str.split(",");\n'
                "    }\n"
                "}\n"
            ),
            "splitter.py": (
                "class MySplitter:\n    def split(self):\n        return 1\n"
            ),
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "split")
    assert "stdlib" in res, (
        "Java str.split must classify stdlib despite a Python split symbol; "
        f"languages_compatible('java','python') is False. got {res}"
    )


# ---------------------------------------------------------------------------
# external method tier
# ---------------------------------------------------------------------------
def test_java_external_method_classifies_as_external(tmp_path: Path) -> None:
    """A Java test ``mock.verify(...)`` with no project ``verify`` → external
    (Mockito), not unknown."""
    _index(
        tmp_path,
        {
            "ServiceTest.java": (
                "class ServiceTest {\n"
                "    void test(Object mock) {\n"
                "        verify(mock);\n"
                "    }\n"
                "}\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "verify")
    assert res, "expected a verify() edge"
    assert "external" in res, (
        f"Java Mockito verify must classify as external; got {res}"
    )


def test_java_project_method_shadows_external_name(tmp_path: Path) -> None:
    """A Java class defining ``verify`` → ``v.verify()`` resolves project, not
    external (shadowing preserved)."""
    _index(
        tmp_path,
        {
            "MockValidator.java": (
                "class MockValidator {\n"
                "    boolean verify() { return true; }\n"
                "    void caller() {\n"
                "        MockValidator v = new MockValidator();\n"
                "        v.verify();\n"
                "    }\n"
                "}\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "verify")
    assert res, "expected a verify() edge"
    assert "external" not in res, (
        f"project-defined Java verify must NOT be classified external; got {res}"
    )


def test_cross_language_python_external_does_not_classify_java_caller(
    tmp_path: Path,
) -> None:
    """A Java ``obj.assert_called_once()`` must NOT be classified external from
    Python's external table (``assert_called_once`` is a unittest.mock name).
    ``languages_compatible('java','python')`` is False, so the Python external
    table is invisible to a Java caller → the edge stays unknown."""
    _index(
        tmp_path,
        {
            "Service.java": (
                "class Service {\n"
                "    void caller(Object obj) {\n"
                "        obj.assert_called_once();\n"
                "    }\n"
                "}\n"
            ),
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "assert_called_once")
    assert res, "expected an assert_called_once() edge"
    assert "external" not in res, (
        f"a Python external-table name must NOT classify a Java caller; got {res}"
    )
