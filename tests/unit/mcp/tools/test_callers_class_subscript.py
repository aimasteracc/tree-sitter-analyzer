"""PR-1: a subscripted project class that is called (``Cls[T](...)``) only constructs.

``_Pipeline[Any, Any](...)`` (pydantic) was counted by the declaring-file guard as
a computed dispatch that could name any method, so every ``_Pipeline`` method
stayed ``unknown`` / ``incomplete``. Calling ``Generic.__class_getitem__``'s alias
runs only construction (``__new__``, ``__init__``, ``__post_init__``) and sets
``__orig_class__`` (``__setattr__``).

The exclusion is allowed only when the subscripted name is provably the class:
one module-level ``class`` binding in the file, no metaclass, no
``__class_getitem__``, no unknown base or decorator, and no dynamic rebinding.
Every other shape keeps the guard (``HANDLERS[k]()`` above all).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.callers_class_subscript import (
    CLASS_CONSTRUCTION_REASON,
    CONSTRUCTION_METHODS,
    constructs_only,
    drop_class_constructions,
    subscripted_name,
)
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_HEAD = (
    "from dataclasses import dataclass\n"
    "from typing import Any, Generic, TypeVar\n\n"
    'T = TypeVar("T")\n\n\n'
)
#: The pydantic ``_Pipeline`` shape: a generic dataclass rebuilt by ``Pipe[T](...)``.
_PIPE = _HEAD + (
    "@dataclass(slots=True)\n"
    "class Pipe(Generic[T]):\n"
    "    steps: tuple\n\n"
    "    def then(self, f):\n"
    "        return Pipe[T](self.steps + (f,))\n\n"
    "    def shout(self):\n"
    "        return 1\n"
)


def _cache(paths: list[str]) -> Any:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, language TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)", [(p, "python") for p in paths]
    )
    return SimpleNamespace(get_conn=lambda: conn)


def _broken() -> Any:
    def fail() -> Any:
        raise sqlite3.OperationalError("no such table")

    return SimpleNamespace(get_conn=fail)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _site(callee: str, file: str = "mod.py", line: int = 12) -> dict[str, Any]:
    return {
        "file": file,
        "line": line,
        "callee": callee,
        "classification": "unresolved",
    }


# --------------------------------------------------------------- pure shapes
@pytest.mark.parametrize(
    ("callee", "expected"),
    [
        ("Pipe[T]", "Pipe"),
        ("Pipe[T, Any]", "Pipe"),
        ("Pipe[dict[int, int]]", "Pipe"),
        ("HANDLERS[k]", "HANDLERS"),
        ("mod.Pipe[T]", None),
        ("self.table[k]", None),
        ("make()[k]", None),
        ("Pipe[T][U]", None),
        ("Pipe", None),
        ("getattr(m, n)", None),
        ("", None),
        ("Pipe[", None),
    ],
)
def test_subscripted_name_only_accepts_a_bare_name_subscript(
    callee: str, expected: str | None
) -> None:
    assert subscripted_name(callee) == expected


def test_generic_dataclass_constructs_only() -> None:
    assert constructs_only(_PIPE, "Pipe") is True


@pytest.mark.parametrize(
    "text",
    [
        # A dict / list / variable: container dispatch, never a construction.
        _HEAD + "HANDLERS = {'a': print}\n",
        _HEAD + "def f(Pipe):\n    return Pipe\n",
        # A metaclass may define `__getitem__`: the subscript is anything.
        _HEAD
        + "class Meta(type):\n    def __getitem__(cls, k):\n        return print\n\n\n"
        + "class Pipe(metaclass=Meta):\n    pass\n",
        # `__class_getitem__` may return a non-class.
        _HEAD
        + "class Pipe:\n    def __class_getitem__(cls, k):\n        return print\n",
        _HEAD
        + "class Pipe:\n    __class_getitem__ = classmethod(lambda c, k: print)\n",
        # Inherited `__class_getitem__` from an in-file base.
        _HEAD
        + "class Base:\n    def __class_getitem__(cls, k):\n        return print\n\n\n"
        + "class Pipe(Base):\n    pass\n",
        # Base whose metaclass cannot be determined (imported / unknown).
        "from elsewhere import Base\n\n\nclass Pipe(Base):\n    pass\n",
        _HEAD + "class Pipe(Unknown[T]):\n    pass\n",
        # `Generic` not bound to typing's.
        "from mylib import Generic\n\n\nclass Pipe(Generic[int]):\n    pass\n",
        # An unknown decorator may replace the class.
        _HEAD + "@register\nclass Pipe(Generic[T]):\n    pass\n",
        # Rebound or conditionally defined.
        _PIPE + "\nPipe = dict\n",
        _HEAD + "if X:\n    class Pipe(Generic[T]):\n        pass\n",
        _HEAD
        + "class Pipe(Generic[T]):\n    pass\n\n\nclass Pipe(Generic[T]):\n    pass\n",
        _PIPE + "\ndef g():\n    global Pipe\n",
        _PIPE + "\nfor Pipe in []:\n    pass\n",
        _PIPE + "\nimport os as Pipe\n",
        # Dynamic rebinding by string name in the same file.
        _PIPE + "\nglobals()['Pipe'] = dict\n",
        _PIPE + "\nsetattr(sys.modules[__name__], 'Pipe', dict)\n",
        _PIPE + "\nexec('Pipe = dict')\n",
        # The class is imported, not defined here.
        "from pkg.pipe import Pipe\n",
        # A keyword on the class statement.
        _HEAD + "class Pipe(Generic[T], flag=True):\n    pass\n",
        # Not parseable.
        "class Pipe(:\n",
    ],
)
def test_shapes_that_are_not_provably_a_plain_class_keep_the_guard(text: str) -> None:
    assert constructs_only(text, "Pipe") is False


def test_in_file_plain_base_and_typing_module_attribute_are_accepted() -> None:
    text = (
        "import dataclasses\n"
        "import typing\n\n"
        'T = typing.TypeVar("T")\n\n\n'
        "class Base:\n    pass\n\n\n"
        "@dataclasses.dataclass\n"
        "class Pipe(Base, typing.Generic[T], object):\n    pass\n"
    )
    assert constructs_only(text, "Pipe") is True


def test_construction_methods_cover_the_generic_alias_call() -> None:
    assert {
        "__init__",
        "__new__",
        "__post_init__",
        "__call__",
        "__class_getitem__",
        "__setattr__",
        "__init_subclass__",
    } <= CONSTRUCTION_METHODS


# ----------------------------------------------------------- drop (unit level)
def test_class_subscript_site_is_excluded_for_an_ordinary_method(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "mod.py", _PIPE)
    kept, excluded = drop_class_constructions(
        _cache(["mod.py"]), str(tmp_path), [_site("Pipe[T]")], [], "shout"
    )
    assert kept == []
    assert [s["reason_code"] for s in excluded] == [CLASS_CONSTRUCTION_REASON]
    assert excluded[0]["classification"] == "excluded"


@pytest.mark.parametrize(
    "target", ["__init__", "__post_init__", "__new__", "__setattr__", "Pipe", "Generic"]
)
def test_construction_and_class_targets_keep_the_site(
    tmp_path: Path, target: str
) -> None:
    _write(tmp_path, "mod.py", _PIPE)
    site = _site("Pipe[T]")
    kept, excluded = drop_class_constructions(
        _cache(["mod.py"]), str(tmp_path), [site], [], target
    )
    assert (kept, excluded) == ([site], [])


def test_base_class_name_target_keeps_the_site(tmp_path: Path) -> None:
    text = (
        _HEAD + "class Base:\n    pass\n\n\nclass Pipe(Base, Generic[T]):\n    pass\n"
    )
    _write(tmp_path, "mod.py", text)
    site = _site("Pipe[T]")
    kept, _ = drop_class_constructions(
        _cache(["mod.py"]), str(tmp_path), [site], [], "Base"
    )
    assert kept == [site]


def test_container_subscript_dispatch_keeps_the_site(tmp_path: Path) -> None:
    _write(tmp_path, "mod.py", _PIPE + "\nHANDLERS = {'a': Pipe.shout}\n")
    site = _site("HANDLERS[k]")
    kept, excluded = drop_class_constructions(
        _cache(["mod.py"]), str(tmp_path), [site], [], "shout"
    )
    assert (kept, excluded) == ([site], [])


@pytest.mark.parametrize(
    "other",
    ["import mod\nmod.Pipe = dict\n", "import mod\nsetattr(mod, 'Pipe', dict)\n"],
)
def test_rebinding_from_another_module_keeps_the_site(
    tmp_path: Path, other: str
) -> None:
    _write(tmp_path, "mod.py", _PIPE)
    _write(tmp_path, "other.py", other)
    site = _site("Pipe[T]")
    kept, _ = drop_class_constructions(
        _cache(["mod.py", "other.py"]), str(tmp_path), [site], [], "shout"
    )
    assert kept == [site]


def test_unreadable_index_or_source_keeps_the_site(tmp_path: Path) -> None:
    _write(tmp_path, "mod.py", _PIPE)
    site = _site("Pipe[T]")
    assert drop_class_constructions(_broken(), str(tmp_path), [site], [], "shout")[
        0
    ] == [site]
    missing = _site("Pipe[T]", file="gone.py")
    assert drop_class_constructions(
        _cache(["gone.py"]), str(tmp_path), [missing], [], "shout"
    )[0] == [missing]


def test_non_python_and_stub_sites_keep_the_guard(tmp_path: Path) -> None:
    _write(tmp_path, "mod.pyi", _PIPE)
    _write(tmp_path, "mod.ts", "class Pipe {}\n")
    sites = [_site("Pipe[T]", file="mod.pyi"), _site("Pipe[T]", file="mod.ts")]
    kept, _ = drop_class_constructions(
        _cache(["mod.pyi", "mod.ts"]), str(tmp_path), sites, [], "shout"
    )
    assert kept == sites


def test_none_inputs_pass_through() -> None:
    assert drop_class_constructions(None, "/x", [], [], "f") == ([], [])
    assert drop_class_constructions(_broken(), "/x", None, [], "f") == (None, [])
    assert drop_class_constructions(_broken(), "/x", [], None, "f") == ([], None)


# --------------------------------------------------------------- end to end
async def _index(root: Path, files: dict[str, str]) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel, text in files.items():
        _write(root, rel, text)
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 20}
    )
    assert indexed["published"] is True
    return str(root)


async def _callers(root: str, name: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "include_bodies": False}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["Pipe.shout", "shout"])
async def test_generic_class_construction_no_longer_blocks_a_method(
    tmp_path: Path, name: str
) -> None:
    root = await _index(tmp_path, {"mod.py": _PIPE})

    result = await _callers(root, name)

    assert (result["caller_count"], result["completeness"]) == (0, "complete")
    assert result["unresolved_sites"] == []
    assert result["excluded_by_reason"].get(CLASS_CONSTRUCTION_REASON) == 1


@pytest.mark.asyncio
async def test_handlers_subscript_dispatch_still_blocks(tmp_path: Path) -> None:
    text = _PIPE + "\n\nHANDLERS = {}\n\n\n" + "def run(k):\n    return HANDLERS[k]()\n"
    root = await _index(tmp_path, {"mod.py": text})

    result = await _callers(root, "Pipe.shout")

    assert result["completeness"] != "complete"
    assert "UNRESOLVED_IN_DECLARING_FILE" in result["completeness_reasons"]
    assert [s["callee"] for s in result["unresolved_sites"]] == ["HANDLERS[k]"]


@pytest.mark.asyncio
async def test_metaclass_getitem_class_still_blocks(tmp_path: Path) -> None:
    text = _HEAD + (
        "class Meta(type):\n"
        "    def __getitem__(cls, key):\n"
        "        return getattr(cls, key)\n\n\n"
        "class Pipe(metaclass=Meta):\n"
        "    def then(self):\n"
        '        return Pipe["shout"](self)\n\n'
        "    def shout(self):\n"
        "        return 1\n"
    )
    root = await _index(tmp_path, {"mod.py": text})

    result = await _callers(root, "Pipe.shout")

    assert result["completeness"] != "complete"
    assert "UNRESOLVED_IN_DECLARING_FILE" in result["completeness_reasons"]


@pytest.mark.asyncio
async def test_construction_method_target_still_blocks(tmp_path: Path) -> None:
    text = _PIPE + "\n    def __post_init__(self):\n        return None\n"
    root = await _index(tmp_path, {"mod.py": text})

    result = await _callers(root, "Pipe.__post_init__")

    assert result["completeness"] != "complete"
