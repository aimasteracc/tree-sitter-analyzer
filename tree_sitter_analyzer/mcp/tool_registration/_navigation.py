"""Tool registration — navigation."""
from typing import Any

from ..tools.batch_search_tool import BatchSearchTool
from ..tools.find_and_grep_tool import FindAndGrepTool
from ..tools.list_files_tool import ListFilesTool
from ..tools.search_content_tool import SearchContentTool
from ._shared import _make_handler


def _register_navigation_tools(registry: Any, project_root: str | None) -> None:
    """Register navigation tools."""
    # list_files
    list_tool = ListFilesTool(project_root)
    registry.register(
        name="list_files",
        toolset="navigation",
        category="file-listing",
        schema=list_tool.get_tool_definition(),
        handler=_make_handler(list_tool),
        description="List files with filtering by type, pattern, size",
        emoji="📁",
    )

    # find_and_grep
    find_tool = FindAndGrepTool(project_root)
    registry.register(
        name="find_and_grep",
        toolset="navigation",
        category="file-search",
        schema=find_tool.get_tool_definition(),
        handler=_make_handler(find_tool),
        description="Find files by name and grep content with patterns",
        emoji="🔍",
    )

    # search_content
    search_tool = SearchContentTool(project_root)
    registry.register(
        name="search_content",
        toolset="navigation",
        category="content-search",
        schema=search_tool.get_tool_definition(),
        handler=_make_handler(search_tool),
        description="Search file content with regex and context",
        emoji="🔎",
    )

    # batch_search
    batch_tool = BatchSearchTool(project_root)
    registry.register(
        name="batch_search",
        toolset="navigation",
        category="batch-search",
        schema=batch_tool.get_tool_definition(),
        handler=_make_handler(batch_tool),
        description="Search multiple patterns across files in batch",
        emoji="📦",
    )
