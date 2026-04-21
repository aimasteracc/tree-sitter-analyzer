"""Tool registration — query."""
from typing import Any

from ..tools.get_code_outline_tool import GetCodeOutlineTool
from ..tools.query_tool import QueryTool
from ..tools.read_partial_tool import ReadPartialTool
from ..tools.semantic_search_tool import SemanticSearchTool
from ._shared import _make_handler


def _register_query_tools(registry: Any, project_root: str | None) -> None:
    """Register query tools."""
    # query_code
    query_tool = QueryTool(project_root)
    registry.register(
        name="query_code",
        toolset="query",
        category="symbol-query",
        schema=query_tool.get_tool_definition(),
        handler=_make_handler(query_tool),
        description="Extract code elements by syntax: functions, classes, imports",
        emoji="🔎",
    )

    # extract_code_section (read_partial)
    partial_tool = ReadPartialTool(project_root)
    registry.register(
        name="extract_code_section",
        toolset="query",
        category="code-extraction",
        schema=partial_tool.get_tool_definition(),
        handler=_make_handler(partial_tool),
        description="Extract code sections by line ranges or semantic boundaries",
        emoji="✂️",
    )

    # get_code_outline
    outline_tool = GetCodeOutlineTool(project_root)
    registry.register(
        name="get_code_outline",
        toolset="query",
        category="code-outline",
        schema=outline_tool.get_tool_definition(),
        handler=_make_handler(outline_tool),
        description="Get code outline: hierarchical structure with metadata",
        emoji="📋",
    )

    # semantic_search
    search_tool = SemanticSearchTool(project_root)
    registry.register(
        name="semantic_search",
        toolset="query",
        category="semantic-search",
        schema=search_tool.get_tool_definition(),
        handler=_make_handler(search_tool, method_name="execute"),
        description="Semantic code search: natural language queries with LLM understanding",
        emoji="🔍",
    )
