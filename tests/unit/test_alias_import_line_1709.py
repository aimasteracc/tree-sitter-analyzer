"""#1709：只经改名导入调用的目标，其导入行何时不再让答复停在 ``incomplete``。

#1670 已规定：有调用方、别名私有、本文件中别名的每次出现都是解析到目标的调用边、
且别名没有被再导出时，``from m import f as _f`` 这一行只是绑定。dogfood 第 9 轮
有 3 个目标仍停在 ``NON_CALL_REFERENCES``，只因为“再导出”的判定把别的文件里
**同名的独立改名导入**（``from .other import g as _f``、另一个文件也
``from .core import f as _f``）当成了再导出。

经公开的 ``nav callers``（``CodeGraphCallersTool``）在已索引的夹具上验证：

* 别名只被调用、别的文件只是独立地绑定同一个别名 → ``complete``；
* 反例（保持非 ``complete``）：别名也作 ``key=`` 回调传递（并点名该位置）；别名被别的
  模块经模块属性调用、或被别的模块导入（再导出，点名再导出的位置）；0 个调用方时
  导入行仍是引用（#1645）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_CORE = (
    "def only_called(x):\n    return x\n\n\n"
    "def shared_alias(x):\n    return x\n\n\n"
    "def callback_target(x):\n    return x\n\n\n"
    "def via_attribute(x):\n    return x\n\n\n"
    "def reimported(x):\n    return x\n\n\n"
    "def zero_callers(x):\n    return x\n"
)
# 第 14 行把 `_cb` 作为 `key=` 回调传递。
_A = (
    "from .core import only_called as _only_called\n"
    "from .core import shared_alias as _shared\n"
    "from .core import callback_target as _cb\n"
    "from .core import via_attribute as _attr\n"
    "from .core import reimported as _reimp\n\n\n"
    "def use_a(x):\n"
    "    _only_called(x)\n"
    "    _shared(x)\n"
    "    _attr(x)\n"
    "    _reimp(x)\n"
    "    _cb(x)\n"
    "    return sorted([x], key=_cb)\n"
)
# 同名的独立绑定：`_only_called` 指向别的函数，`_shared` 也直接改名导入 `core`。
_B = (
    "from .core import shared_alias as _shared\n"
    "from .other import different as _only_called\n\n\n"
    "def use_b(x):\n"
    "    _only_called(x)\n"
    "    return _shared(x)\n"
)
_OTHER = "def different(x):\n    return -x\n"
_ATTRIBUTE_USER = (
    "import pkg.a as owner\n\n\ndef via_module(x):\n    return owner._attr(x)\n"
)
_REIMPORTER = "from .a import _reimp\n\n\ndef via_reimport(x):\n    return _reimp(x)\n"
_ZERO = "from .core import zero_callers as _zero\n"


@pytest.fixture
async def alias_line_root(tmp_path: Path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    files = {
        "__init__.py": "",
        "core.py": _CORE,
        "a.py": _A,
        "b.py": _B,
        "other.py": _OTHER,
        "attribute_user.py": _ATTRIBUTE_USER,
        "reimporter.py": _REIMPORTER,
        "zero.py": _ZERO,
    }
    for name, text in files.items():
        (pkg / name).write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 20}
    )
    assert indexed["published"] is True
    return str(tmp_path)


async def _callers(root: str, name: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "file_path": "pkg/core.py", "include_bodies": False}
    )


def _names(result: dict) -> set[str]:
    return {entry["name"] for entry in result["callers"]}


def _sites(result: dict) -> set[tuple[str, int]]:
    return {(s["file"], s["line"]) for s in result["non_call_reference_sites"] or []}


@pytest.mark.asyncio
async def test_unrelated_binding_of_the_same_alias_is_not_a_reexport(
    alias_line_root: str,
) -> None:
    result = await _callers(alias_line_root, "only_called")

    assert _names(result) == {"use_a"}
    assert (result["completeness"], result["completeness_reasons"]) == (
        "complete",
        [],
    )


@pytest.mark.asyncio
async def test_two_files_aliasing_the_same_target_are_both_accounted(
    alias_line_root: str,
) -> None:
    result = await _callers(alias_line_root, "shared_alias")

    assert _names(result) == {"use_a", "use_b"}
    assert (result["completeness"], result["completeness_reasons"]) == (
        "complete",
        [],
    )


@pytest.mark.asyncio
async def test_alias_passed_as_a_callback_stays_a_reference(
    alias_line_root: str,
) -> None:
    result = await _callers(alias_line_root, "callback_target")

    assert _names(result) == {"use_a"}
    assert result["completeness"] == "incomplete"
    assert result["completeness_reasons"] == ["NON_CALL_REFERENCES"]
    assert ("pkg/a.py", 14) in _sites(result)


@pytest.mark.asyncio
async def test_alias_used_as_a_module_attribute_stays_a_reference(
    alias_line_root: str,
) -> None:
    result = await _callers(alias_line_root, "via_attribute")

    assert result["completeness"] == "incomplete"
    assert result["completeness_reasons"] == ["NON_CALL_REFERENCES"]
    # #1705：owner._attr() 已解析为调用方；它说明别名被再导出，导入行仍是引用。
    assert _names(result) == {"use_a", "via_module"}
    assert ("pkg/a.py", 4) in _sites(result)


@pytest.mark.asyncio
async def test_reimported_alias_stays_a_reference_and_names_the_reexport(
    alias_line_root: str,
) -> None:
    result = await _callers(alias_line_root, "reimported")

    assert _names(result) == {"use_a", "via_reimport"}
    assert result["completeness"] == "incomplete"
    assert {("pkg/a.py", 5), ("pkg/reimporter.py", 1)} <= _sites(result)


@pytest.mark.asyncio
async def test_zero_callers_keep_the_alias_import_as_a_reference(
    alias_line_root: str,
) -> None:
    result = await _callers(alias_line_root, "zero_callers")

    assert result["caller_count"] == 0
    assert result["completeness"] == "unknown"
    assert result["completeness_reasons"] == ["NON_CALL_REFERENCES"]
    assert _sites(result) == {("pkg/zero.py", 1)}


def test_alias_check_is_conservative_when_evidence_cannot_be_read() -> None:
    import re

    from tree_sitter_analyzer.mcp.tools.callers_alias_refs import (
        _mention_sites,
        alias_reference_check,
    )

    class _Broken:
        def get_conn(self):
            raise AttributeError("no index")

    def _lines(text: str, pattern: re.Pattern[str], covered) -> list[int]:
        return []

    text = "from .core import f as _f\n\n\ndef g():\n    return _f()\n"
    check = alias_reference_check(
        _Broken(), "a.py", text, "f", {"core.py"}, _lines, {"b.py": "_f()\n"}
    )
    assert check.masked == frozenset()
    assert (
        _mention_sites(
            _Broken(), "a.py", "_f", "f", {"core.py"}, {"b.py": "_f()\n"}, _lines
        )
        is None
    )
    # 没有别的文件提到别名时不读索引。
    assert _mention_sites(_Broken(), "a.py", "_f", "f", {"core.py"}, {}, _lines) == []
