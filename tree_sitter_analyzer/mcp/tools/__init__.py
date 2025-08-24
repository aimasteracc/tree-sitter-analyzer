#!/usr/bin/env python3
"""
MCP Tools package for Tree-sitter Analyzer

This package contains all MCP tools that provide specific functionality
through the Model Context Protocol.
"""

from typing import Any

# Tool registry for easy access
AVAILABLE_TOOLS: dict[str, dict[str, Any]] = {
    "analyze_code_scale": {
        "description": "Analyze code scale, complexity, and structure metrics",
        "module": "analyze_scale_tool",
        "class": "AnalyzeScaleTool",
    },
    # Future tools will be added here
    # "read_code_partial": {
    #     "description": "Read partial content from code files",
    #     "module": "read_partial_tool",
    #     "class": "ReadPartialTool",
    # },
}

__all__ = [
    "AVAILABLE_TOOLS",
]
