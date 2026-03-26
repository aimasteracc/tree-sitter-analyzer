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
    "get_code_outline": {
        "description": (
            "Return hierarchical outline (package → class → method) without body content. "
            "Use before extract_code_section for outline-first navigation."
        ),
        "module": "get_code_outline_tool",
        "class": "GetCodeOutlineTool",
    },
}

__all__ = [
    "AVAILABLE_TOOLS",
]
