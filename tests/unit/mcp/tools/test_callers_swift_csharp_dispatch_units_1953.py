"""#1953: branch tests of the Swift protocol and C# interface dispatch checks.

The gates read the index only for type files (``ast_symbol_rows``), the files
of a language (``ast_index``) and call edges; an in-memory index stands in.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tree_sitter_analyzer.mcp.tools.callers_csharp_overrides import csharp_row_finding
from tree_sitter_analyzer.mcp.tools.callers_csharp_scope import _items
from tree_sitter_analyzer.mcp.tools.callers_swift_overrides import swift_row_finding


class _Index:
    """Index tables the gates read; every written file is listed."""

    def __init__(self, files: dict[str, str], calls=(), unlisted=()) -> None:
        self._conn = sqlite3.connect(":memory:")
        self._conn.execute(
            "CREATE TABLE ast_symbol_rows (name TEXT, kind TEXT, file_path TEXT, "
            "language TEXT)"
        )
        self._conn.execute("CREATE TABLE ast_index (file_path TEXT, language TEXT)")
        self._conn.execute(
            "CREATE TABLE edges (kind TEXT, callee_name TEXT, file_path TEXT, "
            "line INTEGER, callee_resolution TEXT, callee_resolved_file TEXT, "
            "metadata TEXT)"
        )
        listed = [*files, *unlisted]
        for rel in listed:
            language = "swift" if rel.endswith(".swift") else "csharp"
            self._conn.execute("INSERT INTO ast_index VALUES (?, ?)", (rel, language))
            for name in _type_names(files.get(rel, "")):
                self._conn.execute(
                    "INSERT INTO ast_symbol_rows VALUES (?, 'class', ?, ?)",
                    (name, rel, language),
                )
        self._conn.executemany(
            "INSERT INTO edges VALUES ('calls', ?, ?, ?, 'unknown', '', '{}')", calls
        )

    def get_conn(self) -> sqlite3.Connection:
        return self._conn


class _Broken:
    def get_conn(self) -> sqlite3.Connection:
        raise sqlite3.OperationalError("gone")


def _type_names(text: str) -> list[str]:
    import re

    return re.findall(r"\b(?:class|struct|interface|record)\s+(\w+)", text)


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))


def _line(text: str, needle: str) -> int:
    return next(i for i, line in enumerate(text.splitlines(), 1) if needle in line)


def _swift(tmp_path: Path, files, rel: str, bare: str, cache, needle=None):
    _write(tmp_path, files)
    line = _line(files[rel], needle or f"func {bare}(")
    return swift_row_finding(str(tmp_path), rel, line, bare, cache)[1]


def _cs(tmp_path: Path, files, rel: str, bare: str, cache, needle=None):
    _write(tmp_path, files)
    line = _line(files[rel], needle or f" {bare}(")
    return csharp_row_finding(str(tmp_path), rel, line, bare, cache)[1]


# ------------------------------------------------------------------ Swift


def test_swift_private_methods_and_external_extensions_pass(tmp_path) -> None:
    files = {
        "A.swift": (
            "class A: NSObject, WKExtensionDelegate {\n"
            "    private func hidden() {\n    }\n}\n\n"
            "extension URLRequest {\n    func header() {\n    }\n}\n"
        )
    }
    index = _Index(files)
    assert _swift(tmp_path, files, "A.swift", "hidden", index) is None
    assert _swift(tmp_path, files, "A.swift", "header", index) is None


def test_swift_without_an_index_or_files_blocks(tmp_path) -> None:
    files = {"A.swift": "class A: P {\n    func f() {\n    }\n}\n"}
    found = _swift(tmp_path, files, "A.swift", "f", None)
    assert found is not None and "index could not be read" in found.why
    found = _swift(tmp_path, files, "A.swift", "f", _Broken())
    assert found is not None and "could not be listed" in found.why
    found = _swift(tmp_path, files, "A.swift", "f", _Index(files, unlisted=["G.swift"]))
    assert found is not None and "G.swift could not be read" in found.why


def test_swift_unparsed_declarations_block(tmp_path) -> None:
    files = {
        "A.swift": "class A: P {\n    func f() {\n    }\n}\n",
        # The grammar does not recover this protocol header.
        "P.swift": "protocol P: ( {\n    func f()\n}\n",
    }
    found = _swift(tmp_path, files, "A.swift", "f", _Index(files))
    assert found is not None and "P.swift:1 could not be parsed" in found.why


def test_swift_known_requirements_and_nested_names(tmp_path) -> None:
    files = {
        "A.swift": (
            "struct A: Hashable {\n    func hash(into h: inout Hasher) {\n    }\n}\n\n"
            "struct B: Outer.Kind {\n    func g() {\n    }\n}\n\n"
            "enum Outer {\n    protocol Kind {\n    }\n}\n"
        )
    }
    index = _Index(files)
    found = _swift(tmp_path, files, "A.swift", "hash", index)
    assert found is not None and "`Hashable` requires" in found.why
    # `Kind` is declared only nested in the project: it may be an outside type.
    found = _swift(tmp_path, files, "A.swift", "g", index)
    assert found is not None and "`Kind`" in found.why


def test_swift_project_protocol_requirements_check_the_call_sites(tmp_path) -> None:
    files = {
        "A.swift": (
            "protocol Runner {\n    func run()\n}\n\n"
            "extension Runner {\n    func run() {\n    }\n}\n\n"
            "final class Job: Runner {\n    func run() {\n    }\n}\n"
        ),
        "B.swift": "func go(r: Runner) {\n    r.run()\n}\n",
    }
    closed = _swift(
        tmp_path, files, "A.swift", "run", _Index(files), "    func run() {"
    )
    assert closed is None
    index = _Index(files, calls=[("run", "B.swift", 2)])
    found = _swift(tmp_path, files, "A.swift", "run", index, "    func run() {")
    assert found is not None and "project protocol `Runner`" in found.why
    assert "B.swift:2" in found.why


def test_swift_conformance_closure_too_large_blocks(tmp_path) -> None:
    chain = "".join(f"protocol P{i}: P{i + 1} {{\n}}\n" for i in range(70))
    files = {"A.swift": chain + "class A: P0 {\n    func f() {\n    }\n}\n"}
    found = _swift(tmp_path, files, "A.swift", "f", _Index(files))
    assert found is not None and "too many" in found.why


def test_swift_method_of_a_type_the_grammar_failed_on_blocks(tmp_path) -> None:
    files = {
        "A.swift": (
            "#if os(iOS)\nfinal class A: Base {\n"
            "    func work() async {\n        await other()\n    }\n}\n#endif\n"
        )
    }
    found = _swift(tmp_path, files, "A.swift", "work", _Index(files))
    # Blocked either way: the grammar may or may not recover this file.
    assert found is not None
    assert "could not be parsed" in found.why or "`Base`" in found.why


# --------------------------------------------------------------------- C#


def test_csharp_global_directives_that_cannot_be_read_block(tmp_path) -> None:
    files = {
        "I.cs": "namespace P { public interface IShape { int Area(); } }\n",
        "S.cs": "using P;\npublic class Sq : IShape { public int Area() { return 1; } }\n",
    }
    assert _cs(tmp_path, files, "S.cs", "Area", _Index(files)) is None
    found = _cs(tmp_path, files, "S.cs", "Area", _Index(files, unlisted=["G.cs"]))
    assert found is not None and "global using" in found.why
    broken = {**files, "G.cs": "#if X\nglobal using IShape = (;\n#endif\n"}
    found = _cs(tmp_path, broken, "S.cs", "Area", _Index(broken))
    assert found is not None and "global using" in found.why


def test_csharp_msbuild_using_items_are_global_directives(tmp_path) -> None:
    files = {
        "I.cs": "namespace P { public interface IShape { int Area(); } }\n",
        "src/S.cs": (
            "using P;\npublic class Sq : IShape { public int Area() { return 1; } }\n"
        ),
        "src/App.csproj": '<Project><ItemGroup><Using Include="Ext.IThing" '
        'Alias="IShape" /></ItemGroup></Project>\n',
    }
    found = _cs(tmp_path, files, "src/S.cs", "Area", _Index(files))
    assert found is not None and "alias" in found.why
    assert _items(
        '<Using Include="System.Math" Static="true" /><Using Remove="X" />'
        '<Using Include="System.Linq" />'
    ) == [("static", "System.Math"), ("ns", "System.Linq")]


def test_csharp_subclass_branches(tmp_path) -> None:
    files = {
        "A.cs": (
            "public interface IRun { void Run(); }\n"
            "public class Engine { public void Run() { } }\n"
            "public class Car : Engine { }\n"
            "public class Truck : Car, IRun { }\n"
            "public class Solo { public void Run() { } }\n"
            "public class Sub : Solo { }\n"
            "public class Bad : Ext.Solo { }\n"
        )
    }
    index = _Index(files, calls=[("Run", "A.cs", 99)])
    found = _cs(tmp_path, files, "A.cs", "Run", index, "class Engine")
    assert found is not None and "Truck" in found.why and "IRun" in found.why
    found = _cs(tmp_path, files, "A.cs", "Run", _Broken(), "class Engine")
    assert found is not None
    found = _cs(tmp_path, files, "A.cs", "Run", index, "class Solo")
    assert found is not None and "may derive from it" in found.why


def test_csharp_subclass_closure_too_large_blocks(tmp_path) -> None:
    chain = "".join(f"public class C{i + 1} : C{i} {{ }}\n" for i in range(70))
    files = {"A.cs": "public class C0 { public void M() { } }\n" + chain}
    found = _cs(tmp_path, files, "A.cs", "M", _Index(files))
    assert found is not None and "too many" in found.why


def test_csharp_static_members_and_interfaces(tmp_path) -> None:
    files = {
        "A.cs": (
            "public interface IMake { static abstract object Make(); void Inst(); }\n"
            "public interface IStat { static int Inst() => 1; }\n"
            "public class Maker : IMake, IStat {\n"
            "    public static object Make() { return null; }\n"
            "    public static void Inst() { }\n"
            "    public void Run() { }\n"
            "}\n"
            "public class Err : System.Exception { public static Err Of() { return null; } }\n"
            "public struct Num : INumber<Num> { public static Num One() { return default; } }\n"
        )
    }
    index = _Index(files, calls=[("Make", "B.cs", 3)])
    found = _cs(tmp_path, files, "A.cs", "Make", index, "public static object Make(")
    assert found is not None and "IMake" in found.why
    # A static method does not implement an instance member, nor a static one
    # that is not abstract or virtual.
    assert _cs(tmp_path, files, "A.cs", "Inst", index, "static void Inst(") is None
    assert _cs(tmp_path, files, "A.cs", "Of", index) is None
    found = _cs(tmp_path, files, "A.cs", "One", index)
    assert found is not None and "INumber" in found.why


def test_csharp_subclass_interfaces_closed_in_the_project_pass(tmp_path) -> None:
    files = {
        "A.cs": (
            "public interface IRun { void Run(); int Speed { get; } }\n"
            "public class Engine { public void Run() { } }\n"
            "public record Car(int X) : Engine, IRun { public int Speed => 1; }\n"
        ),
        "Other.cs": "public class Unrelated { }\n",
    }
    # `IRun.Run` is declared, but no call edge may dispatch through it.
    assert _cs(tmp_path, files, "A.cs", "Run", _Index(files), "class Engine") is None


def test_csharp_subclass_scan_fails_closed(tmp_path) -> None:
    files = {
        "A.cs": "public class Engine { public void Run() { } }\n",
        "B.cs": "public class Bad : Engine, ( { }\n",
    }
    found = _cs(tmp_path, files, "A.cs", "Run", _Index(files), "class Engine")
    assert found is not None and "B.cs" in found.why
    ok = {"A.cs": files["A.cs"]}
    found = _cs(tmp_path, ok, "A.cs", "Run", _Index(ok, unlisted=["G.cs"]))
    assert found is not None and "G.cs could not be read" in found.why
    index = _Index(ok)
    index.get_conn().execute("DROP TABLE ast_index")
    found = _cs(tmp_path, ok, "A.cs", "Run", index)
    assert found is not None and "could not be listed" in found.why


def test_csharp_static_scan_shapes(tmp_path) -> None:
    chain = "".join(f"public interface I{i} : I{i + 1} {{ }}\n" for i in range(70))
    files = {
        "A.cs": chain
        + "public interface I70 { }\n"
        + "public struct Big : I0 { public static void Make() { } }\n"
        + "public class Obj : object { public static void Of() { } }\n"
        + "public class Base { }\n"
        + "public record Rec(int X) : Base { public static void New() { } }\n"
        + "public record Kid(int X) : Rec(X) { }\n",
    }
    index = _Index(files)
    found = _cs(tmp_path, files, "A.cs", "Make", index)
    assert found is not None and "too many" in found.why
    assert _cs(tmp_path, files, "A.cs", "Of", index) is None
    assert _cs(tmp_path, files, "A.cs", "New", index) is None


def test_csharp_unreadable_msbuild_file_blocks(tmp_path) -> None:
    files = {
        "I.cs": "namespace P { public interface IShape { int Area(); } }\n",
        "S.cs": "using P;\npublic class Sq : IShape { public int Area() { return 1; } }\n",
    }
    (tmp_path / "Odd.csproj").mkdir()
    found = _cs(tmp_path, files, "S.cs", "Area", _Index(files))
    assert found is not None and "global using" in found.why


def test_csharp_class_header_lost_to_a_syntax_error_blocks(tmp_path) -> None:
    files = {
        "A.cs": "public class Engine { public void Run() { } }\n",
        # No class node: the grammar leaves the whole header in an ERROR node.
        "B.cs": "public class Lost : Engine } {\n",
    }
    found = _cs(tmp_path, files, "A.cs", "Run", _Index(files), "class Engine")
    assert found is not None and "syntax error" in found.why
