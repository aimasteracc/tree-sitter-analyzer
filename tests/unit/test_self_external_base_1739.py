"""#1739：``self.m()`` 只在 ``m`` 经外围类 MRO 解析到项目定义时才是确定调用。

dogfood 第 10 轮（rich / pydantic）：

* ``class _TrackThread(Thread)`` 没有 ``join``，``self.join()`` 是 ``Thread.join``，
  却被绑定到项目里唯一的 ``Text.join``（``callee_resolution: "project"``）；
* ``class LimitedDict(dict)`` 里的 ``self.keys()`` 是 ``dict.keys``，却被绑定到
  ``GetterDict.keys``；
* ``lambda self, v: list(self.keys())`` 的 ``self`` 是 lambda 参数，不是方法接收者。

这些是确定的假调用方。修复后它们至多是可能调用方（答案不得 ``complete``）。
对照：项目基类定义 ``m`` 时仍是确定调用；子类覆写仍只是可能目标（#1648）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_FILES = {
    "pkg/__init__.py": "",
    "pkg/text.py": (
        "class Text:\n"
        "    def join(self, lines):\n"
        "        return lines\n"
    ),
    "pkg/progress.py": (
        "from threading import Thread\n\n\n"
        "class _TrackThread(Thread):\n"
        "    def __exit__(self, *exc):\n"
        "        self.join()\n"
    ),
    "pkg/utils.py": (
        "class GetterDict:\n"
        "    def keys(self):\n"
        "        return []\n"
    ),
    "pkg/generics.py": (
        "class LimitedDict(dict):\n"
        "    def __setitem__(self, key, value):\n"
        "        return list(self.keys())\n"
    ),
    "pkg/serializers.py": (
        "def nested_serializers():\n"
        "    return lambda self, v: list(self.keys())\n"
    ),
    # lambda 定义在方法里：它的 `self` 参数遮蔽了方法的 `self`。
    "pkg/holder.py": (
        "class Holder:\n"
        "    def items(self):\n"
        "        return []\n\n"
        "    def build(self):\n"
        "        return lambda self: self.items()\n\n"
        "    def direct(self):\n"
        "        return self.items()\n"
    ),
    # 对照：项目基类定义了 `fmt`，经 MRO 的 `self.fmt()` 仍是确定调用。
    "pkg/fmt_base.py": (
        "class FmtBase:\n"
        "    def fmt(self):\n"
        "        return ''\n"
    ),
    "pkg/fmt_child.py": (
        "from pkg.fmt_base import FmtBase\n\n\n"
        "class FmtChild(FmtBase):\n"
        "    def show(self):\n"
        "        return self.fmt()\n\n\n"
        "class FmtLeaf(FmtChild):\n"
        "    def fmt(self):\n"
        "        return 'leaf'\n"
    ),
}


@pytest.fixture
async def ext_root(tmp_path: Path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel, text in _FILES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True
    return str(tmp_path)


async def _callers(root: str, name: str, file_path: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "file_path": file_path, "include_bodies": False}
    )


def _caller_sites(result: dict) -> set[tuple[str, str]]:
    return {(entry["file"], entry["name"]) for entry in result["callers"]}


@pytest.mark.asyncio
async def test_self_call_in_thread_subclass_is_not_a_project_caller(
    ext_root: str,
) -> None:
    # rich：`_TrackThread(Thread).__exit__` 的 `self.join()` 是 `Thread.join`。
    result = await _callers(ext_root, "Text.join", "pkg/text.py")

    assert _caller_sites(result) == set()
    assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_self_call_in_dict_subclass_and_lambda_are_not_callers(
    ext_root: str,
) -> None:
    # pydantic：`LimitedDict(dict)` 的 `self.keys()` 与 lambda 参数 `self` 都不是
    # `GetterDict.keys` 的确定调用方。
    result = await _callers(ext_root, "GetterDict.keys", "pkg/utils.py")

    assert _caller_sites(result) == set()
    assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_lambda_self_parameter_inside_a_method_is_not_the_receiver(
    ext_root: str,
) -> None:
    # 方法里的 `lambda self: self.items()`：只有 `direct` 是确定调用方。
    result = await _callers(ext_root, "Holder.items", "pkg/holder.py")

    assert _caller_sites(result) == {("pkg/holder.py", "direct")}
    assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_project_base_defining_the_method_still_binds(ext_root: str) -> None:
    # 对照：MRO 中的项目基类定义了 `fmt`。
    result = await _callers(ext_root, "FmtBase.fmt", "pkg/fmt_base.py")

    assert _caller_sites(result) == {("pkg/fmt_child.py", "show")}


@pytest.mark.asyncio
async def test_override_in_a_subclass_stays_possible(ext_root: str) -> None:
    # 对照（#1648）：`FmtLeaf.fmt` 覆写了 `fmt`，`FmtChild.show` 可能分派到它。
    result = await _callers(ext_root, "FmtLeaf.fmt", "pkg/fmt_child.py")

    assert result["caller_count"] == 0
    assert result["completeness"] != "complete"
