#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP (Model Context Protocol) integration for Tree-sitter Analyzer

This module provides MCP server functionality that exposes the tree-sitter
analyzer capabilities through the Model Context Protocol.
"""

from typing import Any, Dict

__version__ = "1.0.0"
__author__ = "Tree-sitter Analyzer Team"

# MCP module metadata
MCP_INFO: Dict[str, Any] = {
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
