"""Kotlin probes of the grep oracle (#1933): every real unlisted caller stays residual.

The two patterns the Kotlin callers fixes were about are the spec here:

* #1926: in Kotlin ``make()`` inside a class body means ``this.make()``, so a
  bare call in a base class may dispatch to an override in a subclass. Such a
  hit is never a proof, and neither is one inside a lambda that may bring its
  own receiver, an extension function or an unresolved ``this``.
* #1930: an ``override`` of a supertype declared outside the project may be
  called by code the project does not contain, so its own declaration is
  residual (a ``complete`` for it is never proven).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from benchmarks.callers_gate.oracle_grep import Item, Repo, check_item, site_covered

pytest.importorskip("tree_sitter_kotlin")
pytestmark = pytest.mark.slow_ok  # real git repos + git grep subprocesses

PROOFS = {
    "caller",
    "own_declaration",
    "declaration",
    "import_export",
    "comment",
    "string",
    "non_code",
    "other_symbol",
}


def _git_repo(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    subprocess.run(
        ["git", "-C", str(root), "init", "-q"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(root), "add", "."], check=True, capture_output=True
    )
    return root


def _hits(
    root: Path, name: str, file: str, qual: str, callers: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    item = Item(
        key=["bare", file, qual], name=name, file=file, qual=qual, callers=callers
    )
    hits = check_item(Repo(root), item)["hits"]
    assert isinstance(hits, list)
    return hits


def _at(hits: list[dict[str, Any]], file: str, line: int) -> list[str]:
    return [h["class"] for h in hits if h["file"] == file and h["line"] == line]


def _why(hits: list[dict[str, Any]], file: str, line: int) -> str:
    return " | ".join(h["why"] for h in hits if h["file"] == file and h["line"] == line)


# -- #1926: a bare inherited call in a class body reaches an override ---------

DISPATCH = {
    "src/a/A.kt": (
        "package a\n"
        "\n"
        "open class A {\n"
        "  open fun make(): Int = 1\n"
        "  fun run(): Int {\n"
        "    return make()\n"
        "  }\n"
        "  fun viaThis(): Int = this.make()\n"
        "}\n"
    ),
    "src/a/B.kt": ("package a\n\nclass B : A() {\n  override fun make(): Int = 2\n}\n"),
    "src/a/C.kt": (
        "package a\n"
        "\n"
        "class C {\n"
        "  fun make(): Int = 3\n"
        "  fun go(): Int = make()\n"
        "  fun viaThis(): Int = this.make()\n"
        "  fun scoped(b: B): Int = b.run { make() }\n"
        "  fun labelled(): Int = this@C.make()\n"
        "  inner class Inner {\n"
        "    fun up(): Int = make()\n"
        "  }\n"
        "  companion object {\n"
        "    fun fromCompanion(c: C): Int = c.make() + make()\n"
        "  }\n"
        "}\n"
    ),
    "src/a/Top.kt": (
        "package a\n"
        "\n"
        "fun top(c: C): Int {\n"
        "  return c.make()\n"
        "}\n"
        "\n"
        "fun A.ext(): Int = make()\n"
        "\n"
        "fun lam(c: C): Int = with(c) { make() }\n"
        "\n"
        "fun anon(): () -> Int = fun(): Int { return make() }\n"
        "\n"
        "fun refs(): Any = C::make\n"
        "\n"
        "fun named(): Int = listOf(1).fold(0) { acc, _ -> acc }\n"
        "\n"
        "fun bare(): Int = make()\n"
    ),
    "src/a/D.kt": (
        "package a\n"
        "\n"
        "import java.io.Closeable\n"
        "\n"
        "class D : Closeable {\n"
        "  override fun close() {}\n"
        "  fun make(): Int = 4\n"
        "  fun go(): Int = make()\n"
        "  val o = object : Runnable {\n"
        "    override fun run() { make() }\n"
        "  }\n"
        "}\n"
    ),
    "build.gradle.kts": "plugins { }\nval x = make()\n",
}
B_MAKE = ("make", "src/a/B.kt", "B.make")


def test_1926_a_bare_call_in_the_base_class_body_stays_residual(
    tmp_path: Path,
) -> None:
    hits = _hits(_git_repo(tmp_path, DISPATCH), *B_MAKE, [])
    assert _at(hits, "src/a/A.kt", 6) == ["residual"]
    assert "related" in _why(hits, "src/a/A.kt", 6)
    assert _at(hits, "src/a/A.kt", 8) == ["residual"]


def test_1926_the_base_class_call_is_covered_once_its_owner_is_listed(
    tmp_path: Path,
) -> None:
    listed = [{"file": "src/a/A.kt", "name": "run", "line": 5}]
    hits = _hits(_git_repo(tmp_path, DISPATCH), *B_MAKE, listed)
    assert _at(hits, "src/a/A.kt", 6) == ["caller"]


def test_a_bare_or_this_call_in_an_unrelated_class_is_another_symbol(
    tmp_path: Path,
) -> None:
    hits = _hits(_git_repo(tmp_path, DISPATCH), *B_MAKE, [])
    assert _at(hits, "src/a/C.kt", 5) == ["other_symbol"]
    assert _at(hits, "src/a/C.kt", 6) == ["other_symbol"]
    assert _at(hits, "src/a/C.kt", 10) == ["other_symbol"]  # inner class -> C


@pytest.mark.parametrize(
    "file,line,reason",
    [
        ("src/a/C.kt", 7, "lambda"),  # b.run { make() }: the lambda's receiver is a B
        ("src/a/C.kt", 8, "labelled"),  # this@C
        ("src/a/C.kt", 13, "companion"),
        ("src/a/Top.kt", 7, "extension"),  # fun A.ext()
        ("src/a/Top.kt", 9, "lambda"),  # with(c) { make() }
        ("src/a/Top.kt", 11, "anonymous function"),
        ("src/a/D.kt", 8, "related"),  # D : java.io.Closeable does not resolve
        ("src/a/D.kt", 10, "object expression"),
        ("build.gradle.kts", 2, "script"),
    ],
)
def test_receiver_scopes_and_unresolved_this_are_never_proof(
    tmp_path: Path, file: str, line: int, reason: str
) -> None:
    hits = _hits(_git_repo(tmp_path, DISPATCH), *B_MAKE, [])
    classes = _at(hits, file, line)
    assert "residual" in classes, (file, line, classes)
    assert set(classes) <= {"residual"} | (PROOFS - {"other_symbol", "caller"})
    assert reason in _why(hits, file, line)


def test_member_receivers_and_callable_references_are_residual(
    tmp_path: Path,
) -> None:
    hits = _hits(_git_repo(tmp_path, DISPATCH), *B_MAKE, [])
    assert _at(hits, "src/a/Top.kt", 4) == ["residual"]  # c.make()
    assert _at(hits, "src/a/C.kt", 13)[0] == "residual"  # c.make() in companion
    assert _at(hits, "src/a/Top.kt", 13) == ["residual"]  # C::make


def test_a_top_level_bare_call_has_no_implicit_receiver(tmp_path: Path) -> None:
    hits = _hits(_git_repo(tmp_path, DISPATCH), *B_MAKE, [])
    assert _at(hits, "src/a/Top.kt", 17) == ["other_symbol"]


def test_declarations_of_the_name(tmp_path: Path) -> None:
    hits = _hits(_git_repo(tmp_path, DISPATCH), *B_MAKE, [])
    assert _at(hits, "src/a/B.kt", 4) == ["own_declaration"]
    assert _at(hits, "src/a/A.kt", 4) == ["declaration"]
    assert _at(hits, "src/a/C.kt", 4) == ["declaration"]


def test_a_top_level_target_has_no_provable_class(tmp_path: Path) -> None:
    files = {
        "src/t/T.kt": "package t\n\nfun helper(): Int = 1\n",
        "src/t/U.kt": "package t\n\nclass U {\n  fun go(): Int = helper()\n}\n",
    }
    hits = _hits(_git_repo(tmp_path, files), "helper", "src/t/T.kt", "helper", [])
    assert _at(hits, "src/t/T.kt", 3) == ["own_declaration"]
    assert _at(hits, "src/t/U.kt", 4) == ["residual"]


# -- #1930: an override of an external supertype is never complete -----------

OVERRIDES = {
    "src/b/F.kt": (
        "package b\n"
        "\n"
        "import java.io.Closeable\n"
        "\n"
        "class F : Closeable {\n"
        "  override fun close() {}\n"
        "}\n"
    ),
    "src/b/Base.kt": (
        "package b\n"
        "\n"
        "abstract class Base {\n"
        "  abstract fun m(): Int\n"
        "}\n"
        "\n"
        "class G : Base() {\n"
        "  override fun m(): Int = 1\n"
        "}\n"
        "\n"
        "class H : Comparable<H> {\n"
        "  override fun compareTo(other: H): Int = 0\n"
        '  override fun toString(): String = "H"\n'
        "}\n"
    ),
    "src/b/K.kt": (
        "package b\n"
        "\n"
        "import b.Base as Root\n"
        "\n"
        "class K : Root() {\n"
        "  override fun m(): Int = 2\n"
        "}\n"
    ),
    "src/b/Use.kt": "package b\n\nfun use(f: F) {\n  f.close()\n}\n",
}


def test_1930_an_override_of_an_external_supertype_is_residual(
    tmp_path: Path,
) -> None:
    hits = _hits(_git_repo(tmp_path, OVERRIDES), "close", "src/b/F.kt", "F.close", [])
    assert _at(hits, "src/b/F.kt", 6) == ["residual"]
    assert "outside the project" in _why(hits, "src/b/F.kt", 6)
    assert _at(hits, "src/b/Use.kt", 4) == ["residual"]


@pytest.mark.parametrize(
    "name,qual,line", [("compareTo", "H.compareTo", 12), ("toString", "H.toString", 13)]
)
def test_1930_builtin_supertypes_and_any_members_are_outside_the_project(
    tmp_path: Path, name: str, qual: str, line: int
) -> None:
    hits = _hits(_git_repo(tmp_path, OVERRIDES), name, "src/b/Base.kt", qual, [])
    assert _at(hits, "src/b/Base.kt", line) == ["residual"]


def test_1930_an_override_of_a_project_supertype_is_its_own_declaration(
    tmp_path: Path,
) -> None:
    hits = _hits(_git_repo(tmp_path, OVERRIDES), "m", "src/b/Base.kt", "G.m", [])
    assert _at(hits, "src/b/Base.kt", 8) == ["own_declaration"]


def test_1930_a_supertype_bound_by_an_import_alias_is_unresolved(
    tmp_path: Path,
) -> None:
    hits = _hits(_git_repo(tmp_path, OVERRIDES), "m", "src/b/K.kt", "K.m", [])
    assert _at(hits, "src/b/K.kt", 6) == ["residual"]


# -- syntax classes ----------------------------------------------------------

SYNTAX = {
    "src/s/S.kt": (
        "package s\n"
        "\n"
        "import s.other.make\n"
        "import s.other.make as mk\n"
        "\n"
        "/** Calls [make]. */\n"
        "class S {\n"
        "  fun make(): Int = 1\n"
        "  val p = make()\n"
        "  init {\n"
        "    make()\n"
        "  }\n"
        "  fun owner(): Int {\n"
        "    listOf(1).map { make() }\n"
        "    fun local(): Int = make()\n"
        '    val s = "make" + "to make" + "${make()}"\n'
        "    return local() + call(make = 2)\n"
        "  }\n"
        "  fun call(make: Int): Int = make\n"
        "}\n"
    ),
    "README.md": "make it\n",
}


def test_kotlin_syntax_classes(tmp_path: Path) -> None:
    listed = [{"file": "src/s/S.kt", "name": "owner", "line": 13}]
    hits = _hits(_git_repo(tmp_path, SYNTAX), "make", "src/s/S.kt", "S.make", listed)
    assert _at(hits, "src/s/S.kt", 3) == ["import_export"]
    assert _at(hits, "src/s/S.kt", 4) == ["residual"]  # aliased import
    assert _at(hits, "src/s/S.kt", 6) == ["comment"]
    assert _at(hits, "src/s/S.kt", 8) == ["own_declaration"]
    assert _at(hits, "src/s/S.kt", 14) == ["caller"]  # lambda belongs to owner
    assert _at(hits, "src/s/S.kt", 15) == ["residual"]  # inside the local fun
    assert _at(hits, "src/s/S.kt", 16) == ["caller", "caller", "caller"]
    unlisted = _hits(_git_repo(tmp_path, SYNTAX), "make", "src/s/S.kt", "S.make", [])
    # "make" may be a reflective name; "${make()}" is code, not a string
    assert _at(unlisted, "src/s/S.kt", 16) == ["residual", "string", "residual"]
    assert _at(unlisted, "src/s/S.kt", 17) == ["other_symbol"]  # named argument
    # a parameter, then a plain read of it (a Kotlin fun is used only by a call)
    assert _at(hits, "src/s/S.kt", 19) == ["declaration", "other_symbol"]
    assert _at(hits, "README.md", 1) == ["non_code"]


def test_a_raw_string_is_a_string_and_its_templates_are_code(tmp_path: Path) -> None:
    files = {
        "src/r/R.kt": (
            "package r\n\nclass R {\n  fun make() = 1\n"
            '  val s = """\n    |fun make() {\n    |  ${make()}\n    |}\n  """\n}\n'
        )
    }
    hits = _hits(_git_repo(tmp_path, files), "make", "src/r/R.kt", "R.make", [])
    assert _at(hits, "src/r/R.kt", 6) == ["string"]
    assert _at(hits, "src/r/R.kt", 7) == ["residual"]


def test_init_blocks_and_property_initializers_belong_to_module(
    tmp_path: Path,
) -> None:
    module = [
        {"file": "src/s/S.kt", "name": "<module>", "line": 9},
        {"file": "src/s/S.kt", "name": "<module>", "line": 11},
    ]
    hits = _hits(_git_repo(tmp_path, SYNTAX), "make", "src/s/S.kt", "S.make", module)
    assert _at(hits, "src/s/S.kt", 9) == ["caller"]
    assert _at(hits, "src/s/S.kt", 11) == ["caller"]
    unlisted = _hits(_git_repo(tmp_path, SYNTAX), "make", "src/s/S.kt", "S.make", [])
    assert _at(unlisted, "src/s/S.kt", 9) == ["residual"]


def test_a_kotlin_parse_error_is_residual(tmp_path: Path) -> None:
    files = {
        "src/p/P.kt": "package p\n\nclass P {\n  fun make() = 1\n}\n",
        "src/p/Bad.kt": "package p\n\nclass Q {\n  fun f() { )) make() }\n}\n",
    }
    hits = _hits(_git_repo(tmp_path, files), "make", "src/p/P.kt", "P.make", [])
    assert _at(hits, "src/p/Bad.kt", 4) == ["residual"]


def test_site_covered_uses_the_innermost_kotlin_fun(tmp_path: Path) -> None:
    repo = Repo(_git_repo(tmp_path, SYNTAX))
    owner = [{"file": "src/s/S.kt", "name": "owner", "line": 13, "end_line": 18}]
    assert site_covered(repo, "src/s/S.kt", 14, "make", owner)
    assert not site_covered(repo, "src/s/S.kt", 15, "make", owner)
