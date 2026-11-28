"""#1930: the Kotlin ``override`` proof, case by case, over a minimal index."""

from __future__ import annotations

import sqlite3

import pytest

from tree_sitter_analyzer.mcp.tools import callers_kotlin_overrides as kotlin
from tree_sitter_analyzer.mcp.tools.callers_java_overrides import OVERRIDE_REASON
from tree_sitter_analyzer.mcp.tools.callers_kotlin_overrides import (
    kotlin_supertype_finding,
)
from tree_sitter_analyzer.mcp.tools.callers_supertypes import (
    KOTLIN_OVERRIDE_VERB,
    dynamic_supertype,
    dynamic_supertype_hint,
)


class _Cache:
    """Kotlin class rows (``name -> files``) and call edges."""

    def __init__(self, classes=(), edges=(), broken: bool = False) -> None:
        self.broken = broken
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
                "INSERT INTO ast_symbol_rows VALUES (?, 'class', ?, 'kotlin', 1)",
                (name, file),
            )
        for row in edges:
            self.conn.execute(
                "INSERT INTO edges VALUES ('calls', ?, ?, ?, ?, ?, ?)", row
            )

    def get_conn(self):
        if self.broken:
            raise sqlite3.OperationalError("locked")
        return self.conn


_SHAPE = "package p\n\ninterface Shape {\n    fun area(): Int\n}\n"


def _write(tmp_path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _find(tmp_path, cache, file: str, line: int, bare: str, owner: str = ""):
    return kotlin_supertype_finding(
        str(tmp_path), [(file, line, "kotlin")], bare, cache, owner
    )


def _impl(header: str, member: str = "override fun area(): Int = 1") -> str:
    return f"package q\n\n{header} {{\n    {member}\n}}\n"


@pytest.mark.parametrize(
    ("imports", "header"),
    [
        ("import p.Shape\n", "class Sq : Shape"),
        ("import p.Shape as Form\n", "class Sq : Form"),
        ("import p.*\n", "class Sq : Shape"),
        ("", "class Sq : p.Shape"),
        ("import p.Shape\n", "object Sq : Shape"),
    ],
)
def test_a_project_supertype_closes_the_override(tmp_path, imports, header) -> None:
    text = "package q\n\n" + imports + "\n" + header + " {\n"
    text += "    override fun area(): Int = 1\n}\n"
    _write(tmp_path, {"p/Shape.kt": _SHAPE, "q/Sq.kt": text})
    line = text.splitlines().index("    override fun area(): Int = 1") + 1
    cache = _Cache(classes=[("Shape", "p/Shape.kt")])

    assert _find(tmp_path, cache, "q/Sq.kt", line, "area") is None


@pytest.mark.parametrize(
    ("text", "line", "bare", "detail"),
    [
        (
            _impl("class F : java.io.Closeable", "override fun close() {}"),
            4,
            "close",
            "`java.io.Closeable` is declared outside the project",
        ),
        (
            "package q\n\nimport java.io.Closeable\n\nclass F : Closeable {\n"
            "    override fun close() {}\n}\n",
            6,
            "close",
            "(`java.io.Closeable`)",
        ),
        (
            _impl("class F : Runnable", "override fun run() {}"),
            4,
            "run",
            "`Runnable` is declared outside the project",
        ),
        (
            _impl("class F", 'override fun toString(): String = ""'),
            4,
            "toString",
            "kotlin.Any.toString",
        ),
        (
            "package q\n\ntypealias C = java.io.Closeable\n\nclass F : C {\n"
            "    override fun close() {}\n}\n",
            6,
            "close",
            "is a type alias",
        ),
        (
            _impl("class F : (Int) -> Unit", "override fun invoke(x: Int) {}"),
            4,
            "invoke",
            "not a type name",
        ),
        (
            _impl("class F : Marker", "override fun area(): Int = 1"),
            4,
            "area",
            "no supertype in the project declares it",
        ),
    ],
)
def test_an_override_that_is_not_closed_is_found(
    tmp_path, text, line, bare, detail
) -> None:
    _write(tmp_path, {"q/F.kt": text, "q/Marker.kt": "package q\n\ninterface Marker\n"})
    cache = _Cache(classes=[("Marker", "q/Marker.kt")])

    found = _find(tmp_path, cache, "q/F.kt", line, bare, "F")

    assert found is not None
    assert found.reason == OVERRIDE_REASON
    assert found.verb == KOTLIN_OVERRIDE_VERB
    assert not found.unchecked
    assert detail in found.why, found.why


def test_an_external_supertype_of_a_project_supertype_is_named(tmp_path) -> None:
    _write(
        tmp_path,
        {
            "p/Res.kt": "package p\n\ninterface Res : AutoCloseable\n",
            "p/R.kt": _impl("class R : Res", "override fun close() {}").replace(
                "package q", "package p"
            ),
        },
    )
    cache = _Cache(classes=[("Res", "p/Res.kt"), ("R", "p/R.kt")])

    found = _find(tmp_path, cache, "p/R.kt", 4, "close")

    assert found is not None
    assert "`AutoCloseable`" in found.why and "(via `Res`)" in found.why
    hint = dynamic_supertype_hint("R.close", found)
    assert "declared `override`" in hint and "AutoCloseable" in hint


def test_a_call_named_like_it_elsewhere_keeps_it_open(tmp_path) -> None:
    text = _impl("class Sq : Shape")
    _write(
        tmp_path,
        {"q/Shape.kt": _SHAPE.replace("package p", "package q"), "q/Sq.kt": text},
    )
    edges = [("area", "q/Use.kt", 7, "unknown", "", "{}")]
    cache = _Cache(classes=[("Shape", "q/Shape.kt")], edges=edges)

    found = _find(tmp_path, cache, "q/Sq.kt", 4, "area")

    assert found is not None
    assert "q/Use.kt:7" in found.why


@pytest.mark.parametrize(
    ("files", "file", "line", "bare"),
    [
        # nested type in scope, and a nested type reached as Outer.Inner
        (
            {
                "q/O.kt": "package q\n\nclass O {\n    interface I {\n"
                "        fun go()\n    }\n\n    class K : I {\n"
                "        override fun go() {}\n    }\n}\n"
            },
            "q/O.kt",
            9,
            "go",
        ),
        (
            {
                "q/O.kt": "package q\n\nclass O {\n    interface I {\n"
                "        fun go()\n    }\n}\n",
                "q/K.kt": "package q\n\nclass K : O.I {\n    override fun go() {}\n}\n",
            },
            "q/K.kt",
            4,
            "go",
        ),
        # an enum entry body overrides a member of its enum
        (
            {
                "q/E.kt": "package q\n\nenum class E {\n    A {\n"
                "        override fun go() {}\n    };\n\n    open fun go() {}\n}\n"
            },
            "q/E.kt",
            5,
            "go",
        ),
        # a companion object and an object expression implementing a project type
        (
            {
                "q/C.kt": "package q\n\ninterface I {\n    fun go()\n}\n\nclass C {\n"
                "    companion object : I {\n        override fun go() {}\n    }\n}\n"
            },
            "q/C.kt",
            9,
            "go",
        ),
        (
            {
                "q/X.kt": "package q\n\ninterface I {\n    val go: Int\n}\n\n"
                "fun make(): I {\n    return object : I {\n"
                "        override fun go() {}\n    }\n}\n"
            },
            "q/X.kt",
            9,
            "go",
        ),
        # a property declared in the primary constructor
        (
            {
                "q/P.kt": "package q\n\nabstract class B(open val go: Int)\n\n"
                "class P : B(1) {\n    override fun go() {}\n}\n"
            },
            "q/P.kt",
            6,
            "go",
        ),
    ],
)
def test_types_in_the_same_file_or_nested_close_it(
    tmp_path, files, file, line, bare
) -> None:
    _write(tmp_path, files)
    cache = _Cache(classes=[("O", "q/O.kt"), ("B", "q/P.kt")])

    assert _find(tmp_path, cache, file, line, bare) is None


@pytest.mark.parametrize(
    ("files", "why"),
    [
        (
            {
                "q/F.kt": "package q\n\nimport z.Shape\n\nclass Shape\n\n"
                "class F : Shape {\n    override fun area(): Int = 1\n}\n"
            },
            "ambiguous",
        ),
        (
            {
                "q/F.kt": _impl("class F : Shape"),
                "q/S1.kt": _SHAPE.replace("package p", "package q"),
                "q/S2.kt": _SHAPE.replace("package p", "package q"),
            },
            "ambiguous",
        ),
        (
            {
                "q/F.kt": "package q\n\nimport a.*\nimport b.*\n\nclass F : Shape {\n"
                "    override fun area(): Int = 1\n}\n",
                "a/S.kt": _SHAPE.replace("package p", "package a"),
                "b/S.kt": _SHAPE.replace("package p", "package b"),
            },
            "ambiguous",
        ),
    ],
)
def test_an_ambiguous_supertype_keeps_it_open(tmp_path, files, why) -> None:
    _write(tmp_path, files)
    cache = _Cache(
        classes=[("Shape", name) for name in files if name != "q/F.kt"]
        + [("Shape", "q/F.kt")]
    )
    line = files["q/F.kt"].splitlines().index("    override fun area(): Int = 1") + 1

    found = _find(tmp_path, cache, "q/F.kt", line, "area")

    assert found is not None and why in found.why, found


def test_methods_without_override_and_other_rows_pass(tmp_path) -> None:
    text = "package q\n\nclass F : java.io.Closeable {\n    fun close() {}\n}\n"
    _write(tmp_path, {"q/F.kt": text, "q/J.java": "class J {}\n"})

    assert _find(tmp_path, _Cache(), "q/F.kt", 4, "close") is None
    assert _find(tmp_path, _Cache(), "q/F.kt", 3, "F") is None
    rows = [("q/J.java", 1, "java")]
    assert kotlin_supertype_finding(str(tmp_path), rows, "x", _Cache()) is None


def test_unreadable_or_unlocatable_declarations_leave_the_check_not_run(
    tmp_path,
) -> None:
    _write(tmp_path, {"q/F.kt": "package q\n\noverride fun close() {}\n"})

    missing = _find(tmp_path, _Cache(), "q/Gone.kt", 3, "close")
    assert missing is not None and missing.unchecked
    top_level = _find(tmp_path, _Cache(), "q/F.kt", 3, "close")
    assert top_level is not None and "declaring type" in top_level.why
    _write(tmp_path, {"q/G.kt": "package q\n\nclass G : I { override val x\n"})
    unlocated = _find(tmp_path, _Cache(), "q/G.kt", 3, "nope")
    assert unlocated is not None and unlocated.unchecked


def test_an_unreadable_index_or_parser_fails_closed(tmp_path, monkeypatch) -> None:
    text = _impl("class Sq : Shape")
    _write(tmp_path, {"q/Sq.kt": text})

    broken = _find(tmp_path, _Cache(broken=True), "q/Sq.kt", 4, "area")
    assert broken is not None and "could not be read" in broken.why
    no_index = _find(tmp_path, None, "q/Sq.kt", 4, "area")
    assert no_index is not None and "index" in no_index.why
    monkeypatch.setattr(kotlin, "_parse", lambda _text: None)
    unparsed = _find(tmp_path, _Cache(), "q/Sq.kt", 4, "area")
    assert unparsed is not None and unparsed.unchecked


def test_a_broken_supertype_list_fails_closed(tmp_path) -> None:
    text = "package q\n\nclass F : Shape, {\n    override fun area(): Int = 1\n}\n"
    _write(tmp_path, {"q/F.kt": text})

    found = _find(tmp_path, _Cache(), "q/F.kt", 4, "area")

    assert found is not None and not found.unchecked


def test_a_too_large_closure_fails_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(kotlin, "_MAX_TYPES", 1)
    _write(
        tmp_path,
        {
            "q/A.kt": "package q\n\ninterface A {\n    fun area(): Int\n}\n",
            "q/B.kt": "package q\n\ninterface B : A\n",
            "q/F.kt": _impl("class F : B"),
        },
    )
    cache = _Cache(classes=[("A", "q/A.kt"), ("B", "q/B.kt")])

    found = _find(tmp_path, cache, "q/F.kt", 4, "area")

    assert found is not None and "too large" in found.why


def test_dynamic_supertype_routes_kotlin_rows(tmp_path) -> None:
    _write(tmp_path, {"q/F.kt": _impl("class F : Runnable", "override fun run() {}")})

    found = dynamic_supertype(str(tmp_path), [("q/F.kt", 4, "kotlin")], "run", _Cache())

    assert found is not None and found.reason == OVERRIDE_REASON


def test_a_diamond_and_a_file_without_a_package_close_it(tmp_path) -> None:
    _write(
        tmp_path,
        {
            "A.kt": "interface A {\n    fun area(): Int\n}\n\ninterface B : A\n\n"
            "interface C : A\n\nclass F : B, C {\n    override fun area(): Int = 1\n}\n",
        },
    )

    assert _find(tmp_path, _Cache(), "A.kt", 10, "area") is None


@pytest.mark.parametrize(
    ("files", "classes", "why"),
    [
        # p.Shape is declared twice in package p
        (
            {"p/S1.kt": _SHAPE, "p/S2.kt": _SHAPE},
            [("Shape", "p/S1.kt"), ("Shape", "p/S2.kt")],
            "ambiguous",
        ),
        # the index names a file that is gone
        ({}, [("Shape", "p/Gone.kt")], "could not be parsed"),
    ],
)
def test_a_qualified_supertype_that_cannot_be_pinned_keeps_it_open(
    tmp_path, files, classes, why
) -> None:
    _write(tmp_path, {**files, "q/F.kt": _impl("class F : p.Shape")})

    found = _find(tmp_path, _Cache(classes=classes), "q/F.kt", 4, "area")

    assert found is not None and why in found.why, found


def test_a_missing_nested_type_is_outside(tmp_path) -> None:
    _write(
        tmp_path,
        {
            "q/O.kt": "package q\n\nclass O {\n    class I\n}\n",
            "q/F.kt": _impl("class F : O.Missing"),
        },
    )

    found = _find(tmp_path, _Cache(classes=[("O", "q/O.kt")]), "q/F.kt", 4, "area")

    assert found is not None and "`O.Missing` is declared outside" in found.why


def test_unreadable_call_edges_keep_it_open(tmp_path) -> None:
    _write(
        tmp_path,
        {
            "q/S.kt": _SHAPE.replace("package p", "package q"),
            "q/F.kt": _impl("class F : Shape"),
        },
    )
    cache = _Cache(classes=[("Shape", "q/S.kt")])
    cache.conn.execute("DROP TABLE edges")

    found = _find(tmp_path, cache, "q/F.kt", 4, "area")

    assert found is not None and "call edges" in found.why


def test_a_nested_type_out_of_scope_does_not_close_it(tmp_path) -> None:
    # ``I`` is nested in ``O``; ``K`` is not inside ``O``, so ``I`` there is
    # another type (here: none in the project).
    text = (
        "package q\n\nclass O {\n    interface I {\n        fun go()\n    }\n}\n\n"
        "class K : I {\n    override fun go() {}\n}\n"
    )
    _write(tmp_path, {"q/O.kt": text})

    found = _find(tmp_path, _Cache(classes=[("O", "q/O.kt")]), "q/O.kt", 10, "go")

    assert found is not None and "`I` is declared outside" in found.why
