"""``from facade import f`` 而 ``facade`` 只是再导出 ``impl.f``：调用必须归属到 ``impl.f``。

dogfood（#1669 / #1670 门）：``diff_snapshot_readonly.py`` 经
``from .source_oracle_git import entry_map_storage`` 调用，持久化解析指向再导出
文件 ``source_oracle_git.py``，于是 ``nav callers entry_map_storage``（定义文件
``source_oracle_budget.py``）漏掉这个调用，却答 ``complete``——一个错误的普查。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_FILES = {
    "pkg/__init__.py": "",
    "pkg/impl.py": "def helper(x):\n    return x\n\n\ndef local_use(x):\n    return helper(x)\n",
    "pkg/facade.py": "from .impl import helper\n",
    "pkg/deep.py": "from .facade import helper\n",
    "user.py": (
        "from pkg.facade import helper\n\n\ndef use(x):\n    return helper(x)\n"
    ),
    "deep_user.py": (
        "from pkg.deep import helper\n\n\ndef use_deep(x):\n    return helper(x)\n"
    ),
}


@pytest.fixture
async def reexport_root(tmp_path: Path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel, text in _FILES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 20}
    )
    assert indexed["published"] is True
    return str(tmp_path)


@pytest.mark.asyncio
async def test_calls_through_a_reexport_reach_the_definition(
    reexport_root: str,
) -> None:
    result = await CodeGraphCallersTool(reexport_root).execute(
        {"function_name": "helper", "file_path": "pkg/impl.py", "include_bodies": False}
    )

    assert {(c["file"], c["name"], c["line"]) for c in result["callers"]} == {
        ("pkg/impl.py", "local_use", 5),
        ("user.py", "use", 4),
        ("deep_user.py", "use_deep", 4),
    }
