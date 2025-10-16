#!/usr/bin/env python3
"""
MCP Server Interface

New MCP server implementation that uses the API facade for all operations.
Provides a clean separation between MCP protocol concerns and core analysis logic.
"""

import asyncio
import json
import logging
import sys
from typing import Any

from .. import __version__

try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Resource, TextContent, Tool

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

    # Fallback types for development without MCP
    class Server:
        pass

    class InitializationOptions:
        def __init__(self, **kwargs: Any) -> None:
            pass

    class Tool:
        pass

    class Resource:
        pass

    class TextContent:
        pass

    def stdio_server() -> None:
        pass


from .. import api
from ..utils import log_error, log_info

# Configure logging for MCP
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class TreeSitterAnalyzerMCPServer:
    """
    MCP Server for Tree-sitter Analyzer using the new API facade.

    This server provides code analysis capabilities through the Model Context Protocol,
    using the unified API facade for all operations.
    """

    def __init__(self) -> None:
        """Initialize the MCP server."""
        if not MCP_AVAILABLE:
            raise ImportError("MCP library not available. Please install mcp package.")

        self.server: Server | None = None
        self.name = "tree-sitter-analyzer"
        self.version = __version__

        log_info(f"Initializing {self.name} v{self.version}")

    def create_server(self) -> Server:
        """Create and configure the MCP server."""
        server: Any = Server(self.name)

        @server.list_tools()  # type: ignore
        async def handle_list_tools() -> list[Tool]:
            """List available tools."""
            return [
                Tool(
                    name="analyze_file",
                    description="Analyze a source code file comprehensively",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the source file to analyze",
                            },
                            "language": {
                                "type": "string",
                                "description": "Programming language (optional, auto-detected if not specified)",
                            },
                            "queries": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of query names to execute (optional)",
                            },
                            "include_elements": {
                                "type": "boolean",
                                "description": "Whether to extract code elements",
                                "default": True,
                            },
                            "include_queries": {
                                "type": "boolean",
                                "description": "Whether to execute queries",
                                "default": True,
                            },
                        },
                        "required": ["file_path"],
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="analyze_code",
                    description="Analyze source code directly (without file)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "source_code": {
                                "type": "string",
                                "description": "Source code string to analyze",
                            },
                            "language": {
                                "type": "string",
                                "description": "Programming language",
                            },
                            "queries": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of query names to execute (optional)",
                            },
                            "include_elements": {
                                "type": "boolean",
                                "description": "Whether to extract code elements",
                                "default": True,
                            },
                            "include_queries": {
                                "type": "boolean",
                                "description": "Whether to execute queries",
                                "default": True,
                            },
                        },
                        "required": ["source_code", "language"],
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="extract_elements",
                    description="Extract code elements from a file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the source file",
                            },
                            "language": {
                                "type": "string",
                                "description": "Programming language (optional, auto-detected if not specified)",
                            },
                            "element_types": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Types of elements to extract (optional)",
                            },
                        },
                        "required": ["file_path"],
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="execute_query",
                    description="Execute a specific query on a file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the source file",
                            },
                            "query_name": {
                                "type": "string",
                                "description": "Name of the query to execute",
                            },
                            "language": {
                                "type": "string",
                                "description": "Programming language (optional, auto-detected if not specified)",
                            },
                        },
                        "required": ["file_path", "query_name"],
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="validate_file",
                    description="Validate a source code file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the source file to validate",
                            }
                        },
                        "required": ["file_path"],
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="get_supported_languages",
                    description="Get list of supported programming languages",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="get_available_queries",
                    description="Get available queries for a specific language",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "language": {
                                "type": "string",
                                "description": "Programming language name",
                            }
                        },
                        "required": ["language"],
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="get_framework_info",
                    description="Get information about the analyzer framework",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                ),
            ]

        @server.call_tool()  # type: ignore
        async def handle_call_tool(
            name: str, arguments: dict[str, Any]
        ) -> list[TextContent]:
            """Handle tool calls."""
            try:
                result = None

                if name == "analyze_file":
                    result = api.analyze_file(
                        file_path=arguments["file_path"],
                        language=arguments.get("language"),
                        queries=arguments.get("queries"),
                        include_elements=arguments.get("include_elements", True),
                        include_queries=arguments.get("include_queries", True),
                    )

                elif name == "analyze_code":
                    result = api.analyze_code(
                        source_code=arguments["source_code"],
                        language=arguments["language"],
                        queries=arguments.get("queries"),
                        include_elements=arguments.get("include_elements", True),
                        include_queries=arguments.get("include_queries", True),
                    )

                elif name == "extract_elements":
                    result = api.extract_elements(
                        file_path=arguments["file_path"],
                        language=arguments.get("language"),
                        element_types=arguments.get("element_types"),
                    )

                elif name == "execute_query":
                    result = api.execute_query(
                        file_path=arguments["file_path"],
                        query_name=arguments["query_name"],
                        language=arguments.get("language"),
                    )

                elif name == "validate_file":
                    result = api.validate_file(arguments["file_path"])

                elif name == "get_supported_languages":
                    result = {
                        "languages": api.get_supported_languages(),
                        "total": len(api.get_supported_languages()),
                    }

                elif name == "get_available_queries":
                    queries = api.get_available_queries(arguments["language"])
                    result = {
                        "language": arguments["language"],
                        "queries": queries,
                        "total": len(queries),
                    }

                elif name == "get_framework_info":
                    result = api.get_framework_info()

                else:
                    raise ValueError(f"Unknown tool: {name}")

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, ensure_ascii=False),
                    )
                ]

            except Exception as e:
                log_error(f"Tool call error for {name}: {e}")
                error_result = {
                    "error": str(e),
                    "tool": name,
                    "arguments": arguments,
                    "success": False,
                }
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(error_result, indent=2, ensure_ascii=False),
                    )
                ]

        @server.list_resources()  # type: ignore
        async def handle_list_resources() -> list[Resource]:
            """List available resources."""
            return [
                Resource(
                    uri="code://file/{file_path}",  # type: ignore
                    name="Code File Analysis",
                    description="Access to code file content and analysis",
                    mimeType="application/json",
                ),
                Resource(
                    uri="code://stats/{stats_type}",  # type: ignore
                    name="Project Statistics",
                    description="Access to project statistics and analysis data",
                    mimeType="application/json",
                ),
            ]

        @server.read_resource()  # type: ignore
        async def handle_read_resource(uri: str) -> str:
            """Read resource content."""
            try:
                if uri.startswith("code://file/"):
                    # Extract file path from URI
                    file_path = uri[len("code://file/") :]

                    # Analyze the file
                    result = api.analyze_file(file_path)
                    return json.dumps(result, indent=2, ensure_ascii=False)

                elif uri.startswith("code://stats/"):
                    # Extract stats type from URI
                    stats_type = uri[len("code://stats/") :]

                    # Get framework info as basic stats
                    if stats_type == "framework":
                        result = api.get_framework_info()
                    elif stats_type == "languages":
                        result = {
                            "supported_languages": api.get_supported_languages(),
                            "total_languages": len(api.get_supported_languages()),
                        }
                    else:
                        raise ValueError(f"Unknown stats type: {stats_type}")

                    return json.dumps(result, indent=2, ensure_ascii=False)

                else:
                    raise ValueError(f"Resource not found: {uri}")

            except Exception as e:
                log_error(f"Resource read error for {uri}: {e}")
                error_result = {"error": str(e), "uri": uri, "success": False}
                return json.dumps(error_result, indent=2, ensure_ascii=False)

        self.server = server
        log_info("MCP server created successfully")
        return server  # type: ignore

    async def run(self) -> None:
        """Run the MCP server."""
        server = self.create_server()

        # Initialize server options
        options = InitializationOptions(
            server_name=self.name,
            server_version=self.version,
            capabilities={"tools": {}, "resources": {}},  # type: ignore
        )

        log_info(f"Starting MCP server: {self.name} v{self.version}")

        try:
            async with stdio_server() as (read_stream, write_stream):
                await server.run(read_stream, write_stream, options)
        except Exception as e:
            log_error(f"Server error: {e}")
            raise


async def main() -> None:
    """Main entry point for the MCP server."""
    try:
        server = TreeSitterAnalyzerMCPServer()
        await server.run()
    except KeyboardInterrupt:
        log_info("Server stopped by user")
    except Exception as e:
        log_error(f"Server failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
