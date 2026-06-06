"""RFC-0008 RED-first: Java stdlib/external method names classify as
stdlib/external, not unknown — mirroring RFC-0004/0005 for Python.

The cascade's stdlib/external method tiers, generalized to dispatch on the
caller's language, classify a bare Java method name that survives every
project-binding rule (``substring``, ``containsKey``, ``verify``, …) as
``stdlib``/``external`` — but ONLY when the project defines no
compatible-language method of that name (shadowing preserved; ambiguous
project names stay ``unknown``). Per the Codex P2 #326 PRECISION re-curation,
generic verbs (``add``/``get``/``put``/``map``/``split``/...) are DROPPED from
the tables so a non-JDK receiver (e.g. Guava ``Cache.get``) stays ``unknown``.

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
    """``s.substring(1)`` with no project ``substring`` → stdlib, not unknown.
    ``substring`` lives on the ``final`` ``java.lang.String`` (no domain subtype,
    not a ``CharSequence`` interface method), so it survives the PRECISION
    curation — unlike the dropped generic CRUD/interface names
    (``add``/``get``/``stream``/``containsKey``…) that domain & third-party
    objects routinely define (Codex P2 #326, review P1)."""
    _index(
        tmp_path,
        {
            "Service.java": (
                "class Service {\n"
                "    void caller(String s) {\n"
                "        s.substring(1);\n"
                "    }\n"
                "}\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "substring")
    assert res, "expected a substring() edge"
    assert "stdlib" in res, (
        f"Java s.substring must classify as stdlib (RFC-0008 tier); got {res}"
    )
    assert "unknown" not in res


def test_java_optional_method_classifies_as_stdlib(tmp_path: Path) -> None:
    """``opt.orElseThrow()`` with no project ``orElseThrow`` → stdlib. Covers the
    Optional half of the table (vavr ``Option`` uses ``getOrElseThrow``, not
    ``orElseThrow``, so the name is distinctively ``java.util.Optional``)."""
    _index(
        tmp_path,
        {
            "Service.java": (
                "import java.util.Optional;\n"
                "class Service {\n"
                "    void caller(Optional<String> opt) {\n"
                "        opt.orElseThrow();\n"
                "    }\n"
                "}\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "orElseThrow")
    assert res, "expected an orElseThrow() edge"
    assert "stdlib" in res, (
        f"Java opt.orElseThrow must classify as stdlib (RFC-0008 tier); got {res}"
    )


def test_java_project_method_shadows_stdlib_name(tmp_path: Path) -> None:
    """A Java class defining ``substring`` → ``box.substring()`` resolves
    project, not stdlib (shadowing preserved). Uses a KEPT name so the gate is
    actually exercised against a surviving stdlib entry."""
    _index(
        tmp_path,
        {
            "TextBox.java": (
                "class TextBox {\n"
                '    String substring() { return ""; }\n'
                "    void caller() {\n"
                "        TextBox box = new TextBox();\n"
                "        box.substring();\n"
                "    }\n"
                "}\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "substring")
    assert res, "expected a substring() edge"
    assert "stdlib" not in res, (
        f"project-defined Java substring must NOT be classified stdlib; got {res}"
    )


def test_java_ambiguous_project_method_stays_unknown(tmp_path: Path) -> None:
    """Two Java classes define ``substring`` → a bare ``substring()`` stays
    unknown, never falsely claimed stdlib. Uses a KEPT name so ambiguity is
    tested against a surviving stdlib entry."""
    _index(
        tmp_path,
        {
            "Pair.java": (
                "class A {\n"
                '    String substring() { return "a"; }\n'
                "}\n"
                "class B {\n"
                '    String substring() { return "b"; }\n'
                "}\n"
                "class Caller {\n"
                "    void caller(Object obj) {\n"
                "        obj.substring();\n"
                "    }\n"
                "}\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "substring")
    assert res, "expected a substring() edge"
    assert "stdlib" not in res, (
        f"ambiguous project method substring must stay unknown, not stdlib; got {res}"
    )


def test_cross_language_python_table_does_not_classify_java_caller(
    tmp_path: Path,
) -> None:
    """CRITICAL cross-language gate: a Java ``str.substring(1)`` must still
    resolve to (Java) stdlib even though a Python file defines a method
    ``substring`` — the Python symbol does NOT suppress Java's stdlib table
    because ``languages_compatible('java', 'python')`` is False. ``substring``
    is a KEPT distinctively-JDK name (Codex P2 #326)."""
    _index(
        tmp_path,
        {
            "Service.java": (
                "class Service {\n"
                "    void caller(String str) {\n"
                "        str.substring(1);\n"
                "    }\n"
                "}\n"
            ),
            "substringer.py": (
                "class MySubstringer:\n    def substring(self):\n        return 1\n"
            ),
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "substring")
    assert "stdlib" in res, (
        "Java str.substring must classify stdlib despite a Python substring "
        f"symbol; languages_compatible('java','python') is False. got {res}"
    )


def test_java_dropped_generic_method_stays_unknown(tmp_path: Path) -> None:
    """Codex P2 #326 regression lock: a Java ``cache.get(k)`` with no project
    ``get`` must stay UNKNOWN, never ``stdlib``.

    ``get`` is a generic verb that domain and third-party objects (e.g. Guava
    ``Cache`` — NOT the JDK) routinely define. The name tiers carry no
    receiver-type evidence, so labelling it ``stdlib`` was a false positive; the
    PRECISION re-curation DROPPED ``get`` (and add/put/set/remove/contains/
    map/filter/...) from ``STDLIB_METHODS_JAVA`` so such calls fall through to
    unknown instead of being mislabelled JDK."""
    _index(
        tmp_path,
        {
            "Service.java": (
                "class Service {\n"
                "    void caller(Cache cache, String k) {\n"
                "        cache.get(k);\n"
                "    }\n"
                "}\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "get")
    assert res, "expected a get() edge"
    assert "stdlib" not in res, (
        "dropped generic name get on a non-JDK receiver (Guava Cache) must NOT "
        f"be classified stdlib (Codex P2 #326); got {res}"
    )
    assert "unknown" in res, (
        f"cache.get with no project get must stay unknown; got {res}"
    )


def test_java_interface_method_stays_unknown(tmp_path: Path) -> None:
    """Review P1 regression lock: ``flux.stream()`` must stay UNKNOWN, never
    ``stdlib``.

    ``stream``/``parallelStream`` are ``java.util.Collection`` **default
    interface** methods — every Reactor ``Flux``, Guava ``ImmutableList``, Spring
    Data ``Streamable`` and domain collection inherits them, and the AST cache
    does not index inherited external-interface methods, so ``_project_owns``
    can't see them. Dropping all interface-method names from the table is what
    keeps these out of the JDK ``stdlib`` bucket."""
    _index(
        tmp_path,
        {
            "Pipeline.java": (
                "class Pipeline {\n"
                "    void caller(Flux flux) {\n"
                "        flux.stream();\n"
                "    }\n"
                "}\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "stream")
    assert res, "expected a stream() edge"
    assert "stdlib" not in res, (
        "interface method stream() on a non-JDK receiver (Reactor Flux) must NOT "
        f"be classified stdlib (review P1); got {res}"
    )
    assert "unknown" in res, (
        f"flux.stream with no project stream must stay unknown; got {res}"
    )


def test_java_production_verify_stays_unknown(tmp_path: Path) -> None:
    """Review P1 regression lock: ``signature.verify(sig)`` must stay UNKNOWN,
    never ``external`` (Mockito).

    Production security code calls ``verify()`` on ``java.security.Signature`` /
    ``Certificate`` / domain JWT tokens — receiver-qualified, NOT the bare
    Mockito ``verify(mock)``. Dropping ``verify``/``when``/``mock``/``spy`` from
    the external table keeps these production calls out of the test-stack
    bucket."""
    _index(
        tmp_path,
        {
            "Auth.java": (
                "class Auth {\n"
                "    void caller(Object signature, byte[] sig) {\n"
                "        signature.verify(sig);\n"
                "    }\n"
                "}\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "verify")
    assert res, "expected a verify() edge"
    assert "external" not in res, (
        "production security verify() on a non-Mockito receiver must NOT be "
        f"classified external (review P1); got {res}"
    )
    assert "unknown" in res, (
        f"signature.verify with no project verify must stay unknown; got {res}"
    )


# ---------------------------------------------------------------------------
# external method tier
# ---------------------------------------------------------------------------
def test_java_external_method_classifies_as_external(tmp_path: Path) -> None:
    """A Java test ``assertEquals(a, b)`` with no project ``assertEquals`` →
    external (JUnit), not unknown. ``assertEquals`` is a bare static assertion
    entry point — distinctively the test stack — unlike the dropped
    receiver-style Mockito names (``verify``/``when``/``mock``) that collide with
    production code (review P1)."""
    _index(
        tmp_path,
        {
            "ServiceTest.java": (
                "class ServiceTest {\n"
                "    void test(Object a, Object b) {\n"
                "        assertEquals(a, b);\n"
                "    }\n"
                "}\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "assertEquals")
    assert res, "expected an assertEquals() edge"
    assert "external" in res, (
        f"Java JUnit assertEquals must classify as external; got {res}"
    )


def test_java_project_method_shadows_external_name(tmp_path: Path) -> None:
    """A Java class defining ``assertEquals`` → ``c.assertEquals()`` resolves
    project, not external (shadowing preserved). Uses a KEPT external name so the
    ownership gate is exercised against a surviving entry."""
    _index(
        tmp_path,
        {
            "CustomChecker.java": (
                "class CustomChecker {\n"
                "    boolean assertEquals() { return true; }\n"
                "    void caller() {\n"
                "        CustomChecker c = new CustomChecker();\n"
                "        c.assertEquals();\n"
                "    }\n"
                "}\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "assertEquals")
    assert res, "expected an assertEquals() edge"
    assert "external" not in res, (
        f"project-defined Java assertEquals must NOT be classified external; got {res}"
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


# ---------------------------------------------------------------------------
# external-import preservation (Codex P2 #326, 2nd review)
# ---------------------------------------------------------------------------
def test_java_external_import_receiver_not_stdlib(tmp_path: Path) -> None:
    """``StringUtils.substring(s, 1)`` with ``import
    org.apache.commons.lang3.StringUtils`` → external, NOT stdlib.

    The receiver type resolves via the type-import to a non-project, non-JDK
    FQN — a third-party library. The stdlib-method tier (9b) must NOT fire just
    because ``substring`` is a JDK String name; the explicit external import
    terminates the resolution as ``external`` first (Codex P2 #326, 2nd review)."""
    _index(
        tmp_path,
        {
            "Service.java": (
                "import org.apache.commons.lang3.StringUtils;\n"
                "class Service {\n"
                "    void caller(String s) {\n"
                "        StringUtils.substring(s, 1);\n"
                "    }\n"
                "}\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "substring")
    assert res, "expected a substring() edge"
    assert "stdlib" not in res, (
        "StringUtils.substring (Apache Commons, a non-JDK import) must NOT be "
        f"classified stdlib; the external import terminates it; got {res}"
    )
    assert "external" in res, (
        f"an imported non-JDK receiver type must resolve external; got {res}"
    )


def test_java_external_static_import_not_stdlib(tmp_path: Path) -> None:
    """``substring(s, 1)`` with ``import static
    org.apache.commons.lang3.StringUtils.substring`` → external, NOT stdlib.

    The bare name is statically imported from a non-project, non-JDK owner. The
    static-import stage (3) must terminate it as ``external`` before the
    RFC-0008 stdlib-method tier (9b) can mislabel it ``stdlib`` (Codex P2 #326,
    2nd review)."""
    _index(
        tmp_path,
        {
            "Service.java": (
                "import static org.apache.commons.lang3.StringUtils.substring;\n"
                "class Service {\n"
                "    void caller(String s) {\n"
                "        substring(s, 1);\n"
                "    }\n"
                "}\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "substring")
    assert res, "expected a substring() edge"
    assert "stdlib" not in res, (
        "a statically-imported non-JDK substring must NOT be classified stdlib; "
        f"got {res}"
    )
