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
    "trace_impact": {
        "description": (
            "Find all usage sites of a symbol (method/class/function) to assess change impact. "
            "Uses ripgrep for fast search with optional language filtering."
        ),
        "module": "trace_impact_tool",
        "class": "TraceImpactTool",
    },
    "method_chain": {
        "description": (
            "Analyze method/attribute chain length (Law of Demeter violations). "
            "Detects excessively long chains like a.b().c().d()."
        ),
        "module": "method_chain_tool",
        "class": "MethodChainTool",
    },
    "string_concat_loop": {
        "description": (
            "Analyze string concatenation inside loops (O(n^2) risk). "
            "Detects += on strings inside for/while loops."
        ),
        "module": "string_concat_loop_tool",
        "class": "StringConcatLoopTool",
    },
    "duplicate_condition": {
        "description": (
            "Analyze duplicate if conditions (DRY violations). "
            "Detects identical conditions that appear multiple times."
        ),
        "module": "duplicate_condition_tool",
        "class": "DuplicateConditionTool",
    },
    "lazy_class": {
        "description": (
            "Analyze classes for insufficient complexity (lazy classes). "
            "Detects classes with too few methods."
        ),
        "module": "lazy_class_tool",
        "class": "LazyClassTool",
    },
    "god_class": {
        "description": (
            "Analyze classes for excessive size and responsibility (god classes). "
            "Detects classes with too many methods and fields."
        ),
        "module": "god_class_tool",
        "class": "GodClassTool",
    },
}

__all__ = [
    "AVAILABLE_TOOLS",
]
