"""#1611 回归测试的共享项目构造器：同一进程内经公开路由刷新索引。

各工具的测试使用一个长期存活的实例：先建索引并提问，再新增一个调用者并经
``index action=cache mode=index`` 刷新，然后再问一次，断言新调用者可见。
"""

from __future__ import annotations

from pathlib import Path

#: 初始源码：``target`` 只有一个调用者 ``old_caller``。
INITIAL_SOURCE = (
    "def target():\n    return 1\n\n\ndef old_caller():\n    return target()\n"
)
#: 刷新前追加的新调用者。
NEW_CALLER_SOURCE = "\n\ndef new_caller():\n    return target()\n"


async def _refresh_index(project: Path) -> None:
    """经 index facade 的公开路由（action=cache mode=index）刷新索引。"""
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    _, lookup = create_tool_registry(project_root=str(project))
    result = await lookup["index"].execute({"action": "cache", "mode": "index"})
    assert result.get("success") is True, result


async def make_indexed_project(tmp_path: Path) -> Path:
    """建立只含 ``app.py`` 的项目并完成首次索引。"""
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text(INITIAL_SOURCE, encoding="utf-8")
    await _refresh_index(project)
    return project


async def add_caller_and_refresh(project: Path) -> None:
    """追加 ``new_caller`` 并经公开路由刷新索引（发布新 generation）。"""
    app = project / "app.py"
    app.write_text(app.read_text(encoding="utf-8") + NEW_CALLER_SOURCE, "utf-8")
    await _refresh_index(project)
