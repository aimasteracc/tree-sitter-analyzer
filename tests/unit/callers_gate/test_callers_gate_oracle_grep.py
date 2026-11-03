"""The grep oracle's hit classifier on small Java / TS repos (real tree-sitter parses)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from benchmarks.callers_gate.oracle_grep import Item, Repo, check_item
from benchmarks.callers_gate.oracle_scope import owner_at
from benchmarks.callers_gate.oracle_syntax import family

pytest.importorskip("tree_sitter_java")
pytest.importorskip("tree_sitter_typescript")
#: Each test builds a real git repo and runs git grep (subprocess cost, not CPU).
pytestmark = pytest.mark.slow_ok

WIDGET = """package com.example;

/** Calls render() from draw. */
public class Widget {
  // render is cheap
  void render() {}
  void draw() { render(); }
  String s = "use render here";
  String k = "render";
}
"""
OTHER = """package com.example;

class Unrelated {
  void render() {}
  void go() { render(); this.render(); }
}

class Sub extends Widget {
  void go() { render(); }
}

class Caller {
  void x(Widget w) { w.render(); Unrelated.render(); }
  void y() { new Object() { void z() { render(); } }; }
}
"""
PARSE_TS = """export function parse(x: string) {
  return x;
}
"""
USES_TS = """import { parse } from 'external-lib';
export const a = parse('1');
"""
LOCAL_TS = """import { parse } from './parse';
import { parse as p2 } from 'mylib';
export const b = parse('2');
"""


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


def _line(text: str, needle: str) -> int:
    return next(
        i for i, line in enumerate(text.splitlines(), start=1) if needle in line
    )


def _classes(result: dict[str, object]) -> list[tuple[str, int, str]]:
    hits = result["hits"]
    assert isinstance(hits, list)
    return [(h["file"], h["line"], h["class"]) for h in hits]


def test_java_hits_are_classified(tmp_path: Path) -> None:
    root = _git_repo(
        tmp_path,
        {
            "src/Widget.java": WIDGET,
            "src/Other.java": OTHER,
            "README.md": "Call render() first.\n",
        },
    )
    draw = _line(WIDGET, "void draw")
    item = Item(
        key=["bare", "src/Widget.java", "Widget.render"],
        name="render",
        file="src/Widget.java",
        qual="Widget.render",
        callers=[{"file": "src/Widget.java", "name": "draw", "line": draw}],
    )
    result = check_item(Repo(root), item)
    got = _classes(result)
    w, o = "src/Widget.java", "src/Other.java"
    assert got == [
        ("README.md", 1, "non_code"),
        (o, _line(OTHER, "class Unrelated") + 1, "declaration"),
        (o, _line(OTHER, "this.render"), "other_symbol"),
        (o, _line(OTHER, "this.render"), "other_symbol"),
        (o, _line(OTHER, "class Sub") + 1, "residual"),
        (o, _line(OTHER, "w.render"), "residual"),
        (o, _line(OTHER, "w.render"), "other_symbol"),
        (o, _line(OTHER, "new Object"), "residual"),
        (w, _line(WIDGET, "Calls render"), "comment"),
        (w, _line(WIDGET, "render is cheap"), "comment"),
        (w, _line(WIDGET, "void render"), "own_declaration"),
        (w, draw, "caller"),
        (w, _line(WIDGET, "use render here"), "string"),
        (w, _line(WIDGET, 'k = "render"'), "residual"),
    ]
    whys = {(h["line"], h["why"]) for h in result["hits"] if h["class"] == "residual"}  # type: ignore[union-attr]
    assert any("related to Widget" in why for _line_no, why in whys)
    assert any("possible dynamic dispatch" in why for _line_no, why in whys)
    assert result["counts"]["residual"] == 4  # type: ignore[index]


def test_ts_external_imports_prove_a_different_symbol(tmp_path: Path) -> None:
    root = _git_repo(
        tmp_path,
        {
            "package.json": '{"name": "mylib", "dependencies": {"external-lib": "1"}}\n',
            "src/parse.ts": PARSE_TS,
            "src/uses.ts": USES_TS,
            "src/local.ts": LOCAL_TS,
        },
    )
    item = Item(
        key=["bare", "src/parse.ts", "parse"],
        name="parse",
        file="src/parse.ts",
        qual="parse",
        callers=[],
    )
    got = _classes(check_item(Repo(root), item))
    assert got == [
        ("src/local.ts", 1, "import_export"),
        ("src/local.ts", 1, "string"),
        ("src/local.ts", 2, "import_export"),
        ("src/local.ts", 3, "residual"),
        ("src/parse.ts", 1, "own_declaration"),
        ("src/uses.ts", 1, "import_export"),
        ("src/uses.ts", 2, "other_symbol"),
    ]


def test_a_project_package_import_is_not_external(tmp_path: Path) -> None:
    root = _git_repo(
        tmp_path,
        {
            "package.json": '{"name": "mylib"}\n',
            "src/parse.ts": PARSE_TS,
            "src/self.ts": "import { parse } from 'mylib';\nparse('3');\n",
        },
    )
    item = Item(
        key=["bare", "src/parse.ts", "parse"],
        name="parse",
        file="src/parse.ts",
        qual="parse",
        callers=[],
    )
    got = _classes(check_item(Repo(root), item))
    assert ("src/self.ts", 2, "residual") in got


ANON_BASE = """package com.example;

abstract class Fields<T> {
  abstract long[] values(T t);
  void write(T t) { long[] v = values(t); }
}
"""
ANON_OUTER = """package com.example;

final class Adapters {
  static final Fields<String> STRINGS = new Fields<String>() {
    @Override long[] values(String s) { return new long[0]; }
  };
}
"""


def test_a_target_declared_in_an_anonymous_class_is_never_proven_unrelated(
    tmp_path: Path,
) -> None:
    # qual says Adapters.values, but the method belongs to an anonymous
    # subclass of Fields: Fields.write's call can dispatch to it.
    root = _git_repo(
        tmp_path, {"src/Fields.java": ANON_BASE, "src/Adapters.java": ANON_OUTER}
    )
    item = Item(
        key=["bare", "src/Adapters.java", "Adapters.values"],
        name="values",
        file="src/Adapters.java",
        qual="Adapters.values",
        callers=[],
    )
    hits = check_item(Repo(root), item)["hits"]
    call = [
        h for h in hits if h["file"] == "src/Fields.java" and "v = values" in h["text"]
    ]
    assert [h["class"] for h in call] == ["residual"]
    assert "not declared directly" in call[0]["why"]


ALIAS_TS = """import { Widget as W } from './widget';
export class Sub extends W {
  go() { this.render(); }
}
export class Plain {
  go() { this.render(); }
  render() {}
}
"""
WIDGET_TS = """export class Widget {
  render() {}
}
"""


def test_an_aliased_superclass_keeps_this_calls_residual(tmp_path: Path) -> None:
    root = _git_repo(tmp_path, {"src/widget.ts": WIDGET_TS, "src/sub.ts": ALIAS_TS})
    item = Item(
        key=["bare", "src/widget.ts", "Widget.render"],
        name="render",
        file="src/widget.ts",
        qual="Widget.render",
        callers=[],
    )
    got = _classes(check_item(Repo(root), item))
    assert (
        "src/sub.ts",
        3,
        "residual",
    ) in got  # Sub extends W (= Widget): may dispatch
    assert ("src/sub.ts", 6, "other_symbol") in got  # Plain is provably unrelated
    assert ("src/sub.ts", 7, "declaration") in got


SPANS_TS = """export function outer(a: number) {
  return inner(a);
}
export const arrow = (b: number) => {
  return inner(b);
};
class K {
  method() {
    return inner(1);
  }
}
run(() => inner(2));
"""


def _owner(repo: Repo, rel: str, needle: bytes, nth: int = 0) -> tuple[str, list[int]]:
    parsed = repo.tree(rel)
    assert parsed is not None
    tree, src, grammar = parsed
    start = -1
    for _ in range(nth + 1):
        start = src.index(needle, start + 1)
    node = tree.root_node.descendant_for_byte_range(start, start + len(needle))
    line = src[:start].count(b"\n") + 1
    owner = owner_at(node, family(grammar), line)
    return owner.name, sorted(owner.starts)


def test_a_hit_belongs_to_its_innermost_named_definition(tmp_path: Path) -> None:
    repo = Repo(_git_repo(tmp_path, {"src/spans.ts": SPANS_TS}))
    assert _owner(repo, "src/spans.ts", b"inner(a)") == ("outer", [1])
    assert _owner(repo, "src/spans.ts", b"inner(b)") == ("arrow", [4])
    assert _owner(repo, "src/spans.ts", b"inner(1)") == ("method", [8])
    # an anonymous callback is not a definition: the module owns its call
    assert _owner(repo, "src/spans.ts", b"inner(2)") == ("<module>", [12])
