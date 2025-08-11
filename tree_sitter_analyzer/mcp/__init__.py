#!/usr/bin/env python3
"""
MCP (Model Context Protocol) integration for Tree-sitter Analyzer

This module provides MCP server functionality that exposes the tree-sitter
analyzer capabilities through the Model Context Protocol.
"""

from typing import Any

__version__ = "0.2.1"
__author__ = "Tree-sitter Analyzer Team"

# MCP module metadata
MCP_INFO: dict[str, Any] = {
    "name": "tree-sitter-analyzer-mcp",
    "version": __version__,
    "description": "Tree-sitter based code analyzer with MCP support - Solve LLM token limit problems for large code files",
    "protocol_version": "2024-11-05",
    "capabilities": {
        "tools": {
            "description": "Three-step workflow for analyzing large code files",
            "available_tools": [
                "check_code_scale",
                "analyze_code_structure",
                "extract_code_section"
            ],
            "workflow": [
                "1. check_code_scale - Get file metrics and complexity",
                "2. analyze_code_structure - Generate structure tables for large files",
                "3. extract_code_section - Get specific code sections by line range"
            ]
        },
        "resources": {},
        "prompts": {
            "usage_guide": "See README.md AI Assistant Integration section for complete workflow guide"
        },
        "logging": {},
    },
}

__all__ = [
    "MCP_INFO",
    "__version__",
]
