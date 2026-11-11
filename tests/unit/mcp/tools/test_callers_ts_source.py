"""PR-3: JS/TS class facts read from source (``callers_ts_source``).

Each helper answers "cannot prove" for any shape it does not understand, so the
graph-bound site it guards stays counted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools import callers_ts_source as S
from tree_sitter_analyzer.mcp.tools.callers_ts_source import (
    SourceReader,
    chain_avoids,
    class_escapes,
    clear_parsed,
    this_is_method_receiver,
)


def _reader(root: Path, files: dict[str, str]) -> SourceReader:
    clear_parsed()
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return SourceReader(str(root))


# ------------------------------------------------------------ module paths
@pytest.mark.parametrize(
    ("spec", "present", "expected"),
    [
        ("./base", ["src/base.ts"], "src/base.ts"),
        ("./base.js", ["src/base.ts"], "src/base.ts"),
        ("./base.js", ["src/base.js"], "src/base.js"),
        ("./base.mjs", ["src/base.mts"], "src/base.mts"),
        ("./base.ts", ["src/base.ts"], "src/base.ts"),
        ("./lib", ["src/lib/index.ts"], "src/lib/index.ts"),
        ("../top", ["top.ts"], "top.ts"),
        # Two candidates (a TS and a JS file): ambiguous.
        ("./base", ["src/base.ts", "src/base.js"], None),
        ("./missing", [], None),
        ("./data.json", ["src/data.json"], None),
        ("pkg", [], None),
        ("../../outside", [], None),
    ],
)
def test_resolve_module(
    tmp_path: Path, spec: str, present: list[str], expected: str | None
) -> None:
    reader = _reader(tmp_path, dict.fromkeys(present, "export const x = 1\n"))
    assert reader.resolve_module("src/a.ts", spec) == expected


def test_unreadable_or_foreign_files_do_not_parse(tmp_path: Path) -> None:
    reader = _reader(tmp_path, {"a.py": "x = 1\n"})
    assert reader.read("a.py") is None
    assert reader.read("missing.ts") is None


# ------------------------------------------------------------- this receiver
_METHODS = (
    "class C {\n"  # 1
    "  run() {\n"  # 2
    "    return this.m()\n"  # 3
    "  }\n"  # 4
    "  arrow() {\n"  # 5
    "    return [1].map(() => this.m())\n"  # 6
    "  }\n"  # 7
    "  fn() {\n"  # 8
    "    return [1].map(function () { return this.m() })\n"  # 9
    "  }\n"  # 10
    "  static s() {\n"  # 11
    "    return this.m()\n"  # 12
    "  }\n"  # 13
    "  obj() {\n"  # 14
    "    return { k() { return this.m() } }\n"  # 15
    "  }\n"  # 16
    "  field = () => this.m()\n"  # 17
    "  m() {\n"  # 18
    "    return 1\n"  # 19
    "  }\n"  # 20
    "}\n"  # 21
)


@pytest.mark.parametrize(
    ("line", "method_line", "expected"),
    [
        (3, 2, True),
        (6, 5, True),  # arrow functions keep the method's `this`
        (9, 8, False),  # a `function` binds its own `this`
        (12, 11, False),  # static: `this` is the constructor
        (15, 14, False),  # an object literal method
        (17, 17, False),  # a field initializer
        (3, 5, False),  # not the caller's method
    ],
)
def test_this_is_method_receiver(
    tmp_path: Path, line: int, method_line: int, expected: bool
) -> None:
    source = _reader(tmp_path, {"c.ts": _METHODS}).read("c.ts")
    assert source is not None
    assert this_is_method_receiver(source, line, "m", "C", method_line) is expected


def test_this_receiver_needs_one_class_and_a_clean_parse(tmp_path: Path) -> None:
    reader = _reader(
        tmp_path,
        {
            "twice.ts": _METHODS + "function f() {\n  class C {}\n}\n",
            "broken.ts": _METHODS + "class {{{\n",
        },
    )
    twice, broken = reader.read("twice.ts"), reader.read("broken.ts")
    assert twice is not None and broken is not None
    assert this_is_method_receiver(twice, 3, "m", "C", 2) is False
    assert this_is_method_receiver(broken, 3, "m", "C", 2) is False
    assert this_is_method_receiver(twice, 3, "m", "D", 2) is False


# ------------------------------------------------------------- extends chain
@pytest.mark.parametrize(
    ("files", "expected"),
    [
        # Root class, same-file chain, cross-file named import, JS grammar.
        ({"t.ts": "class T {}\n"}, True),
        ({"t.ts": "class A {}\nclass T extends A<number> {}\n"}, True),
        (
            {
                "t.ts": "import { B as A } from './b'\nclass T extends A {}\n",
                "b.ts": "export class B {}\n",
            },
            True,
        ),
        ({"t.js": "class A {}\nclass T extends A {}\n"}, True),
        # The chain reaches the forbidden class.
        ({"t.ts": "class C {}\nclass T extends C {}\n"}, False),
        (
            {
                "t.ts": "import { C } from './c'\nclass T extends C {}\n",
                "c.ts": "export class C {}\n",
            },
            False,
        ),
        # Shapes that cannot be read: fail closed.
        ({"t.ts": "class T extends mix(A) {}\n"}, False),
        ({"t.ts": "import * as ns from './n'\nclass T extends ns.A {}\n"}, False),
        ({"t.ts": "import { A } from 'pkg'\nclass T extends A {}\n"}, False),
        ({"t.ts": "class T extends Unknown {}\n"}, False),
        ({"t.ts": "class A {}\nclass A {}\nclass T extends A {}\n"}, False),
        (
            {
                "t.ts": "import { A } from './a'\nclass A {}\nclass T extends A {}\n",
                "a.ts": "export class A {}\n",
            },
            False,
        ),
        (
            {
                "t.ts": "import { A } from './a'\nclass T extends A {}\n",
                "a.ts": "export { A } from './z'\n",
            },
            False,
        ),
        ({"t.ts": "class A extends T {}\nclass T extends A {}\n"}, False),
        ({"t.ts": "class T {}\nclass T {}\n"}, False),
        ({"t.ts": "class T extends A {{{\n"}, False),
    ],
)
def test_chain_avoids(tmp_path: Path, files: dict[str, str], expected: bool) -> None:
    reader = _reader(tmp_path, files)
    rel = next(iter(files))
    forbidden = ("c.ts", "C") if "c.ts" in files else (rel, "C")
    assert chain_avoids(reader, rel, "T", forbidden) is expected


def test_chain_of_an_unreadable_file_fails(tmp_path: Path) -> None:
    reader = _reader(tmp_path, {})
    assert chain_avoids(reader, "t.ts", "T", ("c.ts", "C")) is False


# ------------------------------------------------------------- value escapes
_DECL = "export class T {\n  m() {\n    return 1\n  }\n  static make() {\n    return new T()\n  }\n}\n"


@pytest.mark.parametrize(
    ("use", "escapes"),
    [
        # Passive: construct, subclass, static member, instanceof, types, matchers.
        ("new T()", False),
        ("class S extends T {}", False),
        ("T.make()", False),
        ("x instanceof T", False),
        ("let v: typeof T", False),
        ("let w: T", False),
        ("expect(x).toBeInstanceOf(T)", False),
        ("export { T }", False),
        # Value uses that can reach the prototype.
        ("applyMixins(D, [T])", True),
        ("T.prototype.m = f", True),
        ("const K = T", True),
        ("register({ T })", True),
        ("export { T as U }", True),
        ("export default T", True),
        ("call(T)", True),
    ],
)
def test_class_escapes_in_the_declaring_file(
    tmp_path: Path, use: str, escapes: bool
) -> None:
    reader = _reader(tmp_path, {"t.ts": _DECL + use + "\n"})
    assert class_escapes(reader, ["t.ts"], "t.ts", "T") is escapes


@pytest.mark.parametrize(
    ("files", "escapes"),
    [
        # Named import of the class, then passed on.
        ({"u.ts": "import { T } from './t'\nuse(T)\n"}, True),
        ({"u.ts": "import { T } from './t'\nnew T()\n"}, False),
        # Aliased import: the alias's uses are not followed.
        ({"u.ts": "import { T as Z } from './t'\nnew Z()\n"}, True),
        # Namespace object read by name or passed through.
        ({"u.ts": "import * as ns from './t'\nuse(ns.T)\n"}, True),
        ({"u.ts": "import * as ns from './t'\nuse(ns['T'])\n"}, True),
        ({"u.ts": "import * as ns from './t'\nnew ns.T()\n"}, False),
        ({"u.ts": "const ns = require('./t')\nuse(ns.T)\n"}, True),
        # Another module's own `T`: not this class.
        (
            {
                "u.ts": "import * as o from './o'\nuse(o.T)\n",
                "o.ts": "export const T = 1\n",
            },
            False,
        ),
        (
            {
                "u.ts": "import { T } from './o'\nuse(T)\n",
                "o.ts": "export class T {}\n",
            },
            False,
        ),
        # A module that may pass this class on.
        (
            {
                "u.ts": "import * as o from './o'\nuse(o.T)\n",
                "o.ts": "export * from './t'\n",
            },
            True,
        ),
        (
            {
                "u.ts": "import { T } from './o'\nuse(T)\n",
                "o.ts": "import { T } from './t'\nexport { T }\n",
            },
            True,
        ),
        # The file declares its own `T`.
        ({"u.ts": "class T {}\nuse(T)\n"}, False),
        ({"u.ts": "const T = 1\nuse(T)\n"}, False),
        # A file the grammar cannot read cleanly: identifiers in error regions escape.
        ({"u.ts": "import { T } from './t'\nuse(T {{{\n"}, True),
        # An enum member of the same name is not the class.
        ({"u.ts": "enum Kind { T = 'T' }\nuse(Kind.T)\n"}, False),
    ],
)
def test_class_escapes_across_files(
    tmp_path: Path, files: dict[str, str], escapes: bool
) -> None:
    reader = _reader(tmp_path, {"t.ts": _DECL, **files})
    assert class_escapes(reader, sorted(files), "t.ts", "T") is escapes


def test_unreadable_listed_file_escapes(tmp_path: Path) -> None:
    reader = _reader(tmp_path, {"t.ts": _DECL})
    assert class_escapes(reader, ["gone.ts"], "t.ts", "T") is True
    assert class_escapes(reader, ["t.ts"], "t.ts", "T") is False


# ------------------------------------------------------------ edge shapes
def test_receiver_shapes_without_a_matching_this_call(tmp_path: Path) -> None:
    reader = _reader(
        tmp_path,
        {
            "c.ts": _METHODS,
            "bare.ts": "class C {\n  run() {\n    return m()\n  }\n}\n",
        },
    )
    source, bare = reader.read("c.ts"), reader.read("bare.ts")
    assert source is not None and bare is not None
    assert this_is_method_receiver(source, 1, "m", "C", 2) is False
    assert this_is_method_receiver(source, 15, "m", "C", 15) is False
    assert this_is_method_receiver(bare, 3, "m", "C", 2) is False


def test_chain_longer_than_the_bound_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader = _reader(
        tmp_path, {"t.ts": "class A {}\nclass B extends A {}\nclass T extends B {}\n"}
    )
    monkeypatch.setattr(S, "_CHAIN_MAX", 1)
    assert chain_avoids(reader, "t.ts", "T", ("c.ts", "C")) is False


def test_memoized_parse_is_reused_and_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reader(tmp_path, {"a.ts": "class A {}\n", "b.ts": "class B {}\n"})

    class _Fixed:
        def read_stamped(self, path: str) -> tuple[bytes, tuple[int, ...]] | None:
            data = Path(path).read_bytes() if Path(path).exists() else None
            return None if data is None else (data, (len(data), 1, 1, 1, 1))

    monkeypatch.setattr(S, "FILE_CACHE", _Fixed())
    monkeypatch.setattr(S, "_PARSED_MAX", 1)
    first = SourceReader(str(tmp_path)).read("a.ts")
    again = SourceReader(str(tmp_path)).read("a.ts")
    assert first is not None and again is first
    assert SourceReader(str(tmp_path)).read("b.ts") is not None
    assert len(S._PARSED) == 1


@pytest.mark.parametrize("mode", ["none", "raise"])
def test_grammar_failure_reads_as_unparsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    import tree_sitter_analyzer.language_loader as loader

    def broken(_language: str) -> object:
        if mode == "raise":
            raise RuntimeError("no grammar")
        return None

    reader = _reader(tmp_path, {"a.ts": "class A {}\n"})
    monkeypatch.setattr(loader, "create_parser_safely", broken)
    assert reader.read("a.ts") is None


def test_import_and_require_shapes_are_collected(tmp_path: Path) -> None:
    text = (
        "import './side'\n"
        "import Def from './d'\n"
        "import * as ns from './n'\n"
        "import { a, b as c } from './m'\n"
        "const { x } = require('./r')\n"
        "const req = require('./q')\n"
        "const dyn = await import('./w')\n"
        "export { a } from './m'\n"
        "export * from './s'\n"
        "export const v = 1, w = 2\n"
        "export function f() {}\n"
        "export enum E { A }\n"
        "let { y } = z\n"
    )
    source = _reader(tmp_path, {"u.ts": text}).read("u.ts")
    assert source is not None
    assert source.module_bindings == {
        "Def": "./d",
        "ns": "./n",
        "req": None,
        "dyn": None,
    }
    assert source.named_imports == {"a": ("./m", "a"), "c": ("./m", "b")}
    assert {"a", "*"} <= source.reexports
    assert {"v", "w", "f", "E"} <= source.exported_values


@pytest.mark.parametrize(
    ("files", "escapes"),
    [
        # Declared and imported at once: cannot tell which a use means.
        ({"u.ts": "import { T } from './t'\nclass T {}\nuse(T)\n"}, True),
        # The module may export this class: it has syntax errors, re-exports the
        # name, or declares nothing of that name.
        (
            {"u.ts": "import * as o from './o'\nuse(o.T)\n", "o.ts": "export {{{\n"},
            True,
        ),
        (
            {
                "u.ts": "import * as o from './o'\nuse(o.T)\n",
                "o.ts": "export { T } from './t'\n",
            },
            True,
        ),
        (
            {
                "u.ts": "import * as o from './o'\nuse(o.T)\n",
                "o.ts": "export const X = 1\n",
            },
            True,
        ),
        # Its own `T` shadows: a shorthand use is not this class.
        ({"u.ts": "const T = 1\nregister({ T })\n"}, False),
        # A default import binding, then constructed.
        ({"u.ts": "import T from './t'\nnew T()\n"}, False),
        # JavaScript class names are identifiers.
        ({"u.js": "class T {}\nnew T()\n"}, False),
        # Not an `instanceof` matcher.
        ({"u.ts": "import { T } from './t'\nnew Box(T)\n"}, True),
        ({"u.ts": "import { T } from './t'\nexpect(x)[k](T)\n"}, True),
    ],
)
def test_more_escape_shapes(
    tmp_path: Path, files: dict[str, str], escapes: bool
) -> None:
    reader = _reader(tmp_path, {"t.ts": _DECL, **files})
    assert class_escapes(reader, sorted(files), "t.ts", "T") is escapes


def test_escape_scan_bounds_and_unparsed_hits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader = _reader(tmp_path, {"t.ts": _DECL, "notes.py": "T = 1\n"})
    assert class_escapes(reader, ["notes.py"], "t.ts", "T") is True
    monkeypatch.setattr(S, "_ESCAPE_FILES_MAX", 0)
    assert class_escapes(reader, ["t.ts"], "t.ts", "T") is True


def test_node_helpers_on_the_root(tmp_path: Path) -> None:
    source = _reader(tmp_path, {"t.ts": _DECL + "use(T)\n"}).read("t.ts")
    assert source is not None
    assert S._field(source.root) is None
    assert S._passive_use(source, source.root) is False
    assert S._instanceof_matcher(source, None) is False
    assert S._escapes_in(source, "T") is True
