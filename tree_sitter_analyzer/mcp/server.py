#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP Server implementation for Tree-sitter Analyzer (Fixed Version)

This module provides the main MCP server that exposes tree-sitter analyzer
functionality through the Model Context Protocol.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        EmbeddedResource,
        ImageContent,
        Resource,
        TextContent,
        Tool,
    )

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

    # Fallback types for development without MCP
    class FallbackServer:
        pass

    class FallbackInitializationOptions:
        pass


from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine
from ..core.analysis_engine import get_analysis_engine, AnalysisRequest
from ..language_detector import detect_language_from_file
from ..utils import setup_logger
from . import MCP_INFO
from .resources import CodeFileResource, ProjectStatsResource
from .tools.base_tool import MCPTool
from .tools.read_partial_tool import ReadPartialTool
from .tools.table_format_tool import TableFormatTool
from .tools.universal_analyze_tool import UniversalAnalyzeTool
from .utils.error_handler import handle_mcp_errors
from .utils import get_performance_monitor

# Set up logging
logger = setup_logger(__name__)


class TreeSitterAnalyzerMCPServer:
    """
    MCP Server for Tree-sitter Analyzer

    Provides code analysis capabilities through the Model Context Protocol,
    integrating with existing analyzer components.
    """

    def __init__(self) -> None:
        """Initialize the MCP server with analyzer components."""
        self.server: Optional[Server] = None
        self.analysis_engine = get_analysis_engine()
        # Use unified analysis engine instead of deprecated AdvancedAnalyzer

        # Initialize MCP tools
        self.read_partial_tool: MCPTool = ReadPartialTool()
        self.universal_analyze_tool: MCPTool = UniversalAnalyzeTool()
        self.table_format_tool: MCPTool = TableFormatTool()

        # Initialize MCP resources
        self.code_file_resource = CodeFileResource()
        self.project_stats_resource = ProjectStatsResource()

        # Server metadata
        self.name = MCP_INFO["name"]
        self.version = MCP_INFO["version"]

        logger.info(f"Initializing {self.name} v{self.version}")

    @handle_mcp_errors("analyze_code_scale")
    async def _analyze_code_scale(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze code scale and complexity metrics by delegating to the universal_analyze_tool.
        """
        # Delegate the execution to the already initialized tool
        return await self.universal_analyze_tool.execute(arguments)

    def create_server(self) -> Server:
        """
        Create and configure the MCP server.

        Returns:
            Configured MCP Server instance
        """
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP library not available. Please install mcp package.")

        server: Server = Server(self.name)

        # Register tools
        @server.list_tools()
        async def handle_list_tools() -> List[Tool]:
            """List available tools."""
            tools = [
                Tool(
                    name="analyze_code_scale",
                    description="Analyze code scale, complexity, and structure metrics",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the code file to analyze",
                            },
                            "language": {
                                "type": "string",
                                "description": "Programming language (optional, auto-detected if not specified)",
                            },
                            "include_complexity": {
                                "type": "boolean",
                                "description": "Include complexity metrics in the analysis",
                                "default": True,
                            },
                            "include_details": {
                                "type": "boolean",
                                "description": "Include detailed element information",
                                "default": False,
                            },
                        },
                        "required": ["file_path"],
                        "additionalProperties": False,
                    },
                )
            ]

            # Add tools from tool classes - FIXED VERSION
            for tool_instance in [
                self.read_partial_tool,
                self.table_format_tool,
                self.universal_analyze_tool,
            ]:
                tool_def = tool_instance.get_tool_definition()
                if isinstance(tool_def, dict):
                    # Convert dict to Tool object
                    tools.append(Tool(**tool_def))
                else:
                    # Already a Tool object
                    tools.append(tool_def)

            return tools

        @server.call_tool()
        async def handle_call_tool(
            name: str, arguments: Dict[str, Any]
        ) -> List[TextContent]:
            """Handle tool calls."""
            try:
                if name == "analyze_code_scale":
                    result = await self._analyze_code_scale(arguments)
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(result, indent=2, ensure_ascii=False),
                        )
                    ]
                elif name == "read_code_partial":
                    result = await self.read_partial_tool.execute(arguments)
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(result, indent=2, ensure_ascii=False),
                        )
                    ]
                elif name == "format_table":
                    result = await self.table_format_tool.execute(arguments)
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(result, indent=2, ensure_ascii=False),
                        )
                    ]
                elif name == "analyze_code_universal":
                    result = await self.universal_analyze_tool.execute(arguments)
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(result, indent=2, ensure_ascii=False),
                        )
                    ]
                else:
                    raise ValueError(f"Unknown tool: {name}")

            except Exception as e:
                try:
                    logger.error(f"Tool call error for {name}: {e}")
                except (ValueError, OSError):
                    pass  # Silently ignore logging errors during shutdown
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {"error": str(e), "tool": name, "arguments": arguments},
                            indent=2,
                        ),
                    )
                ]

        # Register resources
        @server.list_resources()
        async def handle_list_resources() -> List[Resource]:
            """List available resources."""
            return [
                Resource(
                    uri=self.code_file_resource.get_resource_info()["uri_template"],
                    name=self.code_file_resource.get_resource_info()["name"],
                    description=self.code_file_resource.get_resource_info()[
                        "description"
                    ],
                    mimeType=self.code_file_resource.get_resource_info()["mime_type"],
                ),
                Resource(
                    uri=self.project_stats_resource.get_resource_info()["uri_template"],
                    name=self.project_stats_resource.get_resource_info()["name"],
                    description=self.project_stats_resource.get_resource_info()[
                        "description"
                    ],
                    mimeType=self.project_stats_resource.get_resource_info()[
                        "mime_type"
                    ],
                ),
            ]

        @server.read_resource()
        async def handle_read_resource(uri: str) -> str:
            """Read resource content."""
            try:
                # Check which resource matches the URI
                if self.code_file_resource.matches_uri(uri):
                    return await self.code_file_resource.read_resource(uri)
                elif self.project_stats_resource.matches_uri(uri):
                    return await self.project_stats_resource.read_resource(uri)
                else:
                    raise ValueError(f"Resource not found: {uri}")

            except Exception as e:
                try:
                    logger.error(f"Resource read error for {uri}: {e}")
                except (ValueError, OSError):
                    pass  # Silently ignore logging errors during shutdown
                raise

        self.server = server
        try:
            logger.info("MCP server created successfully")
        except (ValueError, OSError):
            pass  # Silently ignore logging errors during shutdown
        return server

    def set_project_path(self, project_path: str) -> None:
        """
        Set the project path for statistics resource

        Args:
            project_path: Path to the project directory
        """
        self.project_stats_resource.set_project_path(project_path)
        try:
            logger.info(f"Set project path to: {project_path}")
        except (ValueError, OSError):
            pass  # Silently ignore logging errors during shutdown

    async def run(self) -> None:
        """
        Run the MCP server.

        This method starts the server and handles stdio communication.
        """
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP library not available. Please install mcp package.")

        server = self.create_server()

        # Initialize server options
        options = InitializationOptions(
            server_name=self.name,
            server_version=self.version,
            capabilities=MCP_INFO["capabilities"],
        )

        try:
            logger.info(f"Starting MCP server: {self.name} v{self.version}")
        except (ValueError, OSError):
            pass  # Silently ignore logging errors during shutdown

        try:
            async with stdio_server() as (read_stream, write_stream):
                await server.run(read_stream, write_stream, options)
        except Exception as e:
            # Use safe logging to avoid I/O errors during shutdown
            try:
                logger.error(f"Server error: {e}")
            except (ValueError, OSError):
                pass  # Silently ignore logging errors during shutdown
            raise
        finally:
            # Safe cleanup
            try:
                logger.info("MCP server shutting down")
            except (ValueError, OSError):
                pass  # Silently ignore logging errors during shutdown


async def main() -> None:
    """Main entry point for the MCP server."""
    try:
        server = TreeSitterAnalyzerMCPServer()
        await server.run()
    except KeyboardInterrupt:
        try:
            logger.info("Server stopped by user")
        except (ValueError, OSError):
            pass  # Silently ignore logging errors during shutdown
    except Exception as e:
        try:
            logger.error(f"Server failed: {e}")
        except (ValueError, OSError):
            pass  # Silently ignore logging errors during shutdown
        sys.exit(1)
    finally:
        # Ensure clean shutdown
        try:
            logger.info("MCP server shutdown complete")
        except (ValueError, OSError):
            pass  # Silently ignore logging errors during shutdown


if __name__ == "__main__":
    asyncio.run(main())
