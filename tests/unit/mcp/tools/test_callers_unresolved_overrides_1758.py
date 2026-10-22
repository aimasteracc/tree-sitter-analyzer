"""#1758：未解析的 ``x.m()`` 在声明了 ``m`` 的文件里，别的文件的同名方法（覆写）同样可能被调用。

dogfood r11（rich）：``console.py`` 里 ``for hook in self._render_hooks[:]:
hook.process_renderables(...)``，同文件声明了抽象的 ``RenderHook.process_renderables``；
``live.py`` 的 ``Live(RenderHook)`` 覆写它。本地档命中同文件的定义后不再看全局档，
``Live.process_renderables`` 因此答 ``complete, 0``——限定名与裸名都如此。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.mcp.tools.test_callers_bare_name_gates_1740 import _callers, _index

_RICH = {
    "rich/__init__.py": "",
    "rich/console.py": (
        "from abc import ABC, abstractmethod\n"
        "from typing import List\n\n\n"
        "class RenderHook(ABC):\n"
        "    @abstractmethod\n"
        "    def process_renderables(self, renderables):\n"
        "        ...\n\n\n"
        "class Console:\n"
        "    def __init__(self):\n"
        "        self._render_hooks: List[RenderHook] = []\n\n"
        "    def render(self, renderables):\n"
        "        render_hooks = self._render_hooks[:]\n"
        "        for hook in render_hooks:\n"
        "            renderables = hook.process_renderables(renderables)\n"
        "        return renderables\n"
    ),
    "rich/live.py": (
        "from .console import RenderHook\n\n\n"
        "class Live(RenderHook):\n"
        "    def process_renderables(self, renderables):\n"
        "        return renderables\n"
    ),
}
#: ``hook.process_renderables(renderables)`` 所在行。
_SITE = "rich/console.py:18"


def _sites(answer: dict) -> set[str]:
    return {
        f"{site.get('file')}:{site.get('line')}"
        for site in answer.get("name_only_sites", [])
    }


# slow_ok：真实全量索引一次，再做三次 callers 查询。
@pytest.mark.slow_ok
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    ["Live.process_renderables", "process_renderables"],
    ids=["qualified", "bare"],
)
async def test_an_override_of_an_unresolved_same_file_call_is_not_complete(
    tmp_path: Path, name: str
) -> None:
    root = await _index(tmp_path, _RICH)

    answer = await _callers(root, name, "rich/live.py")

    assert answer["completeness"] != "complete"
    assert "NAME_ONLY_INBOUND" in answer.get("completeness_reasons", [])
    assert _SITE in _sites(answer)


@pytest.mark.slow_ok
@pytest.mark.asyncio
async def test_the_same_file_definition_keeps_its_possible_site(tmp_path: Path) -> None:
    root = await _index(tmp_path, _RICH)

    answer = await _callers(root, "RenderHook.process_renderables", "rich/console.py")

    assert answer["completeness"] != "complete"
    assert _SITE in _sites(answer)
