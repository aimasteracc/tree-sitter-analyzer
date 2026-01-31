#!/usr/bin/env python3
"""
MCP Resources.

Resource implementations for Model Context Protocol.

Version: 1.10.5
Date: 2026-01-28
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .code_file_resource import CodeFileResource
    from .project_stats_resource import ProjectStatsResource
else:
    try:
        from .code_file_resource import CodeFileResource
        from .project_stats_resource import ProjectStatsResource
    except ImportError as e:
        import logging

        logging.warning(f"Import fallback triggered in mcp.resources: {e}")

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
