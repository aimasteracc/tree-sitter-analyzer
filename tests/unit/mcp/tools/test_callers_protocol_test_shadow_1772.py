"""#1772：未证明接收者的 ``x.m()`` 对测试文件里的同名结构实现同样是可能调用。

dogfood r12（pydantic）：``pydantic/plugin/_schema_validator.py`` 里
``for plugin in plugins: plugin.new_schema_validator(...)``，``plugins`` 注解为
``Iterable[PydanticPluginProtocol]``。真正的目标之一是 ``tests/test_plugins.py`` 里
没有基类的结构实现 ``Plugin1.new_schema_validator``。全局档对非测试调用方剔除
测试文件里的同名定义（只要存在非测试定义，这里是 Protocol 存根），于是测试里的
实现不再是可能目标，限定名与裸名都答 ``complete, 0``。没有存根时它是唯一的
同名定义，不被剔除，答案正确地是 ``unknown``。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.mcp.tools.test_callers_bare_name_gates_1740 import _callers, _index

_PROTOCOL_STUB = (
    "from typing import Protocol\n\n\n"
    "class PluginProtocol(Protocol):\n"
    "    def new_validator(self, schema): ...\n"
)
_NO_STUB = (
    "from typing import Protocol\n\n\n"
    "class PluginProtocol(Protocol):\n"
    "    def other(self): ...\n"
)
_MODULE_LEVEL_IMPL = (
    "from pkg.use import build\n\n\n"
    "class Plugin1:\n"
    "    def new_validator(self, schema):\n"
    "        return schema\n\n\n"
    "def test_structural():\n"
    "    assert build({}, [Plugin1()]) == [{}]\n"
)
_NESTED_IMPL = (
    "from pkg.use import build\n\n\n"
    "def test_structural():\n"
    "    class Plugin1:\n"
    "        def new_validator(self, schema):\n"
    "            return schema\n\n"
    "    assert build({}, [Plugin1()]) == [{}]\n"
)
#: ``plugin.new_validator(schema)`` 所在行。
_SITE = "pkg/use.py:9"


def _project(*, stub: bool, typed: bool, nested: bool = False) -> dict[str, str]:
    annotation = ": Iterable[PluginProtocol]" if typed else ""
    return {
        "pkg/__init__.py": _PROTOCOL_STUB if stub else _NO_STUB,
        "pkg/use.py": (
            "from typing import Iterable\n\nfrom . import PluginProtocol\n\n\n"
            f"def build(schema, plugins{annotation}):\n"
            "    out = []\n"
            "    for plugin in plugins:\n"
            "        out.append(plugin.new_validator(schema))\n"
            "    return out\n"
        ),
        "tests/__init__.py": "",
        "tests/test_plugins.py": _NESTED_IMPL if nested else _MODULE_LEVEL_IMPL,
    }


def _evidence_sites(answer: dict) -> set[str]:
    return {
        f"{site.get('file')}:{site.get('line')}"
        for key in ("name_only_sites", "unresolved_sites")
        for site in answer.get(key) or []
    }


def _assert_not_complete_with_site(answer: dict) -> None:
    assert answer["completeness"] != "complete", answer
    reasons = set(answer.get("completeness_reasons") or [])
    assert reasons & {"NAME_ONLY_INBOUND", "UNRESOLVED_INBOUND"}, answer
    assert _SITE in _evidence_sites(answer), answer


# slow_ok：每个用例真实全量索引一次，再做一次 callers 查询。
@pytest.mark.slow_ok
@pytest.mark.asyncio
@pytest.mark.parametrize("typed", [True, False], ids=["typed", "untyped"])
@pytest.mark.parametrize(
    "name", ["Plugin1.new_validator", "new_validator"], ids=["qualified", "bare"]
)
async def test_a_structural_test_implementation_beside_a_protocol_stub_is_not_complete(
    tmp_path: Path, name: str, typed: bool
) -> None:
    root = await _index(tmp_path, _project(stub=True, typed=typed))

    answer = await _callers(root, name, "tests/test_plugins.py")

    _assert_not_complete_with_site(answer)


@pytest.mark.slow_ok
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name", ["Plugin1.new_validator", "new_validator"], ids=["qualified", "bare"]
)
async def test_a_nested_structural_implementation_beside_a_stub_is_not_complete(
    tmp_path: Path, name: str
) -> None:
    root = await _index(tmp_path, _project(stub=True, typed=True, nested=True))

    answer = await _callers(root, name, "tests/test_plugins.py")

    _assert_not_complete_with_site(answer)


@pytest.mark.slow_ok
@pytest.mark.asyncio
@pytest.mark.parametrize("typed", [True, False], ids=["typed", "untyped"])
async def test_the_protocol_stub_keeps_its_possible_site(
    tmp_path: Path, typed: bool
) -> None:
    root = await _index(tmp_path, _project(stub=True, typed=typed))

    answer = await _callers(root, "PluginProtocol.new_validator", "pkg/__init__.py")

    _assert_not_complete_with_site(answer)


@pytest.mark.slow_ok
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name", ["Plugin1.new_validator", "new_validator"], ids=["qualified", "bare"]
)
async def test_without_a_second_definition_the_answer_stays_unknown(
    tmp_path: Path, name: str
) -> None:
    root = await _index(tmp_path, _project(stub=False, typed=False))

    answer = await _callers(root, name, "tests/test_plugins.py")

    assert answer["completeness"] == "unknown", answer
    _assert_not_complete_with_site(answer)
