#!/usr/bin/env python3
"""
MCP Server implementation for Tree-sitter Analyzer (Refactored)

This module provides the main MCP server that exposes tree-sitter analyzer
functionality through the Model Context Protocol.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path as PathClass
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp.server.stdio import stdio_server as _stdio_server

    stdio_server: Any = _stdio_server
    from mcp.types import Prompt, Resource, TextContent, Tool

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

    # Fallback types for development without MCP
    class Server:  # type: ignore
        def __init__(self, name: str) -> None:
            pass

        def list_tools(self) -> Any:
            return lambda f: f

        def call_tool(self) -> Any:
            return lambda f: f

        def list_resources(self) -> Any:
            return lambda f: f

        def read_resource(self) -> Any:
            return lambda f: f

        def list_prompts(self) -> Any:
            return lambda f: f

        async def run(self, read: Any, write: Any, opts: Any) -> None:
            pass

    class InitializationOptions:  # type: ignore
        def __init__(self, **kwargs: Any) -> None:
            pass

    class Tool:  # type: ignore
        def __init__(self, **kwargs: Any) -> None:
            pass

    class Resource:  # type: ignore
        def __init__(self, **kwargs: Any) -> None:
            pass

    class TextContent:  # type: ignore
        pass

    class Prompt:  # type: ignore
        pass

    pass

    def _fallback_stdio_server() -> Any:
        pass

    stdio_server = _fallback_stdio_server


import contextlib

from ..core.analysis_engine import get_analysis_engine
from ..platform_compat.detector import PlatformDetector
from ..project_detector import detect_project_root
from ..security import SecurityValidator
from ..utils import setup_logger
from . import MCP_INFO
from .handler_resources import ResourceHandler

# Handler imports
from .handler_tools import ToolHandler
from .legacy import LegacyHandler
from .resources import CodeFileResource, ProjectStatsResource
from .tools.analyze_code_structure_tool import AnalyzeCodeStructureTool
from .tools.analyze_scale_tool import AnalyzeScaleTool
from .tools.find_and_grep_tool import FindAndGrepTool
from .tools.list_files_tool import ListFilesTool
from .tools.query_tool import QueryTool
from .tools.read_partial_tool import ReadPartialTool
from .tools.search_content_tool import SearchContentTool
from .utils.file_metrics import compute_file_metrics

# Import UniversalAnalyzeTool at module level for test compatibility
try:
    from .tools.universal_analyze_tool import UniversalAnalyzeTool

    UNIVERSAL_TOOL_AVAILABLE = True
except ImportError:
    UniversalAnalyzeTool = None  # type: ignore
    UNIVERSAL_TOOL_AVAILABLE = False

# Set up logging
logger = setup_logger(__name__)


class TreeSitterAnalyzerMCPServer:
    """
    MCP Server for Tree-sitter Analyzer

    Provides code analysis capabilities through the Model Context Protocol,
    integrating with existing analyzer components.
    """

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize the MCP server with analyzer components."""
        self.server: Server | None = None
        self._initialization_complete = False

        try:
            logger.info("Starting MCP server initialization...")
        except Exception:  # nosec
            pass

        self.analysis_engine = get_analysis_engine(project_root)
        self.security_validator = SecurityValidator(project_root)

        # Initialize MCP tools with security validation (core tools + fd/rg tools)
        self.query_tool = QueryTool(project_root)
        self.read_partial_tool = ReadPartialTool(project_root)
        self.analyze_code_structure_tool = AnalyzeCodeStructureTool(project_root)
        self.table_format_tool = self.analyze_code_structure_tool
        self.analyze_scale_tool = AnalyzeScaleTool(project_root)
        self.list_files_tool = ListFilesTool(project_root)
        self.search_content_tool = SearchContentTool(project_root)
        self.find_and_grep_tool = FindAndGrepTool(project_root)

        # Optional universal tool to satisfy initialization tests
        if UNIVERSAL_TOOL_AVAILABLE and UniversalAnalyzeTool is not None:
            try:
                self.universal_analyze_tool: UniversalAnalyzeTool | None = (
                    UniversalAnalyzeTool(project_root)
                )
            except Exception:
                self.universal_analyze_tool = None
        else:
            self.universal_analyze_tool = None

        # Initialize MCP resources
        self.code_file_resource = CodeFileResource()
        self.project_stats_resource = ProjectStatsResource()
        self.project_stats_resource.project_root = project_root

        # Initialize Handlers
        self.tool_handler = ToolHandler(self)
        self.resource_handler = ResourceHandler(self)
        self.legacy_handler = LegacyHandler(self)

        # Server metadata
        self.name = MCP_INFO["name"]
        self.version = MCP_INFO["version"]

        # Add platform info to version for better diagnostics
        try:
            platform_info = PlatformDetector.detect()
            self.version = f"{self.version} ({platform_info.platform_key})"
            try:
                logger.info(f"Running on platform: {platform_info}")
            except Exception:  # nosec
                pass
        except Exception as e:
            try:
                logger.warning(f"Failed to detect platform: {e}")
            except Exception:  # nosec
                pass

        self._initialization_complete = True
        try:
            logger.info(
                f"MCP server initialization complete: {self.name} v{self.version}"
            )
        except Exception:  # nosec
            pass

    def is_initialized(self) -> bool:
        """Check if the server is fully initialized."""
        return self._initialization_complete

    def _ensure_initialized(self) -> None:
        """Ensure the server is initialized before processing requests."""
        if not self._initialization_complete:
            raise RuntimeError(
                "Server not fully initialized. Please wait for initialization to complete."
            )

    async def _analyze_code_scale(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Legacy method delegated to LegacyHandler."""
        return await self.legacy_handler.analyze_code_scale(arguments)

    def _calculate_file_metrics(self, file_path: str, language: str) -> dict[str, Any]:
        """Legacy wrapper for file metrics calculation."""
        base_root = getattr(
            getattr(self.security_validator, "boundary_manager", None),
            "project_root",
            None,
        )
        return compute_file_metrics(
            file_path, language=language, project_root=base_root
        )

    async def _read_resource(self, uri: str) -> dict[str, Any]:
        """Legacy wrapper for read_resource."""
        return {"content": await self.resource_handler.read_resource(uri)}

    def create_server(self) -> Server:
        """
        Create and configure the MCP server.

        Returns:
            Configured MCP Server instance
        """
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP library not available. Please install mcp package.")

        server: Server = Server(self.name)

        @server.list_tools()  # type: ignore[misc]
        async def handle_list_tools() -> list[Tool]:
            """List all available tools."""
            logger.info("Client requesting tools list")

            tools = [
                Tool(**self.analyze_scale_tool.get_tool_definition()),
                Tool(**self.analyze_code_structure_tool.get_tool_definition()),
                Tool(**self.read_partial_tool.get_tool_definition()),
                Tool(
                    name="set_project_path",
                    description="Set or override the project root path used for security boundaries",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_path": {
                                "type": "string",
                                "description": "Absolute path to the project root",
                            }
                        },
                        "required": ["project_path"],
                        "additionalProperties": False,
                    },
                ),
                Tool(**self.query_tool.get_tool_definition()),
                Tool(**self.list_files_tool.get_tool_definition()),
                Tool(**self.search_content_tool.get_tool_definition()),
                Tool(**self.find_and_grep_tool.get_tool_definition()),
            ]

            logger.info(f"Returning {len(tools)} tools: {[t.name for t in tools]}")
            return tools

        @server.call_tool()  # type: ignore[misc]
        async def handle_call_tool(
            name: str, arguments: dict[str, Any]
        ) -> list[TextContent]:
            """Delegate to ToolHandler."""
            return await self.tool_handler.handle_tool_call(name, arguments)

        @server.list_resources()  # type: ignore
        async def handle_list_resources() -> list[Resource]:
            """Delegate to ResourceHandler."""
            return await self.resource_handler.list_resources()

        @server.read_resource()  # type: ignore
        async def handle_read_resource(uri: str) -> str:
            """Delegate to ResourceHandler."""
            return await self.resource_handler.read_resource(uri)

        # Handle prompts capability (empty for now)
        try:

            @server.list_prompts()  # type: ignore
            async def handle_list_prompts() -> list[Prompt]:
                logger.info("Client requested prompts list (returning empty)")
                return []
        except Exception as e:
            with contextlib.suppress(ValueError, OSError):
                logger.debug(f"Prompts API unavailable or incompatible: {e}")

        self.server = server
        try:
            logger.info("MCP server created successfully")
        except (ValueError, OSError):
            pass
        return server

    def set_project_path(self, project_path: str) -> None:
        """
        Set the project path for all components

        Args:
            project_path: Path to the project directory
        """
        # Invalidate shared caches once when the project root changes.
        from .utils.shared_cache import get_shared_cache

        get_shared_cache().clear()

        # Update project stats resource
        self.project_stats_resource.set_project_path(project_path)

        # Update all MCP tools (all inherit from BaseMCPTool)
        self.query_tool.set_project_path(project_path)
        self.read_partial_tool.set_project_path(project_path)
        self.analyze_code_structure_tool.set_project_path(project_path)
        self.analyze_scale_tool.set_project_path(project_path)
        self.list_files_tool.set_project_path(project_path)
        self.search_content_tool.set_project_path(project_path)
        self.find_and_grep_tool.set_project_path(project_path)

        # Update universal tool if available
        if hasattr(self, "universal_analyze_tool") and self.universal_analyze_tool:
            self.universal_analyze_tool.set_project_path(project_path)

        # Update analysis engine and security validator
        self.analysis_engine = get_analysis_engine(project_path)
        self.security_validator = SecurityValidator(project_path)

        try:
            logger.info(f"Set project path to: {project_path}")
        except (ValueError, OSError):
            pass

    async def run(self) -> None:
        """
        Run the MCP server.

        This method starts the server and handles stdio communication.
        """
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP library not available. Please install mcp package.")

        server = self.create_server()

        # Initialize server options with required capabilities field
        from mcp.server.models import ServerCapabilities
        from mcp.types import (
            LoggingCapability,
            PromptsCapability,
            ResourcesCapability,
            ToolsCapability,
        )

        capabilities = ServerCapabilities(
            tools=ToolsCapability(listChanged=True),
            resources=ResourcesCapability(subscribe=True, listChanged=True),
            prompts=PromptsCapability(listChanged=True),
            logging=LoggingCapability(),
        )

        options = InitializationOptions(
            server_name=self.name,
            server_version=self.version,
            capabilities=capabilities,
        )

        try:
            logger.info(f"Starting MCP server: {self.name} v{self.version}")
        except (ValueError, OSError):
            pass

        try:
            async with stdio_server() as (read_stream, write_stream):
                logger.info("Server running, waiting for requests...")
                await server.run(read_stream, write_stream, options)
        except Exception as e:
            try:
                logger.error(f"Server error: {e}")
            except (ValueError, OSError):
                pass
            raise
        finally:
            try:
                logger.info("MCP server shutting down")
            except (ValueError, OSError):
                pass


def parse_mcp_args(args: list[str] | None = None) -> argparse.Namespace:
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
        """,
    )

    parser.add_argument(
        "--project-root",
        help="Project root directory for security validation (auto-detected if not specified)",
    )

    return parser.parse_args(args)


async def main() -> None:
    """Main entry point for the MCP server."""
    try:
        # Parse command line arguments (ignore unknown so pytest flags won't crash)
        args = parse_mcp_args([] if "pytest" in sys.argv[0] else None)

        # Determine project root with robust priority handling and fallbacks
        project_root = None

        # Priority 1: Command line argument
        if args.project_root:
            project_root = args.project_root
        # Priority 2: Environment variable
        elif (
            PathClass.cwd()
            .joinpath(os.environ.get("TREE_SITTER_PROJECT_ROOT", ""))
            .exists()
        ):
            project_root = os.environ.get("TREE_SITTER_PROJECT_ROOT")
        # Priority 3: Auto-detection from current directory
        else:
            project_root = detect_project_root()

        # Handle unresolved placeholders from clients (e.g., "${workspaceFolder}")
        invalid_placeholder = isinstance(project_root, str) and (
            "${" in project_root or "}" in project_root or "$" in project_root
        )

        # Validate existence; if invalid, fall back to current working directory
        if (
            not project_root
            or invalid_placeholder
            or (isinstance(project_root, str) and not PathClass(project_root).is_dir())
        ):
            # Use current working directory as final fallback
            fallback_root = str(PathClass.cwd())
            with contextlib.suppress(ValueError, OSError):
                logger.warning(
                    f"Invalid project root '{project_root}', falling back to current directory: {fallback_root}"
                )
            project_root = fallback_root

        logger.info(f"MCP server starting with project root: {project_root}")

        server = TreeSitterAnalyzerMCPServer(project_root)
        await server.run()

        # Exit successfully after server run completes
        sys.exit(0)
    except KeyboardInterrupt:
        try:
            logger.info("Server stopped by user")
        except (ValueError, OSError):
            pass
        sys.exit(0)
    except Exception as e:
        try:
            logger.error(f"Server failed: {e}")
        except (ValueError, OSError):
            pass
        sys.exit(1)
    finally:
        # Ensure clean shutdown
        try:
            logger.info("MCP server shutdown complete")
        except (ValueError, OSError):
            pass


def main_sync() -> None:
    """Synchronous entry point for setuptools scripts."""
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
