#!/usr/bin/env python3
"""
MCP Resources Module

This module provides MCP (Model Context Protocol) resource implementations
for the tree-sitter-analyzer project. Resources provide dynamic content
access through URI-based identification.

Resources:
    - CodeFileResource: Access to code file content
    - ProjectStatsResource: Access to project statistics and analysis data

The resources integrate with existing analyzer components to provide
seamless access to code analysis functionality through the MCP protocol.
"""

# Export main resource classes
from .code_file_resource import CodeFileResource
from .project_stats_resource import ProjectStatsResource

# Resource metadata
__author__ = "Tree-Sitter Analyzer Team"

# MCP Resource capabilities
MCP_RESOURCE_CAPABILITIES = {
    "version": "2024-11-05",
    "resources": [
        {
            "name": "code_file",
            "description": "Access to code file content",
            "uri_template": "code://file/{file_path}",
            "mime_type": "text/plain",
        },
        {
            "name": "project_stats",
            "description": "Access to project statistics and analysis data",
            "uri_template": "code://stats/{stats_type}",
            "mime_type": "application/json",
        },
    ],
}

__all__ = ["CodeFileResource", "ProjectStatsResource", "MCP_RESOURCE_CAPABILITIES"]
