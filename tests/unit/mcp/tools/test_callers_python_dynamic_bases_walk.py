"""#1883: the Python base walk, shape by shape (see ``callers_py_supertypes``)."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools import callers_py_supertypes as walk
from tree_sitter_analyzer.mcp.tools.callers_supertypes import (
    dynamic_supertype,
    python_project_tops,
)

_MEMBER = "    def m(self):\n        return 1\n"


def _write(root, files: dict[str, str]) -> str:
    walk.clear_parsed()
    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return str(root)


def _line_of(text: str, needle: str) -> int:
    return next(i for i, line in enumerate(text.split("\n"), 1) if needle in line)


def _why(tmp_path, files, rel="k.py", tops=frozenset(), needle="def m(", bare="m"):
    root = _write(tmp_path, files)
    _name, found = walk.python_dynamic_base(
        root, rel, _line_of(files[rel], needle), bare, lambda: tops
    )
    return None if found is None else found.why


@pytest.mark.parametrize(
    ("prelude", "clause", "why"),
    [
        (
            "def f():\n    global B\n    B = 1\nclass B:\n    pass\n",
            "B",
            "more than once",
        ),
        ("try:\n    pass\nexcept Exception as B:\n    pass\n", "B", "a value"),
        ("match 1:\n    case B:\n        pass\n", "B", "a value"),
        ("match {}:\n    case {**B}:\n        pass\n", "B", "a value"),
        ("for B in ():\n    pass\n", "B", "a value"),
        ("import os\n", "os", "a module, not a class"),
        ("class A:\n    x = 1\n", "A.x", "class attribute"),
        ("", "(lambda: object)()", "a call"),
        ("", "[object][0]", "a `List`"),
        ("class A:\n    pass\n", "A[int]", "subscripted project class"),
        ("", "object if True else int", "a conditional"),
        ("", "(B := object)", "an assignment expression"),
        ("", "object or int", "a boolean expression"),
        ("", "1", "Constant"),
    ],
)
def test_module_level_shapes(tmp_path, prelude: str, clause: str, why: str) -> None:
    text = f"{prelude}\nclass K({clause}):\n{_MEMBER}"

    found = _why(tmp_path, {"k.py": text})

    assert found is not None and why in found, found


def test_function_scope_parameters_and_imports(tmp_path) -> None:
    text = (
        "def make(*args, **kwargs):\n"
        "    from collections import OrderedDict\n"
        "    class A(OrderedDict):\n"
        "        def m(self):\n"
        "            return 1\n"
        "    class B(kwargs):\n"
        "        def m2(self):\n"
        "            return 1\n"
        "    return A, B\n"
    )

    assert _why(tmp_path, {"k.py": text}) is None
    assert "a local value" in _why(
        tmp_path, {"k.py": text}, needle="def m2(", bare="m2"
    )


def test_annotated_class_attribute_is_a_member(tmp_path) -> None:
    text = (
        "def mix(b):\n    return b\nclass K(mix(object)):\n    handler: object = None\n"
    )

    found = _why(tmp_path, {"k.py": text}, needle="handler:", bare="handler")

    assert found is not None and "a call" in found


def test_innermost_same_named_member_wins(tmp_path) -> None:
    text = (
        "def mix(b):\n    return b\n"
        "class K(mix(object)):\n"
        "    def m(self):\n"
        "        class Inner:\n"
        "            def m(self):\n"
        "                return 1\n"
        "        return Inner\n"
    )
    root = _write(tmp_path, {"k.py": text})

    name, found = walk.python_dynamic_base(root, "k.py", 6, "m", lambda: None)

    assert (name, found) == ("Inner", None)


def test_cycle_and_walk_limit(tmp_path, monkeypatch) -> None:
    cycle = "class A(B):\n    pass\nclass B(A):\n" + _MEMBER
    assert "cycle" in _why(tmp_path, {"k.py": cycle})

    chain = "class A:\n    pass\nclass B(A):\n    pass\nclass K(B):\n" + _MEMBER
    monkeypatch.setattr(walk, "_CLASSES_MAX", 2)
    assert "too many" in _why(tmp_path, {"k.py": chain})


def test_diamond_is_followed_once(tmp_path) -> None:
    text = (
        "class A:\n    pass\nclass B(A):\n    pass\nclass C(A):\n    pass\n"
        "class K(B, C):\n" + _MEMBER
    )

    assert _why(tmp_path, {"k.py": text}) is None


@pytest.mark.parametrize(
    ("meta", "why"),
    [
        ("class M(type):\n    def mro(cls):\n        return []\n", "defines `mro`"),
        (
            "def mk():\n    return type\nclass M(mk()):\n    pass\n",
            "cannot be followed",
        ),
        (
            "class M(type):\n    def __new__(mcs, *args):\n        return 1\n",
            "rebinds its bases",
        ),
        (
            "class M(type):\n    def __new__(mcs, name, bases, ns):\n"
            "        global bases\n        return type(name, (), ns)\n",
            "rebinds its bases",
        ),
        (
            "class M(type):\n    def __new__(mcs, name, bases, ns):\n"
            "        return type(name, (object,), ns)\n",
            "rebinds its bases",
        ),
        ("import os\nM = os\n", "a value"),
        ("import os as M\n", "not a metaclass"),
    ],
)
def test_metaclass_shapes(tmp_path, meta: str, why: str) -> None:
    text = f"{meta}\nclass K(metaclass=M):\n{_MEMBER}"

    found = _why(tmp_path, {"k.py": text})

    assert found is not None and why in found, found


def test_metaclass_chain_through_a_project_base(tmp_path) -> None:
    text = (
        "class Base(type):\n"
        "    def __new__(mcs, name, bases, ns):\n"
        "        return type.__new__(mcs, name, bases, ns)\n"
        "class M(Base, Base):\n    pass\n"
        "class K(metaclass=M):\n" + _MEMBER
    )

    assert _why(tmp_path, {"k.py": text}) is None


@pytest.mark.parametrize(
    ("files", "clause", "why"),
    [
        # Star imports: project, external, both, ambiguous, unreadable.
        ({"p.py": "class B:\n    pass\n"}, "from p import *", None),
        ({}, "from os.path import *", None),
        (
            {"p.py": "class B:\n    pass\n", "q.py": "class B:\n    pass\n"},
            "from p import *\nfrom q import *",
            "more than once",
        ),
        ({"p.py": "class B(:\n"}, "from p import *", "could not be read or parsed"),
        (
            {"p/__init__.py": "", "p/x.py": ""},
            "from .gone import *",
            "does not resolve",
        ),
        ({"p.py": "X = 1\n"}, "from p import *", "not bound in any scope"),
    ],
)
def test_star_imports(tmp_path, files, clause: str, why: str | None) -> None:
    text = f"{clause}\nclass K(B):\n{_MEMBER}"

    found = _why(tmp_path, {**files, "k.py": text})

    assert (found is None) if why is None else (found is not None and why in found)


def test_ambiguous_absolute_module(tmp_path) -> None:
    files = {
        "util.py": "class B:\n    pass\n",
        "sub/util.py": "class B:\n    pass\n",
        "sub/k.py": "from util import B\nclass K(B):\n" + _MEMBER,
    }

    found = _why(tmp_path, files, rel="sub/k.py")

    assert found is not None and "more than one project file" in found


def test_relative_import_above_the_root(tmp_path) -> None:
    files = {"k.py": "from ... import B\nclass K(B):\n" + _MEMBER}

    assert "does not resolve" in _why(tmp_path, files)


def test_reexport_cycle_and_depth(tmp_path, monkeypatch) -> None:
    files = {
        "a.py": "from b import B\n",
        "b.py": "from a import B\n",
        "k.py": "from a import B\nclass K(B):\n" + _MEMBER,
    }
    assert "cycle" in _why(tmp_path, files)

    files = {
        "a.py": "from b import B\n",
        "b.py": "class B:\n    pass\n",
        "k.py": "from a import B\nclass K(B):\n" + _MEMBER,
    }
    monkeypatch.setattr(walk, "_HOPS_MAX", 0)
    assert "too deep" in _why(tmp_path, files)


def test_stdlib_shadow_and_missing_names(tmp_path) -> None:
    files = {
        "tests/types.py": "X = 1\n",
        "tests/k.py": "from types import SimpleNamespace\nclass K(SimpleNamespace):\n"
        + _MEMBER,
    }
    assert _why(tmp_path, files, rel="tests/k.py") is None

    files = {
        "pkg/__init__.py": "",
        "k.py": "import pkg\nclass K(pkg.Nope):\n" + _MEMBER,
    }
    assert "its package does not bind" in _why(tmp_path, files)


def test_unreadable_imported_module(tmp_path, monkeypatch) -> None:
    files = {
        "p.py": "class B:\n    pass\n",
        "k.py": "import p\nclass K(p.B):\n" + _MEMBER,
    }
    root = _write(tmp_path, files)
    real = walk.FILE_CACHE.read_stamped

    def read(path: str):
        return None if path.endswith("p.py") else real(path)

    monkeypatch.setattr(walk.FILE_CACHE, "read_stamped", read)

    _name, found = walk.python_dynamic_base(root, "k.py", 4, "m", lambda: None)

    assert found is not None and "could not be read or parsed" in found.why


def test_unreadable_declaring_file_is_unchecked(tmp_path) -> None:
    root = _write(tmp_path, {})

    name, found = walk.python_dynamic_base(root, "gone.py", 1, "m", lambda: None)

    assert name is None and found is not None and found.unchecked


def test_project_tops_classify_unresolved_modules(tmp_path) -> None:
    files = {"k.py": "from lib.x import B\nclass K(B):\n" + _MEMBER}

    assert "does not resolve" in _why(tmp_path, files, tops=frozenset({"lib"}))
    assert _why(tmp_path, files, tops=frozenset({"other"})) is None


def test_parse_memo_is_reused_and_bounded(tmp_path, monkeypatch) -> None:
    files = {
        "p.py": "class B:\n    pass\n",
        "k.py": "from p import B\nclass K(B):\n" + _MEMBER,
    }
    root = _write(tmp_path, files)
    monkeypatch.setattr(walk, "_PARSED_MAX", 1)
    for _ in range(2):
        assert walk.python_dynamic_base(root, "k.py", 4, "m", lambda: None)[1] is None
    assert len(walk._PARSED) <= 1


class _Conn:
    def __init__(self, rows) -> None:
        self._rows = rows

    def execute(self, *_args):
        if self._rows is None:
            raise OSError("unreadable")
        return self

    def fetchall(self):
        return self._rows


class _Cache:
    def __init__(self, rows) -> None:
        self._conn = _Conn(rows)

    def get_conn(self):
        return self._conn


def test_python_project_tops_reads_the_index() -> None:
    rows = [
        ("src/app/models.py",),
        ("tests\\test_x.py",),
        ("pkg/__init__.py",),
        ("pkg/mypy.py",),
        ("pkg/sub/__init__.py",),
        ("tests/mypy/__init__.py",),
    ]
    tops = python_project_tops(_Cache(rows))

    # ``pkg/mypy.py`` and ``pkg/sub`` live in a package: they shadow nothing.
    assert tops == frozenset({"models", "test_x", "pkg", "mypy"})
    assert python_project_tops(_Cache(None)) is None
    assert python_project_tops(None) is None


def test_owner_rows_of_other_classes_are_skipped(tmp_path) -> None:
    text = (
        "def mix(b):\n    return b\n"
        "class Dyn(mix(object)):\n" + _MEMBER + "class Plain:\n" + _MEMBER
    )
    root = _write(tmp_path, {"k.py": text})
    rows = [("k.py", 4, "python"), ("k.py", 7, "python")]

    assert dynamic_supertype(root, rows, "m", owner="Plain") is None
    assert dynamic_supertype(root, rows, "m", owner="Dyn") is not None
    # A qualifier that names no class in the rows (a module path) keeps every row.
    assert dynamic_supertype(root, rows, "m", owner="k") is not None
