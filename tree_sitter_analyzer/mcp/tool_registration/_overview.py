"""Tool registration — overview."""
from typing import Any

from ..tools.overview_tool import OverviewTool
from ._shared import _make_handler


def _register_overview_tools(registry: Any, project_root: str | None) -> None:
    """Register overview tools."""
    # overview
    overview_tool = OverviewTool(project_root)
    registry.register(
        name="overview",
        toolset="overview",
        category="project-overview",
        schema=overview_tool.get_tool_definition(),
        handler=_make_handler(overview_tool),
        description="Unified project overview with all analysis tools",
        emoji="📊",
    )
