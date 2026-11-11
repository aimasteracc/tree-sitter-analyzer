"""#1937 / #1938: branch-level tests of the C#, PHP and Swift override gates.

The gates read source files and two index tables (``ast_symbol_rows`` for the
project's types, ``edges`` for call sites named like the target). A small
SQLite stub stands in for the index, so each fail-closed branch is reached
directly.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_csharp_overrides import csharp_row_finding
from tree_sitter_analyzer.mcp.tools.callers_lang_overrides import (
    lang_override_finding,
)
from tree_sitter_analyzer.mcp.tools.callers_php_overrides import php_row_finding
from tree_sitter_analyzer.mcp.tools.callers_swift_overrides import swift_row_finding


class _Index:
    """``get_conn()`` over an in-memory index with the two tables the gates read."""

    def __init__(
        self, types: list[tuple[str, str, str]] = (), calls=(), files=None
    ) -> None:
        self._conn = sqlite3.connect(":memory:")
        self._conn.execute(
            "CREATE TABLE ast_symbol_rows (name TEXT, kind TEXT, file_path TEXT, "
            "language TEXT)"
        )
        self._conn.execute(
            "CREATE TABLE edges (kind TEXT, callee_name TEXT, file_path TEXT, "
            "line INTEGER, callee_resolution TEXT, callee_resolved_file TEXT, "
            "metadata TEXT)"
        )
        self._conn.executemany(
            "INSERT INTO ast_symbol_rows VALUES (?, 'class', ?, ?)", types
        )
        self._conn.execute("CREATE TABLE ast_index (file_path TEXT, language TEXT)")
        self._conn.executemany(
            "INSERT INTO ast_index VALUES (?, ?)",
            sorted({(rel, language) for _name, rel, language in types})
            if files is None
            else files,
        )
        self._conn.executemany(
            "INSERT INTO edges VALUES ('calls', ?, ?, ?, 'unknown', '', '{}')", calls
        )

    def get_conn(self) -> sqlite3.Connection:
        return self._conn


class _Broken:
    def get_conn(self) -> sqlite3.Connection:
        raise sqlite3.OperationalError("gone")


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))


def _line(text: str, needle: str) -> int:
    return next(i for i, line in enumerate(text.splitlines(), 1) if needle in line)


def _cs(tmp_path: Path, files: dict[str, str], rel: str, bare: str, cache, needle=None):
    _write(tmp_path, files)
    line = _line(files[rel], needle or f" {bare}(")
    return csharp_row_finding(str(tmp_path), rel, line, bare, cache)


# --------------------------------------------------------------------- C#


def test_csharp_unreadable_and_unlocated_declarations_leave_the_check_not_run(
    tmp_path,
) -> None:
    missing = csharp_row_finding(str(tmp_path), "Nope.cs", 1, "M", _Index())
    assert missing[1] is not None and missing[1].unchecked

    _write(tmp_path, {"A.cs": "class A : B {\n    public override int P => 1;\n}\n"})
    unlocated = csharp_row_finding(str(tmp_path), "A.cs", 2, "P", _Index())
    assert unlocated[1] is not None and unlocated[1].unchecked
    plain = csharp_row_finding(str(tmp_path), "A.cs", 1, "Q", _Index())
    assert plain == (None, None)


def test_csharp_methods_that_override_nothing_pass(tmp_path) -> None:
    text = (
        "public class A : System.IDisposable {\n"
        "    public static void S() { }\n"
        "    internal void I() { }\n"
        "    void Local() { void Inner() { } }\n"
        "}\n"
        "public interface IX { void M(); }\n"
    )
    files = {"A.cs": text}
    for bare in ("S", "I", "Local"):
        assert _cs(tmp_path, files, "A.cs", bare, _Index())[1] is None, bare
    assert _cs(tmp_path, files, "A.cs", "M", _Index())[1] is None


def test_csharp_without_an_index_or_with_a_broken_one_fails_closed(tmp_path) -> None:
    files = {"A.cs": "class A : B {\n    public override void M() { }\n}\n"}
    _owner, no_index = _cs(tmp_path, files, "A.cs", "M", None)
    assert no_index is not None and "index could not be read" in no_index.why
    _owner, broken = _cs(tmp_path, files, "A.cs", "M", _Broken())
    assert broken is not None and "could not be read" in broken.why


def test_csharp_explicit_implementation_closed_in_the_project_passes(tmp_path) -> None:
    text = (
        "namespace N {\n"
        "    public interface IRun { void Run(); }\n"
        "    public class Job : IRun { void IRun.Run() { } }\n"
        "}\n"
    )
    index = _Index([("IRun", "J.cs", "csharp"), ("Job", "J.cs", "csharp")])
    found = _cs(tmp_path, {"J.cs": text}, "J.cs", "Run", index, "IRun.Run")
    assert found == ("Job", None)
    blocked = _Index(
        [("IRun", "J.cs", "csharp"), ("Job", "J.cs", "csharp")],
        [("Run", "Other.cs", 3)],
    )
    _owner, site = _cs(tmp_path, {"J.cs": text}, "J.cs", "Run", blocked, "IRun.Run")
    assert site is not None and "Other.cs:3" in site.why


@pytest.mark.parametrize(
    ("base", "needle"),
    [
        ("X::Base", "using alias `X`"),
        ("global::Missing.Base", "outside the project"),
        ("Base[]", "not a type name"),
    ],
)
def test_csharp_unresolvable_base_shapes_block(tmp_path, base, needle) -> None:
    text = f"public class A : {base} {{\n    public override void M() {{ }}\n}}\n"
    _owner, found = _cs(tmp_path, {"A.cs": text}, "A.cs", "M", _Index())
    assert found is not None and needle in found.why, found


def test_csharp_ambiguous_using_imports_and_static_usings_block(tmp_path) -> None:
    files = {
        "P.cs": "namespace P { public class Base { public virtual void M() { } } }\n",
        "Q.cs": "namespace Q { public class Base { public virtual void M() { } } }\n",
        "A.cs": (
            "using P;\nusing Q;\n"
            "public class A : Base {\n    public override void M() { }\n}\n"
        ),
        "S.cs": (
            "namespace R.S {\n    using static Outer;\n"
            "    public class C : Base2 { public override void M() { } }\n}\n"
            "namespace R { public class Base2 { public virtual void M() { } } }\n"
        ),
    }
    index = _Index(
        [
            ("Base", "P.cs", "csharp"),
            ("Base", "Q.cs", "csharp"),
            ("Base2", "S.cs", "csharp"),
        ]
    )
    _owner, ambiguous = _cs(tmp_path, files, "A.cs", "M", index, "override")
    assert ambiguous is not None and "ambiguous" in ambiguous.why
    _owner, hidden = _cs(tmp_path, files, "S.cs", "M", index, "class C")
    assert hidden is not None and "using" in hidden.why


def test_csharp_inherited_nested_types_and_records_resolve(tmp_path) -> None:
    files = {
        "B.cs": (
            "namespace N {\n"
            "    public class Host { public class Node { public virtual void V() { } } }\n"
            "    public class Sub : Host {\n"
            "        public class Leaf : Node { public override void V() { } }\n"
            "    }\n"
            "    public record Root(int X) { public virtual void R() { } }\n"
            "    public record Kid(int X) : Root(X) { public override void R() { } }\n"
            "    public class Obj : object { public override void Z() { } }\n"
            "}\n"
        )
    }
    index = _Index(
        [(n, "B.cs", "csharp") for n in ("Host", "Node", "Sub", "Leaf", "Root", "Kid")]
    )
    assert _cs(tmp_path, files, "B.cs", "V", index, "override void V")[1] is None
    assert _cs(tmp_path, files, "B.cs", "R", index, "override void R")[1] is None
    _owner, obj = _cs(tmp_path, files, "B.cs", "Z", index, "override void Z")
    assert obj is not None and "object" in obj.why


def test_csharp_base_list_with_a_syntax_error_blocks(tmp_path) -> None:
    text = (
        "public class A : B\n#if X\n    , IAsync\n#endif\n"
        "{\n    public override void M() { }\n}\n"
    )
    _owner, found = _cs(tmp_path, {"A.cs": text}, "A.cs", "M", _Index())
    assert found is not None and "could not be parsed" in found.why


# -------------------------------------------------------------------- PHP


def _php(tmp_path: Path, files: dict[str, str], rel: str, bare: str, cache):
    _write(tmp_path, files)
    line = _line(files[rel], f"function {bare}(")
    return php_row_finding(str(tmp_path), rel, line, bare, cache)


def test_php_unreadable_file_and_free_functions(tmp_path) -> None:
    missing = php_row_finding(str(tmp_path), "nope.php", 1, "m", _Index())
    assert missing[1] is not None and missing[1].unchecked
    files = {"f.php": "<?php\nfunction m() {}\n"}
    _write(tmp_path, files)
    assert php_row_finding(str(tmp_path), "f.php", 2, "m", _Index()) == (None, None)


def test_php_without_an_index_fails_closed(tmp_path) -> None:
    files = {"a.php": "<?php\nclass A extends B {\n    public function m() {}\n}\n"}
    _owner, found = _php(tmp_path, files, "a.php", "m", None)
    assert found is not None and "index could not be read" in found.why


def test_php_relative_names_duplicates_and_adapted_traits(tmp_path) -> None:
    files = {
        "base.php": "<?php\nnamespace App;\nclass Base {}\n",
        "dup1.php": "<?php\nnamespace App;\nclass Dup {}\n",
        "dup2.php": "<?php\nnamespace App;\nclass Dup {}\n",
        "a.php": (
            "<?php\nnamespace App;\nuse function strlen;\n"
            "class A extends namespace\\Base {\n    public function m() {}\n}\n"
            "class D extends Dup {\n    public function d() {}\n}\n"
            "trait T { public function t() {} }\n"
            "class E {\n    use T { t as protected u; }\n"
            "    public function e() {}\n}\n"
        ),
    }
    index = _Index(
        [
            ("Base", "base.php", "php"),
            ("Dup", "dup1.php", "php"),
            ("Dup", "dup2.php", "php"),
            ("T", "a.php", "php"),
        ]
    )
    assert _php(tmp_path, files, "a.php", "m", index)[1] is None
    _owner, dup = _php(tmp_path, files, "a.php", "d", index)
    assert dup is not None and "more than once" in dup.why
    _owner, adapted = _php(tmp_path, files, "a.php", "e", index)
    assert adapted is not None and "adapts" in adapted.why


def test_php_broken_index_blocks(tmp_path) -> None:
    files = {"a.php": "<?php\nclass A extends B {\n    public function m() {}\n}\n"}
    _owner, found = _php(tmp_path, files, "a.php", "m", _Broken())
    assert found is not None and "could not be read" in found.why


# ------------------------------------------------------------------ Swift


def _swift(
    tmp_path: Path, files: dict[str, str], rel: str, bare: str, cache, needle=None
):
    _write(tmp_path, files)
    line = _line(files[rel], needle or f"func {bare}(")
    return swift_row_finding(str(tmp_path), rel, line, bare, cache)


def test_swift_unreadable_file_and_free_functions(tmp_path) -> None:
    missing = swift_row_finding(str(tmp_path), "nope.swift", 1, "f", _Index())
    assert missing[1] is not None and missing[1].unchecked
    files = {"f.swift": "func testFree() {\n}\n"}
    assert _swift(tmp_path, files, "f.swift", "testFree", _Index()) == (None, None)


def test_swift_static_and_parameterised_test_names_are_no_xctest_methods(
    tmp_path,
) -> None:
    files = {
        "T.swift": (
            "class T {\n    static func testS() {\n    }\n\n"
            "    func testP(_ x: Int) {\n    }\n}\n"
        )
    }
    assert _swift(tmp_path, files, "T.swift", "testS", _Index())[1] is None
    assert _swift(tmp_path, files, "T.swift", "testP", _Index())[1] is None


def test_swift_override_branches(tmp_path) -> None:
    files = {
        "A.swift": (
            "class Animal {\n    func speak() {\n    }\n}\n\n"
            "class Dup {\n}\n\n"
            "class Dog: Animal {\n}\n\n"
            "extension Dog {\n    override func speak() {\n    }\n}\n\n"
            "class Cat: Animal {\n    override func purr() {\n    }\n}\n\n"
            "class Pug: Dup {\n    override func bark() {\n    }\n}\n\n"
            "class Box: Array<Int> {\n    override func count() {\n    }\n}\n"
        ),
        "B.swift": "class Dup {\n}\n",
        "S.swift": "struct S {\n    override func s() {\n    }\n}\n",
    }
    index = _Index(
        [
            ("Animal", "A.swift", "swift"),
            ("Dog", "A.swift", "swift"),
            ("Dup", "A.swift", "swift"),
            ("Dup", "B.swift", "swift"),
        ]
    )
    speak = _swift(tmp_path, files, "A.swift", "speak", index, "override func speak(")
    assert speak == ("Dog", None)
    _o, purr = _swift(tmp_path, files, "A.swift", "purr", index)
    assert purr is not None and "no superclass" in purr.why
    _o, bark = _swift(tmp_path, files, "A.swift", "bark", index)
    assert bark is not None and "more than once" in bark.why
    _o, count = _swift(tmp_path, files, "A.swift", "count", index)
    assert count is not None and "not a simple name" in count.why
    _o, struct = _swift(tmp_path, files, "S.swift", "s", index)
    assert struct is not None and "not a class" in struct.why
    _o, no_index = _swift(tmp_path, files, "A.swift", "purr", None)
    assert no_index is not None and "index could not be read" in no_index.why


# ----------------------------------------------------------------- router


def test_router_prefers_rows_of_the_owner_and_skips_other_languages(tmp_path) -> None:
    files = {
        "A.php": (
            "<?php\nclass A {\n    public function __invoke() {}\n}\n"
            "class B {\n    public function __invoke() {}\n}\n"
        ),
    }
    _write(tmp_path, files)
    rows = [("A.php", 3, "php"), ("A.php", 6, "php"), ("x.py", 1, "python")]
    found = lang_override_finding(str(tmp_path), rows, "__invoke", _Index(), "B")
    assert found is not None and found.class_name == "B"
    assert lang_override_finding(str(tmp_path), rows[2:], "m", _Index()) is None


# ------------------------------------------------------- more fail-closed paths


class _NoEdges(_Index):
    def __init__(self, types) -> None:
        super().__init__(types)
        self._conn.execute("DROP TABLE edges")


def test_csharp_supertypes_that_declare_nothing_or_only_classes(tmp_path) -> None:
    files = {
        "N.cs": (
            "namespace N;\nusing System;\n\n"
            "public class Base\n{\n"
            "#if NET\n    public virtual void Cond() { }\n#endif\n"
            "}\n"
            "public class Gen<T> { public virtual void G() { } }\n"
            "public interface IFoo { }\n"
            "public class A : Base, IFoo\n{\n"
            "    public override void Missing() { }\n"
            "    public void Pub() { }\n"
            "    public override void Cond() { }\n"
            "}\n"
            "public class O : object, IFoo { public void Pub2() { } }\n"
            "public class GA : Gen<int> { public override void G() { } }\n"
        )
    }
    index = _Index(
        [(n, "N.cs", "csharp") for n in ("Base", "Gen", "IFoo", "A", "O", "GA")]
    )
    _o, missing = _cs(tmp_path, files, "N.cs", "Missing", index)
    assert missing is not None and "no supertype" in missing.why
    assert _cs(tmp_path, files, "N.cs", "Pub", index)[1] is None
    assert _cs(tmp_path, files, "N.cs", "Pub2", index)[1] is None
    assert _cs(tmp_path, files, "N.cs", "Cond", index, "override void Cond")[1] is None
    assert _cs(tmp_path, files, "N.cs", "G", index, "override void G")[1] is None
    _o, no_edges = _cs(
        tmp_path,
        files,
        "N.cs",
        "Cond",
        _NoEdges(index_rows(index)),
        "override void Cond",
    )
    assert no_edges is not None and "call edges" in no_edges.why


def index_rows(index: _Index) -> list[tuple[str, str, str]]:
    return list(
        index.get_conn().execute(
            "SELECT name, file_path, language FROM ast_symbol_rows"
        )
    )


def test_csharp_large_closures_missing_files_and_enclosing_bases(tmp_path) -> None:
    chain = "".join(f"public interface I{i} : I{i + 1} {{ }}\n" for i in range(70))
    files = {
        "Big.cs": chain + "public interface I70 { }\n"
        "public class Big : I0 { public void Run() { } }\n",
        "Enc.cs": (
            "public class Base { public virtual void M() { } }\n"
            "public class Outer : External\n{\n"
            "    public class In : Base { public override void M() { } }\n"
            "}\n"
            "public class Gone2 : Gone { public override void M() { } }\n"
        ),
        "Al.cs": (
            "using X = N;\n"
            "namespace N { public class B { public virtual void M() { } } }\n"
            "public class Q : X.B { public override void M() { } }\n"
        ),
    }
    rows = [(f"I{i}", "Big.cs", "csharp") for i in range(71)]
    rows += [("Big", "Big.cs", "csharp"), ("Base", "Enc.cs", "csharp")]
    rows += [("Gone", "Missing.cs", "csharp"), ("B", "Al.cs", "csharp")]
    index = _Index(rows, files=[(f, "csharp") for f in ("Al.cs", "Big.cs", "Enc.cs")])
    _o, big = _cs(tmp_path, files, "Big.cs", "Run", index)
    assert big is not None and "too large" in big.why
    _o, enclosing = _cs(tmp_path, files, "Enc.cs", "M", index, "class In")
    assert enclosing is not None and "enclosing type" in enclosing.why
    _o, gone = _cs(tmp_path, files, "Enc.cs", "M", index, "class Gone2")
    assert gone is not None and "could not be parsed" in gone.why
    _o, alias = _cs(tmp_path, files, "Al.cs", "M", index, "class Q")
    assert alias is not None and "alias" in alias.why


def test_parse_failures_leave_the_checks_not_run(tmp_path, monkeypatch) -> None:
    from tree_sitter_analyzer.mcp.tools import (
        callers_csharp_overrides,
        callers_php_overrides,
        callers_swift_overrides,
    )

    _write(tmp_path, {"A.cs": "class A { }\n", "a.php": "<?php\n", "a.swift": "\n"})
    for module in (
        callers_csharp_overrides,
        callers_php_overrides,
        callers_swift_overrides,
    ):
        monkeypatch.setattr(module, "parse", lambda _language, _text: None)
    for check, rel in (
        (csharp_row_finding, "A.cs"),
        (php_row_finding, "a.php"),
        (swift_row_finding, "a.swift"),
    ):
        found = check(str(tmp_path), rel, 1, "m", _Index())[1]
        assert found is not None and found.unchecked, rel


def test_common_parse_returns_none_for_a_missing_grammar(monkeypatch) -> None:
    from tree_sitter_analyzer import language_loader
    from tree_sitter_analyzer.mcp.tools.callers_override_common import parse, same

    monkeypatch.setattr(language_loader, "create_parser_safely", lambda _l: None)
    assert parse("csharp", "class A { }") is None

    def boom(_language):
        raise RuntimeError("grammar")

    monkeypatch.setattr(language_loader, "create_parser_safely", boom)
    assert parse("csharp", "class A { }") is None
    monkeypatch.undo()
    tree = parse("csharp", "class A { }")
    assert tree is not None and same(tree.root, tree.root)


def test_php_large_closures_and_unreadable_candidates(tmp_path) -> None:
    chain = "".join(f"interface I{i} extends I{i + 1} {{}}\n" for i in range(70))
    files = {
        "big.php": "<?php\n" + chain + "interface I70 {}\n"
        "class Big implements I0 {\n    public function run() {}\n}\n"
        "class Lost extends Gone {\n    public function lost() {}\n}\n"
    }
    rows = [(f"I{i}", "big.php", "php") for i in range(71)]
    rows += [("Gone", "missing.php", "php")]
    index = _Index(rows)
    _o, big = _php(tmp_path, files, "big.php", "run", index)
    assert big is not None and "too large" in big.why
    _o, lost = _php(tmp_path, files, "big.php", "lost", index)
    assert lost is not None and "could not be parsed" in lost.why


def test_swift_unparsed_bodies_fallback_lines_cycles_and_unknown_extensions(
    tmp_path,
) -> None:
    files = {
        "R.swift": (
            "#if canImport(SystemConfiguration)\n\nimport XCTest\n\n"
            "final class R: XCTestCase {\n    // MARK: - Tests\n\n"
            "    override func setUp() {\n        super.setUp()\n    }\n\n"
            '    func testA() {\n        let m = M(host: "h")\n    }\n}\n\n#endif\n'
        ),
        "C.swift": (
            "class A: B {\n}\n\nclass B: A {\n    override func f() {\n    }\n}\n\n"
            "extension Ghost {\n    override func g() {\n    }\n}\n"
        ),
        "L.swift": "class Lost: Gone {\n    override func h() {\n    }\n}\n",
    }
    rows = [("A", "C.swift", "swift"), ("B", "C.swift", "swift")]
    rows += [("Gone", "missing.swift", "swift")]
    index = _Index(rows)
    _o, set_up = _swift(tmp_path, files, "R.swift", "setUp", index)
    assert set_up is not None and not set_up.unchecked
    _o, test = _swift(tmp_path, files, "R.swift", "testA", index, "final class R")
    assert test is not None and "XCTest" in test.why
    _o, cycle = _swift(tmp_path, files, "C.swift", "f", index)
    assert cycle is not None and "cyclic" in cycle.why
    _o, ghost = _swift(tmp_path, files, "C.swift", "g", index)
    assert ghost is not None and "Ghost" in ghost.why
    _o, lost = _swift(tmp_path, files, "L.swift", "h", index)
    assert lost is not None and "could not be parsed" in lost.why


def test_duplicate_supertypes_bodiless_records_and_broken_indexes(tmp_path) -> None:
    files = {
        "D.cs": (
            "public interface I { }\npublic interface J : I { }\n"
            "public class K : I, J { public void Pub() { } }\n"
            "public class Base { public virtual void M() { } }\n"
            "public record R(int X) : Base;\n"
            "public record S(int X) : R(X) { public override void M() { } }\n"
            "public class Q : N.B { public override void M() { } }\n"
        ),
        "d.php": (
            "<?php\ninterface I {}\ninterface J extends I {}\n"
            "class K implements I, J {\n    public function k() {}\n}\n"
            "$x = new class {\n    public function anon() {}\n};\n"
        ),
        "D.swift": (
            "class Animal {\n    class Inner {\n        func speak() {\n        }\n    }\n}\n\n"
            "class Dog: Animal {\n    override func speak() {\n    }\n}\n"
        ),
    }
    cs = _Index([(n, "D.cs", "csharp") for n in ("I", "J", "K", "Base", "R", "S")])
    assert _cs(tmp_path, files, "D.cs", "Pub", cs)[1] is None
    assert _cs(tmp_path, files, "D.cs", "M", cs, "record S")[1] is None
    _o, qualified = _cs(tmp_path, files, "D.cs", "M", _Broken(), "class Q")
    assert qualified is not None and "could not be read" in qualified.why
    php = _Index([("I", "d.php", "php"), ("J", "d.php", "php"), ("K", "d.php", "php")])
    assert _php(tmp_path, files, "d.php", "k", php)[1] is None
    assert _php(tmp_path, files, "d.php", "anon", php) == (None, None)
    swift = _Index([("Animal", "D.swift", "swift"), ("Dog", "D.swift", "swift")])
    _o, inner = _swift(tmp_path, files, "D.swift", "speak", swift, "override func")
    assert inner is not None and "no superclass" in inner.why
    _o, broken = _swift(tmp_path, files, "D.swift", "speak", _Broken(), "override func")
    assert broken is not None and "could not be read" in broken.why
    missing = swift_row_finding(str(tmp_path), "D.swift", 1, "absent", swift)
    assert missing == (None, None)
