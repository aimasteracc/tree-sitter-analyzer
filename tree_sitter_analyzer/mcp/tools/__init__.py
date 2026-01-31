#!/usr/bin/env python3
"""
MCP Tools.

Tool implementations for Model Context Protocol.

Version: 1.10.5
Date: 2026-01-28
"""

from __future__ import annotations

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
