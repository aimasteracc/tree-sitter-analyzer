"""#1798：项目里唯一定义的名字，带不带 ``file_path`` 得到同一个 callers 答案。

dogfood（rich）：``Color.get_truecolor`` 带范围列出 2 个调用方、裸名 6 个；``Text.join``
带范围 7 个、裸名 48 个——多出来的是 ``", ".join`` / ``os.path.join`` 这类接收者未被
证明的同名调用。不带范围的问题现在先补上唯一定义的文件，再走同一次 #1759 改写与
同一个 RFC-0040 目标集，四种问法的答案按构造一致。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.callers_target_set import sole_definition_file
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_COLOR = (
    "class Color:\n"
    "    def get_truecolor(self, theme=None):\n"
    "        return theme\n"
    "\n"
    "    def join(self, parts):\n"
    "        return parts\n"
)
_USE = (
    "import os\n"
    "\n"
    "from .color import Color\n"
    "\n"
    "\n"
    "def bound():\n"
    "    return Color().get_truecolor()\n"
    "\n"
    "\n"
    "def untyped(style):\n"
    "    return style.color.get_truecolor()\n"
    "\n"
    "\n"
    "def strings(parts):\n"
    '    return ", ".join(parts)\n'
    "\n"
    "\n"
    "def paths(root):\n"
    '    return os.path.join(root, "x")\n'
    "\n"
    "\n"
    "def size():\n"
    "    return 1\n"
)
_OTHER = "class Box:\n    def size(self):\n        return 2\n"


async def _index(root: Path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel_path, text in {
        "pkg/__init__.py": "",
        "pkg/color.py": _COLOR,
        "pkg/use.py": _USE,
        "pkg/other.py": _OTHER,
    }.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True
    return str(root)


async def _ask(root: str, name: str, file_path: str | None) -> dict[str, Any]:
    arguments: dict[str, Any] = {"function_name": name, "include_bodies": False}
    if file_path is not None:
        arguments["file_path"] = file_path
    return await CodeGraphCallersTool(root).execute(arguments)


def _shape(result: dict[str, Any]) -> tuple[Any, ...]:
    return (
        result["function"],
        result["completeness"],
        tuple(result.get("completeness_reasons") or ()),
        tuple(sorted((c["file"], c["name"]) for c in result.get("callers") or [])),
        tuple(
            sorted((s["file"], s["line"]) for s in result.get("name_only_sites") or [])
        ),
        result.get("completeness_checks"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("member", ["get_truecolor", "join"])
async def test_all_four_forms_of_a_unique_method_agree(tmp_path, member: str) -> None:
    root = await _index(tmp_path)

    answers = [
        await _ask(root, name, file_path)
        for name in (member, f"Color.{member}")
        for file_path in ("pkg/color.py", None)
    ]

    assert len({repr(_shape(a)) for a in answers}) == 1, [_shape(a) for a in answers]


@pytest.mark.asyncio
async def test_unproven_same_name_calls_are_not_listed_unscoped(tmp_path) -> None:
    root = await _index(tmp_path)

    result = await _ask(root, "join", None)

    listed = {c["name"] for c in result.get("callers") or []}
    # `", ".join` and `os.path.join` are str / stdlib calls, not callers of Color.join.
    assert {"strings", "paths"}.isdisjoint(listed)
    assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_a_constructor_bound_caller_stays_listed_unscoped(tmp_path) -> None:
    root = await _index(tmp_path)

    result = await _ask(root, "get_truecolor", None)

    assert ("pkg/use.py", "bound") in {
        (c["file"], c["name"]) for c in result.get("callers") or []
    }
    # The untyped receiver is evidence, not a silent drop.
    assert result["completeness"] != "complete"


_BASE = (
    "from abc import ABC, abstractmethod\n"
    "\n"
    "\n"
    "class Renderer(ABC):\n"
    "    @abstractmethod\n"
    "    def render_page(self):\n"
    "        raise NotImplementedError\n"
)
_IMPL = (
    "from .base import Renderer\n"
    "\n"
    "\n"
    "class HtmlRenderer(Renderer):\n"
    "    def render_page(self):\n"
    "        return '<p/>'\n"
    "\n"
    "\n"
    "def show(renderer: Renderer):\n"
    "    return renderer.render_page()\n"
)


@pytest.mark.asyncio
async def test_an_override_target_stays_unscoped(tmp_path) -> None:
    # java-1743 shape: an abstract declaration plus its override are two
    # definitions. Virtual dispatch through the base makes the unscoped bare
    # name a union question, so it must not be narrowed to the override's file.
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel_path, text in {
        "ui/__init__.py": "",
        "ui/base.py": _BASE,
        "ui/html.py": _IMPL,
    }.items():
        path = tmp_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True
    tool = CodeGraphCallersTool(str(tmp_path))
    graph = tool._graph_for(None)[0]

    assert sole_definition_file(graph, tool._try_get_cache(), "render_page") is None
    bare = await _ask(str(tmp_path), "render_page", None)
    assert bare["function"] == "render_page"


@pytest.mark.asyncio
async def test_a_name_with_several_definitions_keeps_the_unscoped_union(
    tmp_path,
) -> None:
    root = await _index(tmp_path)

    result = await _ask(root, "size", None)

    # `size` is a module function in use.py and a method in other.py: not scoped.
    assert result["function"] == "size"


# -- sole_definition_file -------------------------------------------------------


class _Graph:
    def __init__(self, refs: list[Any], fail: bool = False) -> None:
        self._refs = refs
        self._fail = fail

    def resolve_targets(self, name: str, file_path: str | None = None) -> list[Any]:
        if self._fail:
            raise RuntimeError("unreadable")
        return [ref for ref in self._refs if ref.name == name]


class _Cache:
    def __init__(self, files: tuple[str, ...] | None) -> None:
        self._files = files

    def symbol_declaring_files(self, name: str) -> tuple[str, ...] | None:
        return self._files


def _ref(name: str, file_path: str, receiver: str | None = None) -> Any:
    return SimpleNamespace(name=name, file_path=file_path, receiver=receiver)


_ONE_METHOD = _Graph([_ref("paint", "app/color.py", "Color")])


@pytest.mark.parametrize("name", ["paint", "Color.paint"])
def test_sole_definition_file_scopes_a_unique_definition(name: str) -> None:
    assert (
        sole_definition_file(_ONE_METHOD, _Cache(("app/color.py",)), name)
        == "app/color.py"
    )


def test_sole_definition_file_normalises_separators() -> None:
    graph = _Graph([_ref("paint", "app\\color.py", "Color")])

    assert sole_definition_file(graph, _Cache(("app\\color.py",)), "paint") == (
        "app/color.py"
    )


@pytest.mark.parametrize(
    ("graph", "cache", "name"),
    [
        pytest.param(
            _Graph([_ref("paint", "app/color.py", "Color"), _ref("paint", "app/b.py")]),
            _Cache(("app/color.py", "app/b.py")),
            "paint",
            id="two-definitions",
        ),
        pytest.param(
            _ONE_METHOD, _Cache(("app/color.py",)), "Brush.paint", id="other-owner"
        ),
        pytest.param(
            _ONE_METHOD,
            _Cache(("app/color.py", "app/vars.py")),
            "paint",
            id="same-name-variable",
        ),
        pytest.param(_ONE_METHOD, _Cache(None), "paint", id="unreadable-index"),
        pytest.param(_ONE_METHOD, None, "paint", id="no-index"),
        pytest.param(_Graph([], fail=True), _Cache(()), "paint", id="unreadable-graph"),
        pytest.param(_Graph([]), _Cache(()), "paint", id="not-defined"),
        pytest.param(
            _ONE_METHOD, _Cache(("app/color.py",)), "app/color.py:paint", id="path-like"
        ),
        pytest.param(
            _ONE_METHOD, _Cache(("app/color.py",)), "Color.", id="empty-member"
        ),
        pytest.param(None, _Cache(("app/color.py",)), "paint", id="no-graph"),
        pytest.param(
            _Graph([_ref("paint", "", "Color")]), _Cache(("",)), "paint", id="no-file"
        ),
    ],
)
def test_sole_definition_file_keeps_the_question_unscoped(
    graph: Any, cache: Any, name: str
) -> None:
    assert sole_definition_file(graph, cache, name) is None


def test_an_unreadable_graph_leaves_the_query_unscoped(monkeypatch) -> None:
    class _Broken:
        def get(self) -> Any:
            raise RuntimeError("graph build failed")

    assert (
        CodeGraphCallersTool._sole_definition_file(object(), "paint", _Broken())  # type: ignore[arg-type]
        is None
    )
