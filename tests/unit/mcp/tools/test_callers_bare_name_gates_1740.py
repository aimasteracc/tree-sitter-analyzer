"""#1740：裸方法名 + ``file_path`` 必须经过与限定名相同的完整性门。

dogfood r10：``nav callers function_name=getDelegateAdapter file_path=.../Gson.java``
给出 ``complete, 0``，而 ``Gson.getDelegateAdapter`` 给出 ``unknown, NAME_ONLY_INBOUND``
并在 ``name_only_sites`` 点名 5 个真实调用方（gson 7/40、rich 4/40 错误 complete）。
裸名查询走 SQL 快路径，从不查询接收者无法绑定的同名调用点。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

# gson 形态：接收者是参数 / 字段，类型无法绑定（只按同名匹配）。
_GSON = {
    "src/com/google/gson/Gson.java": (
        "package com.google.gson;\n\n"
        "public final class Gson {\n"
        "  public <T> TypeAdapter<T> getDelegateAdapter(TypeAdapterFactory skipPast, Object type) {\n"
        "    return null;\n"
        "  }\n"
        "}\n"
    ),
    "src/com/google/gson/internal/Excluder.java": (
        "package com.google.gson.internal;\n\n"
        "import com.google.gson.Gson;\n\n"
        "public final class Excluder {\n"
        "  public Object create(Gson gson, Object type) {\n"
        "    return gson.getDelegateAdapter(null, type);\n"
        "  }\n"
        "}\n"
    ),
}

# rich 形态：局部别名 `_Style = Style` 与属性接收者 `self.console`。
_RICH = {
    "rich/style.py": (
        "class Style:\n"
        "    @classmethod\n"
        "    def from_color(cls, color=None):\n"
        "        return cls()\n"
    ),
    "rich/ansi.py": (
        "from .style import Style\n\n\n"
        "def decode(text):\n"
        "    _Style = Style\n"
        "    return _Style.from_color(text)\n"
    ),
    "rich/console.py": (
        "class Console:\n"
        "    def set_alt_screen(self, enable=True):\n"
        "        return enable\n"
    ),
    "rich/live.py": (
        "class Live:\n"
        "    def __init__(self, console):\n"
        "        self.console = console\n\n"
        "    def start(self):\n"
        "        self.console.set_alt_screen(True)\n"
    ),
    "rich/bound.py": (
        "from .console import Console\n\n\n"
        "def run():\n"
        "    console = Console()\n"
        "    return console.set_alt_screen(False)\n"
    ),
}


async def _index(root: Path, files: dict[str, str]) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True
    return str(root)


async def _callers(root: str, name: str, file_path: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "file_path": file_path, "include_bodies": False}
    )


def _sites(result: dict) -> list[tuple[str, int]]:
    return [
        (site["file"], site["line"]) for site in result.get("name_only_sites") or []
    ]


@pytest.mark.asyncio
# slow_ok：两种语言的真实全量索引与每个模式各一次 callers 查询。
@pytest.mark.slow_ok
@pytest.mark.parametrize(
    ("files", "bare", "qualified", "file_path", "missed"),
    [
        (
            _GSON,
            "getDelegateAdapter",
            "Gson.getDelegateAdapter",
            "src/com/google/gson/Gson.java",
            [("src/com/google/gson/internal/Excluder.java", 7)],
        ),
        (
            _RICH,
            "from_color",
            "Style.from_color",
            "rich/style.py",
            [("rich/ansi.py", 6)],
        ),
    ],
    ids=["gson-java", "rich-python"],
)
async def test_a_bare_name_is_never_more_confident_than_its_qualified_form(
    tmp_path, files, bare, qualified, file_path, missed
) -> None:
    root = await _index(tmp_path, files)

    bare_result = await _callers(root, bare, file_path)
    qualified_result = await _callers(root, qualified, file_path)

    assert qualified_result["completeness"] != "complete"
    assert "NAME_ONLY_INBOUND" in qualified_result["completeness_reasons"]
    # RED（#1740 之前）：裸名给出 complete、0 个调用方、没有 name_only_sites。
    assert bare_result["completeness"] == qualified_result["completeness"]
    assert "NAME_ONLY_INBOUND" in bare_result["completeness_reasons"]
    assert _sites(bare_result) == missed == _sites(qualified_result)


@pytest.mark.asyncio
@pytest.mark.slow_ok  # 同上：一次真实全量索引
async def test_a_bound_caller_is_listed_once_and_not_reported_as_name_only(
    tmp_path,
) -> None:
    # `console = Console(); console.set_alt_screen()` 是确定调用方；`self.console`
    # 那一处仍只按同名匹配。确定的调用方不得重复出现在 name_only_sites 里。
    root = await _index(tmp_path, _RICH)

    result = await _callers(root, "set_alt_screen", "rich/console.py")

    listed = [(c["file"], c["line"]) for c in result["callers"]]
    assert ("rich/bound.py", 4) in listed
    assert "NAME_ONLY_INBOUND" in result["completeness_reasons"]
    assert _sites(result) == [("rich/live.py", 6)]


# TSA 自身（#1740 复核）：经混入类 MRO 绑定的实例调用只在调用图里，SQL 边上没有。
_MIXIN = {
    "fmt/rows.py": (
        "class RowsMixin:\n    def _format_row(self, value):\n        return value\n"
    ),
    "fmt/table.py": (
        "from .rows import RowsMixin\n\n\nclass TableFormatter(RowsMixin):\n    pass\n"
    ),
    "tests/test_rows.py": (
        "from fmt.table import TableFormatter\n\n\n"
        "def test_row():\n"
        "    formatter = TableFormatter()\n"
        "    return formatter._format_row(1)\n"
    ),
}


@pytest.mark.asyncio
@pytest.mark.slow_ok  # 一次真实全量索引与两种模式的查询
async def test_a_bare_name_lists_the_callers_its_qualified_form_binds(tmp_path) -> None:
    root = await _index(tmp_path, _MIXIN)

    bare = await _callers(root, "_format_row", "fmt/rows.py")
    qualified = await _callers(root, "RowsMixin._format_row", "fmt/rows.py")

    def listed(result: dict) -> list[tuple[str, str]]:
        return sorted((c["file"], c["name"]) for c in result["callers"])

    assert listed(qualified) == [("tests/test_rows.py", "test_row")]
    assert listed(bare) == listed(qualified)
    assert bare["completeness"] == qualified["completeness"]
