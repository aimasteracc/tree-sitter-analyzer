"""#1949: a Python method a base outside the project may call is never ``complete``.

``class _Reader(io.RawIOBase)``: the standard library calls ``writable()``, so
``_Reader.writable`` with no project caller is not dead. Before the fix the
supertype walk stopped at the external base and the answer was ``complete``.
Special methods (``__eq__``, ``__init__``) are called by the interpreter and
answered ``complete`` on any class.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools import callers_py_supertypes
from tree_sitter_analyzer.mcp.tools.callers_java_overrides import OVERRIDE_REASON
from tree_sitter_analyzer.mcp.tools.callers_py_overrides import (
    known_members,
    python_override_finding,
)
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_CALLS = "def main():\n    return helper()\n\n\ndef helper():\n    return 1\n"
_BASES = (
    "import io\n"
    "import logging\n"
    "\n"
    "class Plain:\n"
    "    def plain_only(self):\n"
    "        return 1\n"
    "\n"
    "class Handler(logging.Handler):\n"
    "    pass\n"
)
_MODELS = (
    "import abc\n"
    "import collections\n"
    "import enum\n"
    "import io\n"
    "from typing import Generic, NamedTuple, Protocol, TypeVar\n"
    "from pydantic import BaseModel\n"
    "from base import Handler, Plain\n"
    "T = TypeVar('T')\n"
    "\n"
    "class _Reader(io.RawIOBase):\n"
    "    def writable(self):\n"
    "        return False\n"
    "\n"
    "    def reader_only(self):\n"
    "        return 1\n"
    "\n"
    "    def __mangled(self):\n"
    "        return 1\n"
    "\n"
    "class Item(BaseModel):\n"
    "    def item_only(self):\n"
    "        return 1\n"
    "\n"
    "class Leaf(Handler):\n"
    "    def emit(self, record):\n"
    "        return None\n"
    "\n"
    "class Std(collections.OrderedDict):\n"
    "    def std_only(self):\n"
    "        return 1\n"
    "\n"
    "class Oops(Exception):\n"
    "    def oops_only(self):\n"
    "        return 1\n"
    "\n"
    "    def with_traceback(self, tb):\n"
    "        return self\n"
    "\n"
    "class Keys(dict):\n"
    "    def keys(self):\n"
    "        return []\n"
    "\n"
    "class Gen(Generic[T], abc.ABC):\n"
    "    def gen_only(self):\n"
    "        return 1\n"
    "\n"
    "class Proto(Protocol):\n"
    "    def proto_only(self):\n"
    "        return 1\n"
    "\n"
    "class Pair(NamedTuple):\n"
    "    a: int\n"
    "\n"
    "    def pair_only(self):\n"
    "        return 1\n"
    "\n"
    "class Color(enum.Enum):\n"
    "    RED = 1\n"
    "\n"
    "    def label(self):\n"
    "        return 'r'\n"
    "\n"
    "    @classmethod\n"
    "    def _missing_(cls, value):\n"
    "        return cls.RED\n"
    "\n"
    "class Meta(Plain, metaclass=abc.ABCMeta):\n"
    "    def meta_only(self):\n"
    "        return 1\n"
    "\n"
    "class Child(Plain):\n"
    "    def child_only(self):\n"
    "        return 1\n"
    "\n"
    "class Point:\n"
    "    def __init__(self, x):\n"
    "        self.x = x\n"
    "\n"
    "    def __eq__(self, other):\n"
    "        return self.x == other.x\n"
    "\n"
    "    def __enter__(self):\n"
    "        return self\n"
    "\n"
    "def make():\n"
    "    return Point(1)\n"
    "\n"
    "def __getattr__(name):\n"
    "    return name\n"
)


async def _index(root, files: dict[str, str]) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    _write(root, files)
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 20}
    )
    assert indexed["published"] is True
    return str(root)


def _write(root, files: dict[str, str]) -> str:
    callers_py_supertypes.clear_parsed()
    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return str(root)


async def _callers(root: str, name: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "include_bodies": False}
    )


_FILES = {"main.py": _CALLS, "base.py": _BASES, "models.py": _MODELS}


# --- end to end ---------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "named"),
    [
        ("_Reader.writable", "class `_Reader` (models.py:10) has base `io.RawIOBase`"),
        ("_Reader.reader_only", "has base `io.RawIOBase`"),
        ("Item.item_only", "has base `BaseModel`"),
        ("Leaf.emit", "class `Handler` (base.py:8) has base `logging.Handler`"),
        ("Std.std_only", "has base `collections.OrderedDict`"),
        ("Oops.with_traceback", "has base `Exception`, a class outside the project "),
        ("Keys.keys", "has base `dict`"),
        ("Color._missing_", "has base `enum.Enum`"),
    ],
)
async def test_external_base_overrides_are_not_complete(
    tmp_path, name: str, named: str
) -> None:
    root = await _index(tmp_path, dict(_FILES))

    result = await _callers(root, name)

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reasons"] == [OVERRIDE_REASON]
    assert named in result["next_step"], result["next_step"]
    assert "outside the project" in result["next_step"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name", ["Point.__eq__", "Point.__enter__", "Point.__init__", "__getattr__"]
)
async def test_special_methods_are_not_complete(tmp_path, name: str) -> None:
    root = await _index(tmp_path, dict(_FILES))

    result = await _callers(root, name)

    assert result["completeness"] in ("unknown", "incomplete"), result
    assert result["completeness"] != "complete"
    assert OVERRIDE_REASON in result["completeness_reasons"], result
    assert "special method" in result["next_step"], result["next_step"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    [
        "Plain.plain_only",
        "Child.child_only",
        "Meta.meta_only",
        "Oops.oops_only",
        "Gen.gen_only",
        "Proto.proto_only",
        "Pair.pair_only",
        "Color.label",
        "_Reader.__mangled",
    ],
)
async def test_closed_and_project_bases_keep_complete(tmp_path, name: str) -> None:
    root = await _index(tmp_path, dict(_FILES))

    result = await _callers(root, name)

    assert (result["completeness"], result["completeness_reasons"]) == (
        "complete",
        [],
    ), result


@pytest.mark.asyncio
async def test_a_project_caller_is_not_the_whole_list(tmp_path) -> None:
    files = {
        **_FILES,
        "use.py": "from models import _Reader\n\n\ndef go(r: _Reader):\n"
        "    return r.writable()\n",
    }
    root = await _index(tmp_path, files)

    result = await _callers(root, "_Reader.writable")

    if result["caller_count"]:
        assert result["completeness"] == "incomplete", result
    else:
        assert result["completeness"] == "unknown", result
    assert OVERRIDE_REASON in result["completeness_reasons"]


# --- the walk -------------------------------------------------------------


def _line_of(text: str, needle: str) -> int:
    return next(i for i, line in enumerate(text.split("\n"), 1) if needle in line)


def _tops() -> frozenset[str]:
    return frozenset({"base", "models", "main"})


@pytest.mark.parametrize(
    ("clause", "blocked"),
    [
        ("ExternalMeta", True),  # metaclass from a package
        ("type", False),
        ("abc.ABCMeta", False),
    ],
)
def test_external_metaclass_blocks(tmp_path, clause: str, blocked: bool) -> None:
    text = (
        "import abc\n"
        "from somelib import ExternalMeta\n"
        "\n"
        f"class K(metaclass={clause}):\n"
        "    def m(self):\n"
        "        return 1\n"
    )
    root = _write(tmp_path, {"k.py": text})

    found = python_override_finding(root, "k.py", _line_of(text, "def m"), "m", _tops)

    assert (found is not None) is blocked, found
    if found is not None:
        assert found.reason == OVERRIDE_REASON
        assert "metaclass" in found.describe()


def test_shadowed_builtin_is_not_the_builtin(tmp_path) -> None:
    text = (
        "from somelib import Exception\n"
        "\n"
        "class K(Exception):\n"
        "    def m(self):\n"
        "        return 1\n"
    )
    root = _write(tmp_path, {"k.py": text})

    found = python_override_finding(root, "k.py", 4, "m", _tops)

    assert found is not None and "may define or call `m`" in found.why


def test_not_a_member_and_unreadable_pass(tmp_path) -> None:
    root = _write(tmp_path, {"k.py": "def free():\n    return 1\n"})

    assert python_override_finding(root, "k.py", 1, "free", _tops) is None
    assert python_override_finding(root, "gone.py", 1, "x", _tops) is None
    assert python_override_finding(root, "notes.txt", 1, "x", _tops) is None


def test_known_members() -> None:
    assert "keys" in (known_members("builtins.dict") or ())
    assert "with_traceback" in (known_members("builtins.Exception") or ())
    assert "_asdict" in (known_members("typing_extensions.NamedTuple") or ())
    assert known_members("io.RawIOBase") is None
    assert known_members("enum.auto") is None
    assert known_members("builtins.len") is None
