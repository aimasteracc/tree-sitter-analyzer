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
    "description": "Tree-sitter based code analyzer with MCP support",
    "protocol_version": "2024-11-05",
    "capabilities": {
        "tools": {},
        "resources": {},
        "prompts": {},
        "logging": {},
    },
}

__all__ = [
    "MCP_INFO",
    "__version__",
]
