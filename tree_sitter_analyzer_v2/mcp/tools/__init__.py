"""
MCP Tools for tree-sitter-analyzer v2.

This module provides MCP tool implementations:
- BaseTool: Base class for all tools
- ToolRegistry: Registry for managing tools
- AnalyzeTool: Analyze code structure
- FindFilesTool: Find files using fd
- SearchContentTool: Search content using ripgrep
- QueryTool: Query code elements
- CheckCodeScaleTool: Check code scale and complexity
- FindAndGrepTool: Combined file finding and content search
- ExtractCodeSectionTool: Extract code sections by line range
- AnalyzeCodeGraphTool: Analyze code structure and call relationships (NEW!)
- FindFunctionCallersTool: Find who calls a function (NEW!)
- QueryCallChainTool: Find call paths between functions (NEW!)
"""

from tree_sitter_analyzer_v2.mcp.tools.analyze import AnalyzeTool
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool
from tree_sitter_analyzer_v2.mcp.tools.code_graph import (
    AnalyzeCodeGraphTool,
    FindFunctionCallersTool,
    QueryCallChainTool,
    VisualizeCodeGraphTool,
)
from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool
from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool
from tree_sitter_analyzer_v2.mcp.tools.query import QueryTool
from tree_sitter_analyzer_v2.mcp.tools.registry import ToolRegistry
from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool
from tree_sitter_analyzer_v2.mcp.tools.replace import ReplaceInFileTool
from tree_sitter_analyzer_v2.mcp.tools.search import FindFilesTool, SearchContentTool
from tree_sitter_analyzer_v2.mcp.tools.write import WriteFileTool

__all__ = [
    "BaseTool",
    "ToolRegistry",
    "AnalyzeTool",
    "FindFilesTool",
    "SearchContentTool",
    "QueryTool",
    "CheckCodeScaleTool",
    "FindAndGrepTool",
    "ExtractCodeSectionTool",
    "AnalyzeCodeGraphTool",
    "FindFunctionCallersTool",
    "QueryCallChainTool",
    "VisualizeCodeGraphTool",
    "WriteFileTool",
    "ReplaceInFileTool",
]
