#!/usr/bin/env python3
"""
MCP Server implementation for Tree-sitter Analyzer (Fixed Version)

This module provides the main MCP server that exposes tree-sitter analyzer
functionality through the Model Context Protocol.
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Any

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
        def __init__(self, **kwargs):
            pass

    class Tool:
        pass

    class Resource:
        pass

    class TextContent:
        pass

    def stdio_server():
        pass


from ..core.analysis_engine import get_analysis_engine
from ..project_detector import detect_project_root
from ..security import SecurityValidator
from ..utils import setup_logger
from . import MCP_INFO
from .resources import CodeFileResource, ProjectStatsResource
from .tools.base_tool import MCPTool
from .tools.read_partial_tool import ReadPartialTool
from .tools.table_format_tool import TableFormatTool
from .utils.error_handler import handle_mcp_errors

# Set up logging
logger = setup_logger(__name__)


class TreeSitterAnalyzerMCPServer:
    """
    MCP Server for Tree-sitter Analyzer

    Provides code analysis capabilities through the Model Context Protocol,
    integrating with existing analyzer components.
    """

    def __init__(self, project_root: str = None) -> None:
        """Initialize the MCP server with analyzer components."""
        self.server: Server | None = None
        self._initialization_complete = False

        logger.info("Starting MCP server initialization...")

        self.analysis_engine = get_analysis_engine(project_root)
        self.security_validator = SecurityValidator(project_root)
        # Use unified analysis engine instead of deprecated AdvancedAnalyzer

        # Initialize MCP tools with security validation (three core tools)
        self.read_partial_tool: MCPTool = ReadPartialTool(project_root)  # extract_code_section
        self.table_format_tool: MCPTool = TableFormatTool(project_root)  # analyze_code_structure

        # Initialize MCP resources
        self.code_file_resource = CodeFileResource()
        self.project_stats_resource = ProjectStatsResource()

        # Server metadata
        self.name = MCP_INFO["name"]
        self.version = MCP_INFO["version"]

        self._initialization_complete = True
        logger.info(f"MCP server initialization complete: {self.name} v{self.version}")

    def is_initialized(self) -> bool:
        """Check if the server is fully initialized."""
        return self._initialization_complete

    def _ensure_initialized(self) -> None:
        """Ensure the server is initialized before processing requests."""
        if not self._initialization_complete:
            raise RuntimeError("Server not fully initialized. Please wait for initialization to complete.")

    @handle_mcp_errors("check_code_scale")
    async def _analyze_code_scale(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Analyze code scale and complexity metrics using the analysis engine directly.
        """
        self._ensure_initialized()

        # Validate required arguments
        if "file_path" not in arguments:
            raise ValueError("file_path is required")

        file_path = arguments["file_path"]
        language = arguments.get("language")
        include_complexity = arguments.get("include_complexity", True)
        include_details = arguments.get("include_details", False)

        # Security validation
        is_valid, error_msg = self.security_validator.validate_file_path(file_path)
        if not is_valid:
            raise ValueError(f"Invalid file path: {error_msg}")

        # Use analysis engine directly
        from ..core.analysis_engine import AnalysisRequest
        from ..language_detector import detect_language_from_file
        from pathlib import Path

        # Validate file exists
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Detect language if not specified
        if not language:
            language = detect_language_from_file(file_path)

        # Create analysis request
        request = AnalysisRequest(
            file_path=file_path,
            language=language,
            include_complexity=include_complexity,
            include_details=include_details,
        )

        # Perform analysis
        analysis_result = await self.analysis_engine.analyze(request)

        if analysis_result is None or not analysis_result.success:
            error_msg = analysis_result.error_message if analysis_result else "Unknown error"
            raise RuntimeError(f"Failed to analyze file: {file_path} - {error_msg}")

        # Convert to dictionary format
        result_dict = analysis_result.to_dict()

        # Format result to match test expectations
        elements = result_dict.get("elements", [])

        # Count elements by type
        classes_count = len([e for e in elements if e.get("__class__") == "Class"])
        methods_count = len([e for e in elements if e.get("__class__") == "Function"])
        fields_count = len([e for e in elements if e.get("__class__") == "Variable"])
        imports_count = len([e for e in elements if e.get("__class__") == "Import"])

        result = {
            "file_path": file_path,
            "language": language,
            "metrics": {
                "lines_total": result_dict.get("line_count", 0),
                "lines_code": result_dict.get("line_count", 0),  # Approximation
                "lines_comment": 0,  # Not available in basic analysis
                "lines_blank": 0,    # Not available in basic analysis
                "elements": {
                    "classes": classes_count,
                    "methods": methods_count,
                    "fields": fields_count,
                    "imports": imports_count,
                    "total": len(elements),
                }
            }
        }

        if include_complexity:
            # Add complexity metrics if available
            methods = [e for e in elements if e.get("__class__") == "Function"]
            if methods:
                complexities = [e.get("complexity_score", 0) for e in methods]
                result["metrics"]["complexity"] = {
                    "total": sum(complexities),
                    "average": sum(complexities) / len(complexities) if complexities else 0,
                    "max": max(complexities) if complexities else 0,
                }

        if include_details:
            result["detailed_elements"] = elements

        return result

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
        @server.list_tools()  # type: ignore
        async def handle_list_tools() -> list[Tool]:
            """
            List available tools with clear naming and usage guidance.

            🎯 SOLVE LLM TOKEN LIMIT PROBLEMS FOR LARGE CODE FILES

            REQUIRED WORKFLOW FOR LLM (follow this order):
            1. FIRST: 'check_code_scale' - understand file size and complexity
            2. SECOND: 'analyze_code_structure' - get detailed structure with line positions
            3. THIRD: 'extract_code_section' - get specific code from line positions

            ⚠️  PARAMETER NAMES: Use snake_case (file_path, start_line, end_line, format_type)
            📖 Full guide: See README.md AI Assistant Integration section
            """
            tools = [
                Tool(
                    name="check_code_scale",
                    description="🔍 STEP 1: Check code file scale, complexity, and basic metrics. Use this FIRST to understand if the file is large and needs structure analysis. Returns: line count, element counts, complexity metrics.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the code file to analyze (REQUIRED - use exact file path)",
                            },
                            "language": {
                                "type": "string",
                                "description": "Programming language (optional, auto-detected if not specified)",
                            },
                            "include_complexity": {
                                "type": "boolean",
                                "description": "Include complexity metrics in the analysis (default: true)",
                                "default": True,
                            },
                            "include_details": {
                                "type": "boolean",
                                "description": "Include detailed element information (default: false)",
                                "default": False,
                            },
                        },
                        "required": ["file_path"],
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="analyze_code_structure",
                    description="📊 STEP 2: Generate detailed structure tables (classes, methods, fields) with LINE POSITIONS for large files. Use AFTER check_code_scale shows file is large (>100 lines). Returns: tables with start_line/end_line for each element.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the code file to analyze (REQUIRED - use exact file path)",
                            },
                            "format_type": {
                                "type": "string",
                                "description": "Table format type (default: 'full' for detailed tables)",
                                "enum": ["full", "compact", "csv"],
                                "default": "full",
                            },
                            "language": {
                                "type": "string",
                                "description": "Programming language (optional, auto-detected if not specified)",
                            },
                        },
                        "required": ["file_path"],
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="extract_code_section",
                    description="✂️ STEP 3: Extract specific code sections by line range. Use AFTER analyze_code_structure to get exact code from structure table line positions. Returns: precise code content without reading entire file.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the code file to read (REQUIRED - use exact file path)",
                            },
                            "start_line": {
                                "type": "integer",
                                "description": "Starting line number (REQUIRED - 1-based, get from structure table)",
                                "minimum": 1,
                            },
                            "end_line": {
                                "type": "integer",
                                "description": "Ending line number (optional - 1-based, reads to end if not specified)",
                                "minimum": 1,
                            },
                            "start_column": {
                                "type": "integer",
                                "description": "Starting column number (optional - 0-based)",
                                "minimum": 0,
                            },
                            "end_column": {
                                "type": "integer",
                                "description": "Ending column number (optional - 0-based)",
                                "minimum": 0,
                            },
                            "format": {
                                "type": "string",
                                "description": "Output format for the content (default: 'text')",
                                "enum": ["text", "json"],
                                "default": "text",
                            },
                        },
                        "required": ["file_path", "start_line"],
                        "additionalProperties": False,
                    },
                ),
            ]

            return tools

        @server.call_tool()  # type: ignore
        async def handle_call_tool(
            name: str, arguments: dict[str, Any]
        ) -> list[TextContent]:
            """Handle tool calls with security validation."""
            try:
                # Ensure server is fully initialized
                self._ensure_initialized()

                # Security validation for tool name
                sanitized_name = self.security_validator.sanitize_input(name, max_length=100)

                # Log tool call for audit
                logger.info(f"MCP tool call: {sanitized_name} with args: {list(arguments.keys())}")

                # Validate arguments contain no malicious content
                for key, value in arguments.items():
                    if isinstance(value, str):
                        # Check for potential injection attempts
                        if len(value) > 10000:  # Prevent extremely large inputs
                            raise ValueError(f"Input too large for parameter {key}")

                        # Basic sanitization for string inputs
                        sanitized_value = self.security_validator.sanitize_input(value, max_length=10000)
                        arguments[key] = sanitized_value

                # Handle tool calls with unified naming (only new names)
                if sanitized_name == "check_code_scale":
                    result = await self._analyze_code_scale(arguments)
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(result, indent=2, ensure_ascii=False),
                        )
                    ]
                elif sanitized_name == "analyze_code_structure":
                    result = await self.table_format_tool.execute(arguments)
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(result, indent=2, ensure_ascii=False),
                        )
                    ]
                elif sanitized_name == "extract_code_section":
                    result = await self.read_partial_tool.execute(arguments)
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(result, indent=2, ensure_ascii=False),
                        )
                    ]
                else:
                    raise ValueError(f"Unknown tool: {name}. Available tools: check_code_scale, analyze_code_structure, extract_code_section")

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
        @server.list_resources()  # type: ignore
        async def handle_list_resources() -> list[Resource]:
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

        @server.read_resource()  # type: ignore
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


def parse_mcp_args(args=None) -> argparse.Namespace:
    """Parse command line arguments for MCP server."""
    parser = argparse.ArgumentParser(
        description="Tree-sitter Analyzer MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  TREE_SITTER_PROJECT_ROOT    Project root directory (alternative to --project-root)

Examples:
  python -m tree_sitter_analyzer.mcp.server
  python -m tree_sitter_analyzer.mcp.server --project-root /path/to/project
        """
    )

    parser.add_argument(
        "--project-root",
        help="Project root directory for security validation (auto-detected if not specified)"
    )

    return parser.parse_args(args)


async def main() -> None:
    """Main entry point for the MCP server."""
    try:
        # Parse command line arguments (empty list for testing)
        args = parse_mcp_args([])

        # Determine project root with priority handling
        project_root = None

        # Priority 1: Command line argument
        if args.project_root:
            project_root = args.project_root
        # Priority 2: Environment variable
        elif os.getenv('TREE_SITTER_PROJECT_ROOT'):
            project_root = os.getenv('TREE_SITTER_PROJECT_ROOT')
        # Priority 3: Auto-detection from current directory
        else:
            project_root = detect_project_root()

        logger.info(f"MCP server starting with project root: {project_root}")

        server = TreeSitterAnalyzerMCPServer(project_root)
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
