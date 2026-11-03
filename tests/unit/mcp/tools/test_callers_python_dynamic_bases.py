"""#1883: a Python method under a base the index cannot follow is never ``complete``.

``class V1(mix(Proc))`` gets no inheritance edge, so ``self.get_query()`` in
``Proc.run`` never offers ``V1.get_query`` as a target: before the fix the
override answered ``complete`` with 0 callers. The same holds for a starred base,
a module-level alias (``Alias = Proc``), a subscripted project class
(``GProc[int]``) and any class above one of those.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools import callers_py_supertypes
from tree_sitter_analyzer.mcp.tools.callers_outcomes import Checked, NotChecked
from tree_sitter_analyzer.mcp.tools.callers_supertypes import (
    DYNAMIC_SUPERTYPE_REASON,
    dynamic_supertype,
    dynamic_supertype_hint,
    supertype_outcome,
)
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_PROC = (
    "from typing import Generic, TypeVar\n"
    "T = TypeVar('T')\n"
    "\n"
    "class Proc:\n"
    "    def run(self):\n"
    "        return self.get_query()\n"
    "\n"
    "    def get_query(self):\n"
    "        return ''\n"
    "\n"
    "class GProc(Generic[T]):\n"
    "    def run(self):\n"
    "        return self.g_query()\n"
    "\n"
    "    def g_query(self):\n"
    "        return ''\n"
)
#: The issue's repro (V1, V3, V5) and the plain-base control (V2).
_ISSUE = (
    "from a import Proc, GProc\n"
    "\n"
    "def mix(B):\n"
    "    return B\n"
    "\n"
    "bases = (Proc,)\n"
    "Alias = Proc\n"
    "\n"
    "class V1(mix(Proc)):          # call\n"
    "    def get_query(self):\n"
    "        return 'v1'\n"
    "\n"
    "class V2(Proc):               # control: plain base\n"
    "    def get_query(self):\n"
    "        return 'v2'\n"
    "\n"
    "    def v2_only(self):\n"
    "        return 2\n"
    "\n"
    "class V3(*bases):             # starred\n"
    "    def get_query(self):\n"
    "        return 'v3'\n"
    "\n"
    "class V5(mix(Proc)):\n"
    "    def other(self):\n"
    "        return 5\n"
    "\n"
    "class V8(Alias):\n"
    "    def get_query(self):\n"
    "        return 'v8'\n"
    "\n"
    "class V9(GProc[int]):\n"
    "    def g_query(self):\n"
    "        return 'v9'\n"
    "\n"
    "class Mid(mix(Proc)):\n"
    "    pass\n"
    "\n"
    "class Leaf(Mid):\n"
    "    def leaf_only(self):\n"
    "        return 1\n"
)
#: Bases that end the walk or are followed: the answers must not change.
_PLAIN = (
    "import abc\n"
    "import collections\n"
    "from typing import Generic, Protocol, TypeVar\n"
    "import typing\n"
    "from a import Proc\n"
    "T = TypeVar('T')\n"
    "\n"
    "class Root:\n"
    "    def root_only(self):\n"
    "        return 1\n"
    "\n"
    "class Obj(object):\n"
    "    def obj_only(self):\n"
    "        return 1\n"
    "\n"
    "class Gen(Generic[T]):\n"
    "    def gen_only(self):\n"
    "        return 1\n"
    "\n"
    "class TGen(typing.Generic[T], Root):\n"
    "    def tgen_only(self):\n"
    "        return 1\n"
    "\n"
    "class Proto(Protocol):\n"
    "    def proto_only(self):\n"
    "        return 1\n"
    "\n"
    "class Std(collections.OrderedDict, abc.ABC):\n"
    "    def std_only(self):\n"
    "        return 1\n"
    "\n"
    "class Oops(Exception):\n"
    "    def oops_only(self):\n"
    "        return 1\n"
    "\n"
    "class Meta(Proc, metaclass=abc.ABCMeta):\n"
    "    def meta_only(self):\n"
    "        return 1\n"
    "\n"
    "class Child(Proc):\n"
    "    def child_only(self):\n"
    "        return 1\n"
)


#: Some resolved call, so the project's evidence base is not empty.
_CALLS = "def main():\n    return helper()\n\n\ndef helper():\n    return 1\n"


async def _index(root, files: dict[str, str]) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    _write(root, files)
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 20}
    )
    assert indexed["published"] is True
    return str(root)


async def _callers(root: str, name: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "include_bodies": False}
    )


def _write(root, files: dict[str, str]) -> str:
    callers_py_supertypes.clear_parsed()
    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return str(root)


def _line_of(text: str, needle: str) -> int:
    return next(i for i, line in enumerate(text.split("\n"), 1) if needle in line)


def _finding(tmp_path, files: dict[str, str], rel: str, needle: str, bare: str):
    root = _write(tmp_path, files)
    line = _line_of(files[rel], needle)
    return dynamic_supertype(root, [(rel, line, "python")], bare)


# --- end to end ---------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "clause"),
    [
        ("V1.get_query", "`mix(Proc)`"),
        ("V3.get_query", "`*bases`"),
        ("V5.other", "`mix(Proc)`"),
        ("V8.get_query", "`Alias`"),
        ("V9.g_query", "`GProc[int]`"),
    ],
)
async def test_issue_repros_are_not_complete(tmp_path, name: str, clause: str) -> None:
    root = await _index(tmp_path, {"a.py": _PROC, "b.py": _ISSUE})

    result = await _callers(root, name)

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reasons"] == [DYNAMIC_SUPERTYPE_REASON]
    assert clause in result["next_step"]


@pytest.mark.asyncio
async def test_dynamic_grandparent_blocks_the_leaf(tmp_path) -> None:
    root = await _index(tmp_path, {"a.py": _PROC, "b.py": _ISSUE})

    result = await _callers(root, "Leaf.leaf_only")

    assert result["completeness"] == "unknown"
    assert result["completeness_reasons"] == [DYNAMIC_SUPERTYPE_REASON]
    assert "class `Mid` (b.py:36) has base `mix(Proc)`" in result["next_step"]


@pytest.mark.asyncio
async def test_plain_base_control_keeps_its_answer(tmp_path) -> None:
    root = await _index(tmp_path, {"a.py": _PROC, "b.py": _ISSUE})

    override = await _callers(root, "V2.get_query")
    unique = await _callers(root, "V2.v2_only")

    assert override["completeness_reasons"] == ["NAME_ONLY_INBOUND"]
    assert (unique["completeness"], unique["completeness_reasons"]) == ("complete", [])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    [
        "Root.root_only",
        "Obj.obj_only",
        "Gen.gen_only",
        "TGen.tgen_only",
        "Proto.proto_only",
        "Std.std_only",
        "Oops.oops_only",
        "Meta.meta_only",
        "Child.child_only",
    ],
)
async def test_plain_and_known_external_bases_keep_complete(tmp_path, name) -> None:
    root = await _index(tmp_path, {"a.py": _PROC, "c.py": _PLAIN})

    result = await _callers(root, name)

    assert (result["completeness"], result["completeness_reasons"]) == ("complete", [])
    assert result["completeness_checks"] == {"required": 13, "checked": 13}


@pytest.mark.asyncio
async def test_third_party_base_keeps_complete(tmp_path) -> None:
    files = {
        "app/__init__.py": "",
        "app/main.py": _CALLS,
        "app/models.py": (
            "from pydantic import BaseModel\n"
            "import sqlalchemy.orm\n"
            "\n"
            "class Item(BaseModel):\n"
            "    def item_only(self):\n"
            "        return 1\n"
            "\n"
            "class Row(sqlalchemy.orm.DeclarativeBase):\n"
            "    def row_only(self):\n"
            "        return 1\n"
        ),
    }
    root = await _index(tmp_path, files)

    for name in ("Item.item_only", "Row.row_only"):
        result = await _callers(root, name)
        assert (result["completeness"], result["completeness_reasons"]) == (
            "complete",
            [],
        ), name


@pytest.mark.asyncio
async def test_unresolvable_project_import_blocks(tmp_path) -> None:
    # ``app`` is a project package, but ``app.gone`` is not a project file.
    files = {
        "app/__init__.py": "",
        "app/main.py": _CALLS,
        "app/base.py": "class Base:\n    pass\n",
        "app/user.py": (
            "from app.gone import Base\n"
            "\n"
            "class U(Base):\n"
            "    def u_only(self):\n"
            "        return 1\n"
        ),
    }
    root = await _index(tmp_path, files)

    result = await _callers(root, "U.u_only")

    assert result["completeness_reasons"] == [DYNAMIC_SUPERTYPE_REASON]
    assert "does not resolve to one project file" in result["next_step"]


# --- the walk -------------------------------------------------------------

_CLAUSES = (
    "import abc\n"
    "import pkg\n"
    "from pkg.base import Base, Other\n"
    "from pkg import base as base_mod\n"
    "from pkg.gone import Gone\n"
    "from pkg.meta import Inject, Passes\n"
    "\n"
    "def mix(b):\n"
    "    return b\n"
    "\n"
    "flag = True\n"
    "Value = mix(Base)\n"
    "if flag:\n"
    "    class Twice:\n"
    "        pass\n"
    "else:\n"
    "    class Twice:\n"
    "        pass\n"
    "Reassigned = Base\n"
    "Reassigned = Other\n"
    "kw = {}\n"
    "\n"
    "class K({clause}):\n"
    "    def m(self):\n"
    "        return 1\n"
)
_PKG = {
    "pkg/__init__.py": "from .base import Base\n",
    "pkg/base.py": (
        "class Base:\n"
        "    def run(self):\n"
        "        return self.m()\n"
        "\n"
        "class Other:\n"
        "    pass\n"
        "\n"
        "class Outer:\n"
        "    class Inner:\n"
        "        pass\n"
    ),
    "pkg/meta.py": (
        "class Inject(type):\n"
        "    def __new__(mcs, name, bases, ns):\n"
        "        bases = bases + (object,)\n"
        "        return super().__new__(mcs, name, bases, ns)\n"
        "\n"
        "class Passes(type):\n"
        "    def __new__(mcs, name, bases, ns, **kwargs):\n"
        "        return super().__new__(mcs, name, bases, ns, **kwargs)\n"
    ),
}


@pytest.mark.parametrize(
    ("clause", "why"),
    [
        ("mix(Base)", "a call"),
        ("*[Base]", "a starred"),
        ("Base if flag else Other", "a conditional"),
        ("Value", "a value"),
        ("Reassigned", "bound more than once"),
        ("Twice", "bound more than once"),
        ("Missing", "not bound"),
        ("Gone", "does not resolve to one project file"),
        ("type('X', (Base,), {})", "a call"),
        ("Base[int]", "subscripted project class"),
        ("pkg.base.Nope", "does not bind"),
        ("Base, metaclass=mix(abc.ABCMeta)", "a call"),
        ("Base, metaclass=Inject", "rebinds its bases"),
        ("Base, **kw", "keyword"),
        ("base_mod.Outer.Missing", "not a class"),
    ],
)
def test_unfollowable_bases_are_named(tmp_path, clause: str, why: str) -> None:
    files = {**_PKG, "c.py": _CLAUSES.replace("{clause}", clause)}

    found = _finding(tmp_path, files, "c.py", "    def m(self):", "m")

    assert found is not None and not found.unchecked, found
    assert (found.file, found.class_name) == ("c.py", "K")
    assert why in found.why, found.why
    assert "has base" in dynamic_supertype_hint("K.m", found) or "metaclass" in (
        found.describe()
    )


@pytest.mark.parametrize(
    "clause",
    [
        "Base",
        "Other, Base",
        "pkg.Base",
        "pkg.base.Base",
        "base_mod.Base",
        "base_mod.Outer.Inner",
        "abc.ABC",
        "object",
        "Exception",
        "Base, metaclass=abc.ABCMeta",
        "Base, metaclass=Passes",
        "Base, total=False",
    ],
)
def test_followable_bases_pass(tmp_path, clause: str) -> None:
    files = {**_PKG, "c.py": _CLAUSES.replace("{clause}", clause)}

    assert _finding(tmp_path, files, "c.py", "    def m(self):", "m") is None


def test_relative_imports_and_reexports_are_followed(tmp_path) -> None:
    files = {
        **_PKG,
        "pkg/sub/__init__.py": "from ..base import Base as Renamed\n",
        "pkg/sub/user.py": (
            "from . import Renamed\n"
            "from ..base import Other\n"
            "from .. import base\n"
            "\n"
            "class U(Renamed, Other, base.Base):\n"
            "    def m(self):\n"
            "        return 1\n"
        ),
    }

    found = _finding(tmp_path, files, "pkg/sub/user.py", "    def m(self):", "m")

    assert found is None


def test_dynamic_base_two_imports_up_is_found(tmp_path) -> None:
    files = {
        "pkg/__init__.py": "",
        "pkg/root.py": "def mix(b):\n    return b\n\nclass Top(mix(object)):\n    pass\n",
        "pkg/mid.py": "from .root import Top\n\nclass Mid(Top):\n    pass\n",
        "pkg/leaf.py": (
            "from pkg.mid import Mid\n\nclass Leaf(Mid):\n    def m(self):\n        return 1\n"
        ),
    }

    found = _finding(tmp_path, files, "pkg/leaf.py", "    def m(self):", "m")

    assert found is not None
    assert (found.file, found.class_name, found.clause) == (
        "pkg/root.py",
        "Top",
        "mix(object)",
    )


def test_nested_class_resolves_bases_in_its_enclosing_scopes(tmp_path) -> None:
    files = {
        **_PKG,
        "n.py": (
            "from pkg.base import Base\n"
            "\n"
            "def make(flag):\n"
            "    class Local(Base):\n"
            "        pass\n"
            "    Dyn = Local if flag else Base\n"
            "    class A(Local):\n"
            "        def m(self):\n"
            "            return 1\n"
            "    class B(Dyn):\n"
            "        def m2(self):\n"
            "            return 1\n"
            "    return A, B\n"
        ),
    }
    _write(tmp_path, files)
    text = files["n.py"]

    passes = dynamic_supertype(
        str(tmp_path), [("n.py", _line_of(text, "def m(self)"), "python")], "m"
    )
    blocked = dynamic_supertype(
        str(tmp_path), [("n.py", _line_of(text, "def m2(self)"), "python")], "m2"
    )

    assert passes is None
    assert blocked is not None and "a local value" in blocked.why


@pytest.mark.parametrize("bare", ["__init__", "__new__", "__private", "__repr__"])
def test_no_python_member_is_exempt(tmp_path, bare: str) -> None:
    text = (
        "def mix(b):\n"
        "    return b\n"
        "\n"
        "class K(mix(object)):\n"
        f"    def {bare}(self):\n"
        "        return 1\n"
    )

    found = _finding(tmp_path, {"k.py": text}, "k.py", f"def {bare}(", bare)

    assert found is not None and found.clause == "mix(object)"


def test_class_body_attribute_is_gated(tmp_path) -> None:
    text = (
        "def mix(b):\n"
        "    return b\n"
        "\n"
        "class K(mix(object)):\n"
        "    handler = staticmethod(print)\n"
    )

    found = _finding(tmp_path, {"k.py": text}, "k.py", "handler =", "handler")

    assert found is not None


@pytest.mark.parametrize(
    "text",
    [
        "def m():\n    return 1\n",
        "def outer():\n    def m():\n        return 1\n    return m\n",
    ],
)
def test_functions_outside_a_class_body_pass(tmp_path, text: str) -> None:
    assert _finding(tmp_path, {"f.py": text}, "f.py", "def m(", "m") is None


def test_unparsable_declaring_file_is_unchecked(tmp_path) -> None:
    root = _write(tmp_path, {"bad.py": "class K(:\n    def m(self):\n"})

    found = dynamic_supertype(root, [("bad.py", 2, "python")], "m")

    assert found is not None and found.unchecked


def test_unparsable_base_file_is_named(tmp_path) -> None:
    files = {
        "broken.py": "class Base(:\n",
        "k.py": "from broken import Base\n\nclass K(Base):\n    def m(self):\n        return 1\n",
    }

    found = _finding(tmp_path, files, "k.py", "def m(", "m")

    assert found is not None and "could not be read or parsed" in found.why


def test_third_party_without_an_index_cannot_be_classified(tmp_path) -> None:
    # Without the index's file list a non-stdlib module may be a project one.
    files = {
        "k.py": "from pydantic import BaseModel\n\nclass K(BaseModel):\n    def m(self):\n        return 1\n"
    }

    found = _finding(tmp_path, files, "k.py", "def m(", "m")

    assert found is not None and "cannot be classified" in found.why


def test_outcome_is_checked_with_the_reason(tmp_path) -> None:
    root = _write(tmp_path, {"a.py": _PROC, "b.py": _ISSUE})
    line = _line_of(_ISSUE, "return 'v1'") - 1

    outcome, finding = supertype_outcome(
        ("K.m", None), root, [("b.py", line, "python")], "get_query"
    )

    assert isinstance(outcome, Checked)
    assert outcome.problems == (DYNAMIC_SUPERTYPE_REASON,)
    assert finding is not None and finding.clause == "mix(Proc)"


def test_walk_failure_is_not_checked(tmp_path, monkeypatch) -> None:
    root = _write(tmp_path, {"a.py": _PROC, "b.py": _ISSUE})

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(callers_py_supertypes, "python_dynamic_base", boom)

    outcome, finding = supertype_outcome(
        ("K.m", None), root, [("b.py", 10, "python")], "get_query"
    )

    assert isinstance(outcome, NotChecked)
    assert finding is not None and finding.unchecked
