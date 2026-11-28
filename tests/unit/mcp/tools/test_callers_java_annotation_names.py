"""PR-2: which Java annotation texts provably denote a passive ``java.lang`` annotation."""

from __future__ import annotations

import sqlite3

import pytest

from tree_sitter_analyzer.mcp.tools.callers_decorators import (
    DECORATED_REASON,
    decorator_finding,
    registering_decorator,
)
from tree_sitter_analyzer.mcp.tools.callers_java_annotations import (
    annotation_name,
    java_findings,
)


class _Cache:
    def __init__(self, classes=()) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE ast_symbol_rows (name TEXT, kind TEXT, file_path TEXT, "
            "language TEXT, line INTEGER)"
        )
        self.conn.execute(
            "CREATE TABLE edges (kind TEXT, callee_name TEXT, file_path TEXT, line "
            "INTEGER, callee_resolution TEXT, callee_resolved_file TEXT, metadata TEXT)"
        )
        for name in classes:
            self.conn.execute(
                "INSERT INTO ast_symbol_rows VALUES (?, 'class', 'x/X.java', 'java', 1)",
                (name,),
            )

    def get_conn(self):
        return self.conn


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("@Override", "Override"),
        ('@SuppressWarnings("x")', "SuppressWarnings"),
        ('@java.lang.Deprecated(since = "1")', "java.lang.Deprecated"),
        ("@ java . lang . SafeVarargs", "java.lang.SafeVarargs"),
        ("Override", None),
    ],
)
def test_annotation_name(text: str, name: str | None) -> None:
    assert annotation_name(text) == name


def _findings(cache, annotations, text="class A {}\n", bare="m"):
    return java_findings(cache, "/nowhere", "A.java", text, 1, bare, annotations)


def test_passive_annotations_pass_with_an_index() -> None:
    annotations = ['@SuppressWarnings("x")', "@Deprecated", "@java.lang.SafeVarargs"]

    assert _findings(_Cache(), annotations) == []


@pytest.mark.parametrize(
    ("cache", "text", "annotation"),
    [
        # No index: nothing is exempt.
        (None, "class A {}\n", "@Deprecated"),
        # A project type of that name shadows java.lang.
        (_Cache(classes=["Deprecated"]), "class A {}\n", "@Deprecated"),
        # A single-type (or static member) import shadows it too.
        (_Cache(), "import com.x.Deprecated;\nclass A {}\n", "@Deprecated"),
        (
            _Cache(),
            "import static com.x.Outer.Deprecated;\nclass A {}\n",
            "@Deprecated",
        ),
        # A qualified name outside java.lang, or a nested java.lang name.
        (_Cache(), "class A {}\n", "@com.x.Deprecated"),
        (_Cache(), "class A {}\n", "@java.lang.annotation.Native"),
        # Registering annotations.
        (_Cache(), "class A {}\n", "@Subscribe"),
        (_Cache(), "class A {}\n", "@Bean"),
    ],
)
def test_other_annotations_block_as_registering(
    cache, text: str, annotation: str
) -> None:
    (found,) = _findings(cache, [annotation], text=text)

    assert (found.text, found.override) == (annotation, False)


def test_override_without_a_target_name_blocks_as_registering() -> None:
    (found,) = _findings(_Cache(), ["@Override"], bare=None)

    assert found.override is False


def test_override_that_cannot_be_proved_is_an_override_finding() -> None:
    (found,) = _findings(
        _Cache(), ["@Override"], text="class A { @Override void m() {} }\n"
    )

    # `A` has no supertype, so nothing in the project declares `m` for it.
    assert (found.override, found.detail) == (
        True,
        "no supertype in the project declares it",
    )


def test_decorator_finding_prefers_a_registering_annotation(tmp_path) -> None:
    (tmp_path / "A.java").write_text(
        "class A extends Missing {\n  @Override\n  @Subscribe\n  void m() {}\n}\n",
        encoding="utf-8",
    )
    declarations = [("A.java", 2, "java")]

    found = decorator_finding(str(tmp_path), declarations, cache=_Cache(), bare="m")

    assert (found.text, found.reason) == ("@Subscribe", DECORATED_REASON)
    # Without the index every annotation blocks, as before PR-2.
    assert registering_decorator(str(tmp_path), declarations) == "@Override"


def test_decorator_finding_reports_the_override(tmp_path) -> None:
    (tmp_path / "A.java").write_text(
        "class A extends Missing {\n  @Override\n  void m() {}\n}\n", encoding="utf-8"
    )

    found = decorator_finding(
        str(tmp_path), [("A.java", 2, "java")], cache=_Cache(), bare="m"
    )

    assert found.reason == "OVERRIDE_DISPATCH"
    assert found.detail == "its supertype `Missing` is outside the project"
