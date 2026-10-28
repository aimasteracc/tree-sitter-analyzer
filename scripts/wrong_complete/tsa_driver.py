"""驱动被测对象 TSA：全量索引与 ``nav action=callers`` 查询（进程内）。

这是本包里**唯一**导入 ``tree_sitter_analyzer`` 的模块；判定器与评分器不依赖它。
查询走 ``nav`` facade（与 MCP 客户端看到的同一入口），而不是直接调内部工具类。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: 小型夹具的索引文件上限；真实仓库扫描显式传更大的值。
FIXTURE_MAX_FILES = 200


def write_project(root: Path, files: dict[str, str]) -> Path:
    """把 ``{相对路径: 源码}`` 写到 ``root`` 下（UTF-8、LF）。"""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return root


async def index_project(
    root: Path, max_files: int = FIXTURE_MAX_FILES
) -> dict[str, Any]:
    """全量索引 ``root``；未发布索引时抛出 ``RuntimeError``（失败要响亮）。"""
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    result: dict[str, Any] = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": max_files}
    )
    if result.get("published") is not True:
        raise RuntimeError(f"index not published for {root}: {result}")
    return result


async def query_callers(
    root: Path, function_name: str, file_path: str | None
) -> dict[str, Any]:
    """``nav action=callers``，不带函数体、不截断（limit 5000，与 dogfood 一致）。

    ``file_path`` 为 ``None`` 时不带范围提问（#1798）。
    """
    from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade

    arguments: dict[str, Any] = {
        "action": "callers",
        "function_name": function_name,
        "include_bodies": False,
        "limit": 5000,
    }
    if file_path is not None:
        arguments["file_path"] = file_path
    answer: dict[str, Any] = await build_nav_facade(str(root)).execute(arguments)
    return answer
