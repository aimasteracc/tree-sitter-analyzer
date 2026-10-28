"""#1773：``@overload`` 存根与实现是同一个方法，``self.m()`` 确定绑定到它。

dogfood r12（pydantic）：``pydantic/experimental/pipeline.py`` 的 ``_Pipeline.constrain``
有约十个 ``@overload`` 存根和一个实现，15 个调用方都是兄弟方法里的
``self.constrain(...)``。外围类里有多个同名定义，``self.constrain`` 在它们之间无法
区分，只是同名匹配：限定名 ``_Pipeline.constrain`` 列出 0 个调用方，裸名列出 16 个。

存根只供类型检查，运行时类体里最后一个（未加 ``@overload`` 的）定义才是方法本身，
因此存根与实现按一个可调用对象处理：两种查询都确定列出这些调用方，答案相同。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.mcp.tools.test_callers_bare_name_gates_1740 import _callers, _index

_FILE = "pkg/pipe.py"

_MODULE_LEVEL = (
    "import typing\n"
    "from typing import overload\n\n\n"
    "class Pipeline:\n"
    "    @overload\n"
    "    def constrain(self, c: int) -> 'Pipeline': ...\n\n"
    "    @typing.overload\n"
    "    def constrain(self, c: str) -> 'Pipeline': ...\n\n"
    "    def constrain(self, c):\n"
    "        return self\n\n"
    "    def gt(self, v):\n"
    "        return self.constrain(v)\n\n"
    "    def lt(self, v):\n"
    "        return self.constrain(v)\n"
)

_NESTED = (
    "from typing import overload\n\n\n"
    "def make():\n"
    "    class Pipeline:\n"
    "        @overload\n"
    "        def constrain(self, c: int) -> 'Pipeline': ...\n\n"
    "        @overload\n"
    "        def constrain(self, c: str) -> 'Pipeline': ...\n\n"
    "        def constrain(self, c):\n"
    "            return self\n\n"
    "        def gt(self, v):\n"
    "            return self.constrain(v)\n\n"
    "        def lt(self, v):\n"
    "            return self.constrain(v)\n\n"
    "    return Pipeline\n"
)

# 两个都不是 ``@overload`` 的同名定义（条件定义）：哪一个生效无法静态确定。
_CONDITIONAL = (
    "import sys\n\n\n"
    "class Pipeline:\n"
    "    if sys.version_info >= (3, 12):\n"
    "        def constrain(self, c):\n"
    "            return self\n"
    "    else:\n"
    "        def constrain(self, c):\n"
    "            return None\n\n"
    "    def gt(self, v):\n"
    "        return self.constrain(v)\n"
)

_MODES = pytest.mark.parametrize(
    "name", ["Pipeline.constrain", "constrain"], ids=["qualified", "bare"]
)


def _names(answer: dict) -> set[str]:
    return {str(caller.get("name")) for caller in answer.get("callers") or []}


def _name_only(answer: dict) -> set[str]:
    return {str(site.get("caller")) for site in answer.get("name_only_sites") or []}


# slow_ok：每个用例真实全量索引一次，再做一次 callers 查询。
@pytest.mark.slow_ok
@pytest.mark.asyncio
@_MODES
@pytest.mark.parametrize("source", [_MODULE_LEVEL, _NESTED], ids=["module", "nested"])
async def test_self_calls_bind_to_an_overloaded_method(
    tmp_path: Path, name: str, source: str
) -> None:
    root = await _index(tmp_path, {"pkg/__init__.py": "", _FILE: source})

    answer = await _callers(root, name, _FILE)

    assert _names(answer) == {"gt", "lt"}, answer
    assert not answer.get("name_only_inbound"), answer
    assert answer["completeness"] == "complete", answer


@pytest.mark.slow_ok
@pytest.mark.asyncio
@pytest.mark.parametrize("source", [_MODULE_LEVEL, _NESTED], ids=["module", "nested"])
async def test_bare_and_qualified_answer_alike_for_an_overloaded_method(
    tmp_path: Path, source: str
) -> None:
    root = await _index(tmp_path, {"pkg/__init__.py": "", _FILE: source})

    qualified = await _callers(root, "Pipeline.constrain", _FILE)
    bare = await _callers(root, "constrain", _FILE)

    for key in ("completeness", "completeness_reasons", "caller_count"):
        assert qualified[key] == bare[key], (key, qualified, bare)
    assert _names(qualified) == _names(bare)


@pytest.mark.slow_ok
@pytest.mark.asyncio
async def test_two_plain_definitions_stay_ambiguous(tmp_path: Path) -> None:
    root = await _index(tmp_path, {"pkg/__init__.py": "", _FILE: _CONDITIONAL})

    answer = await _callers(root, "Pipeline.constrain", _FILE)

    # 没有 ``@overload``：两个定义都保留，``self.constrain`` 仍只是同名匹配。
    assert answer["completeness"] != "complete", answer
    assert "gt" not in _names(answer), answer
    assert "gt" in _name_only(answer) or answer.get("name_only_inbound"), answer
