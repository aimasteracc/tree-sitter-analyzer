"""Tool registration — index."""
from typing import Any

from ..tools.build_project_index_tool import BuildProjectIndexTool
from ..tools.get_project_summary_tool import GetProjectSummaryTool
from ._shared import _make_handler


def _register_index_tools(registry: Any, project_root: str | None) -> None:
    """Register index tools."""
    # build_project_index
    build_tool = BuildProjectIndexTool(project_root)
    registry.register(
        name="build_project_index",
        toolset="index",
        category="project-index",
        schema=build_tool.get_tool_definition(),
        handler=_make_handler(build_tool),
        description="Build persistent project index for fast queries",
        emoji="🏗️",
    )

    # get_project_summary
    summary_tool = GetProjectSummaryTool(project_root)
    registry.register(
        name="get_project_summary",
        toolset="index",
        category="project-summary",
        schema=summary_tool.get_tool_definition(),
        handler=_make_handler(summary_tool),
        description="Get project summary: stats, structure, key files",
        emoji="📚",
    )
