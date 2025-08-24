#!/usr/bin/env python3
"""
MCP (Model Context Protocol) integration for Tree-sitter Analyzer

This module provides MCP server functionality that exposes the tree-sitter
analyzer capabilities through the Model Context Protocol.
"""

from typing import Any

# Import main package version for consistency
try:
    from .. import __version__ as main_version

    __version__ = main_version
except ImportError:
    # Fallback version if main package not available
    __version__ = "1.1.0"

__author__ = "Tree-sitter Analyzer Team"

# MCP module metadata
MCP_INFO: dict[str, Any] = {
    "name": "tree-sitter-analyzer-mcp",
    "version": __version__,
    "description": "Tree-sitter based code analyzer with MCP support - Solve LLM token limit problems for large code files",
    "protocol_version": "2024-11-05",
    "capabilities": {"tools": {}, "resources": {}, "prompts": {}, "logging": {}},
}

__all__ = [
    "MCP_INFO",
    "__version__",
]
