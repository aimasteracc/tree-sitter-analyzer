"""RFC-0043 Phase C: the owner class of a Python member comes from a member
table kept per content digest, and picks what the whole-tree walk picked."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools import callers_py_members as members
from tree_sitter_analyzer.mcp.tools import callers_py_supertypes as walk
from tree_sitter_analyzer.resident import parse_facts

_SOURCE = (
    "import functools\n"
    "x = 1\n"
    "class A:\n"
    "    a = b = a = 2\n"
    "    c: int = 3\n"
    "    d: int\n"
    "    @functools.cache\n"
    "    @staticmethod\n"
    "    def m(): return 1\n"
    "    if True:\n"
    "        def m(self): return 2\n"
    "    class Inner:\n"
    "        def m(self):\n"
    "            def m(): pass\n"
    "            return m\n"
    "        m = m; n = 1\n"
    "    async def am(self):\n"
    "        x = 1\n"
    "def m():\n"
    "    class Local:\n"
    "        def m(self): pass\n"
    "    return Local\n"
    "class B(A): m = 1; x = 2\n"
    "class C:\n"
    "    def f(self): pass\n"
    "    def f(self): pass\n"
    "    def m(self): m = 1\n"
)
_NAMES = ("a", "b", "c", "d", "m", "n", "x", "am", "f", "missing")


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(parse_facts.ENV_VAR, raising=False)
    monkeypatch.delenv("TSA_RESIDENT", raising=False)
    parse_facts.clear()
    walk.clear_parsed()
    yield
    parse_facts.clear()
    walk.clear_parsed()


def _walk_owner(module: Any, line: int, bare: str) -> ast.ClassDef | None:
    """The pre-Phase-C ``_owner_class``: a walk over the whole tree."""
    best: Any = None
    for node in ast.walk(module.tree):
        if not walk._declares(node, bare):
            continue
        first = min(
            [node.lineno, *(d.lineno for d in getattr(node, "decorator_list", ()))]
        )
        if not first <= line <= (node.end_lineno or node.lineno):
            continue
        if best is None or node.lineno >= best.lineno:
            best = node
    parent = None if best is None else module.parents.get(id(best))
    return parent if isinstance(parent, ast.ClassDef) else None


def _module(text: str) -> Any:
    module = walk._parse("k.py", text.encode("utf-8"))
    if module is None:
        raise AssertionError("fixture must parse")
    return module


def _every_owner(module: Any) -> list[tuple[int, str, int | None]]:
    lines = range(0, _SOURCE.count("\n") + 2)
    return [
        (line, bare, None if owner is None else id(owner))
        for line in lines
        for bare in _NAMES
        for owner in [walk._owner_class(module, line, bare)]
    ]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_owner_equals_the_whole_tree_walk_on_every_line(newline: str) -> None:
    module = _module(_SOURCE.replace("\n", newline))
    lines = range(0, _SOURCE.count("\n") + 2)

    for line in lines:
        for bare in _NAMES:
            assert walk._owner_class(module, line, bare) is _walk_owner(
                module, line, bare
            ), (line, bare)
    owned = {
        (line, bare)
        for line in lines
        for bare in _NAMES
        if walk._owner_class(module, line, bare) is not None
    }
    assert (9, "m") in owned and (11, "m") not in owned and (13, "m") in owned
    # Same line, walk order: the assignment inside `m` comes last and wins.
    assert (27, "m") not in owned


def test_memo_on_and_off_give_the_same_owners(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module(_SOURCE)
    monkeypatch.setenv(parse_facts.ENV_VAR, "0")
    off = _every_owner(module)
    assert parse_facts.stats()["entries"] == 0
    monkeypatch.delenv(parse_facts.ENV_VAR)
    on = _every_owner(module)
    again = _every_owner(module)

    assert off == on == again
    assert parse_facts.stats()["misses"] == 1  # one table per content


def test_table_is_built_once_per_content(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    real = members.build_member_table

    def counting(tree: ast.Module):
        calls.append(1)
        return real(tree)

    monkeypatch.setattr(members, "build_member_table", counting)
    first, second = _module(_SOURCE), _module(_SOURCE)  # two parses, same bytes
    walk._owner_class(first, 9, "m")
    walk._owner_class(second, 13, "m")
    walk._owner_class(_module(_SOURCE + "\n"), 9, "m")

    assert len(calls) == 2


def test_table_holds_no_syntax_tree() -> None:
    table = members.build_member_table(_module(_SOURCE).tree)

    def plain(value: Any) -> bool:
        if isinstance(value, tuple):
            return all(plain(item) for item in value)
        return value is None or isinstance(value, str | int)

    assert table and plain(table)


def test_without_a_digest_the_table_is_built_live() -> None:
    module = _module(_SOURCE)

    assert members.member_table(b"", module.tree) == members.build_member_table(
        module.tree
    )
    assert parse_facts.stats()["entries"] == 0


def test_entry_bound_keeps_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parse_facts, "MAX_ENTRIES", 1)
    one, two = _module(_SOURCE), _module(_SOURCE + "y = 1\n")
    for _ in range(2):
        for module in (one, two):
            assert walk._owner_class(module, 9, "m") is _walk_owner(module, 9, "m")

    assert parse_facts.stats()["entries"] == 1


def _write(root: Path, text: str) -> str:
    # Bytes, not text: no newline translation, so each edit below has its own size.
    (root / "k.py").write_bytes(text.encode("utf-8"))
    return str(root)


def test_an_edit_is_read_again(tmp_path: Path) -> None:
    root = _write(tmp_path, "class A:\n    def m(self):\n        pass\n")
    name, _found = walk.python_dynamic_base(root, "k.py", 2, "m", frozenset)
    assert name == "A"
    # A different size: the evidence file cache's stamp changes and it reads again.
    _write(tmp_path, "def m():\n    pass\n\n\nclass Z:\n    pass\n")
    moved, _found = walk.python_dynamic_base(root, "k.py", 2, "m", frozenset)
    _write(tmp_path, "class Zed:\n    def m(self):\n        pass\n")
    renamed, _found = walk.python_dynamic_base(root, "k.py", 2, "m", frozenset)

    assert moved is None
    assert renamed == "Zed"


def test_dynamic_base_is_identical_with_the_memo_off(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    text = "def mix(c):\n    return c\nclass B:\n    pass\nclass A(mix(B)):\n" + (
        "    def m(self):\n        pass\n"
    )
    root = _write(tmp_path, text)
    monkeypatch.setenv(parse_facts.ENV_VAR, "0")
    off = walk.python_dynamic_base(root, "k.py", 6, "m", frozenset)
    walk.clear_parsed()
    monkeypatch.delenv(parse_facts.ENV_VAR)
    on = walk.python_dynamic_base(root, "k.py", 6, "m", frozenset)
    again = walk.python_dynamic_base(root, "k.py", 6, "m", frozenset)

    assert off == on == again
    assert off[0] == "A" and off[1] is not None and "a call" in off[1].why
