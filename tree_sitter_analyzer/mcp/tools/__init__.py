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
    "dead_code_path": {
        "description": (
            "Analyze functions for unreachable code paths. "
            "Detects code after terminal statements and dead branches."
        ),
        "module": "dead_code_path_tool",
        "class": "DeadCodePathTool",
    },
    "empty_block": {
        "description": (
            "Analyze code for empty blocks that may hide bugs. "
            "Detects empty function bodies, empty catch blocks, empty loops."
        ),
        "module": "empty_block_tool",
        "class": "EmptyBlockTool",
    },
    "magic_string": {
        "description": (
            "Analyze code for hardcoded string literals that should be constants. "
            "Detects magic strings and repeated strings."
        ),
        "module": "magic_string_tool",
        "class": "MagicStringTool",
    },
    "tautological_condition": {
        "description": (
            "Detect conditions that always evaluate to the same value. "
            "Finds contradictory, subsumed, and tautological comparisons."
        ),
        "module": "tautological_condition_tool",
        "class": "TautologicalConditionTool",
    },
    "flag_argument": {
        "description": (
            "Detect boolean parameters (flag arguments) that indicate "
            "SRP violations in function signatures."
        ),
        "module": "flag_argument_tool",
        "class": "FlagArgumentTool",
    },
    "nested_ternary": {
        "description": (
            "Detect deeply nested ternary/conditional expressions "
            "that hurt readability (depth >= 2)."
        ),
        "module": "nested_ternary_tool",
        "class": "NestedTernaryTool",
    },
    "assignment_in_conditional": {
        "description": (
            "Detect assignments used as if/while conditions "
            "(likely = vs == typo)."
        ),
        "module": "assignment_in_conditional_tool",
        "class": "AssignmentInConditionalTool",
    },
}

__all__ = [
    "AVAILABLE_TOOLS",
]
