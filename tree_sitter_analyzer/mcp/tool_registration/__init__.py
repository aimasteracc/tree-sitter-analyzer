"""MCP tool registration — composable architecture."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from ..registry import TOOLSET_DEFINITIONS, get_registry
from ._analysis import _register_analysis_tools
from ._diagnostic import _register_diagnostic_tools
from ._index import _register_index_tools
from ._navigation import _register_navigation_tools
from ._optimization import _register_optimization_tools
from ._overview import _register_overview_tools
from ._query import _register_query_tools
from ._safety import _register_safety_tools

__all__ = ["register_all_tools", "get_tool_info"]


def register_all_tools(project_root: str | None = None) -> None:
    """
    Register all MCP tools with the ToolRegistry.

    Args:
        project_root: Optional project root directory for tool initialization
    """
    registry = get_registry()

    _register_analysis_tools(registry, project_root)
    _register_query_tools(registry, project_root)
    _register_navigation_tools(registry, project_root)
    _register_safety_tools(registry, project_root)
    _register_diagnostic_tools(registry, project_root)
    _register_index_tools(registry, project_root)
    _register_overview_tools(registry, project_root)
    _register_optimization_tools(registry, project_root)


def get_tool_info() -> dict[str, Any]:
    """
    Get information about all registered tools.

    Returns:
        Dictionary with toolsets, tools, and metadata
    """
    registry = get_registry()
    return {
        "toolsets": TOOLSET_DEFINITIONS,
        "registered_tools": registry.get_toolsets(),
    }
