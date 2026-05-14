#!/usr/bin/env python3
"""
MCP Server implementation for Tree-sitter Analyzer (Refactored)

This module provides the main MCP server that exposes tree-sitter analyzer
functionality through the Model Context Protocol.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path as PathClass
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp.server.stdio import stdio_server as _stdio_server

    stdio_server: Any = _stdio_server
    from mcp.types import Resource, TextContent, Tool

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

    # Fallback types for development without MCP
    class Server:  # type: ignore
        pass

    class InitializationOptions:  # type: ignore
        def __init__(self, **kwargs: Any) -> None:
            pass

    class Tool:  # type: ignore
        pass

    class Resource:  # type: ignore
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
from .resources import CodeFileResource, ProjectStatsResource
from .server_utils.code_scale_handler import analyze_code_scale
from .server_utils.error_recovery import build_agent_friendly_error
from .server_utils.smart_prompts import (
    build_smart_analyze_response,
    build_smart_explore_response,
)
from .tools.analyze_code_structure_tool import AnalyzeCodeStructureTool
from .tools.analyze_scale_tool import AnalyzeScaleTool
from .tools.dependency_analysis_tool import DependencyAnalysisTool
from .tools.file_health_tool import FileHealthTool
from .tools.find_and_grep_tool import FindAndGrepTool
from .tools.list_files_tool import ListFilesTool
from .tools.project_health_tool import ProjectHealthTool
from .tools.project_overview_tool import ProjectOverviewTool
from .tools.query_tool import QueryTool
from .tools.read_partial_tool import ReadPartialTool
from .tools.search_content_tool import SearchContentTool
from .utils.file_metrics import compute_file_metrics
from .utils.shared_cache import get_shared_cache

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

        # Tool registry: ordered list of (name, instance) pairs
        self._tool_instances: list[tuple[str, Any]] = [
            ("check_code_scale", AnalyzeScaleTool(project_root)),
            ("analyze_code_structure", AnalyzeCodeStructureTool(project_root)),
            ("extract_code_section", ReadPartialTool(project_root)),
            ("query_code", QueryTool(project_root)),
            ("list_files", ListFilesTool(project_root)),
            ("search_content", SearchContentTool(project_root)),
            ("find_and_grep", FindAndGrepTool(project_root)),
            ("get_project_overview", ProjectOverviewTool(project_root)),
            ("check_project_health", ProjectHealthTool(project_root)),
            ("check_file_health", FileHealthTool(project_root)),
            ("analyze_dependencies", DependencyAnalysisTool(project_root)),
        ]
        self._tools: dict[str, Any] = dict(self._tool_instances)

        # Backward-compatible aliases for tests that access tools by attribute
        self.analyze_scale_tool = self._tools["check_code_scale"]
        self.analyze_code_structure_tool = self._tools["analyze_code_structure"]
        self.table_format_tool = self.analyze_code_structure_tool
        self.read_partial_tool = self._tools["extract_code_section"]
        self.query_tool = self._tools["query_code"]
        self.list_files_tool = self._tools["list_files"]
        self.search_content_tool = self._tools["search_content"]
        self.find_and_grep_tool = self._tools["find_and_grep"]
        self.project_overview_tool = self._tools["get_project_overview"]
        self.file_health_tool = self._tools["check_file_health"]
        self.dependency_analysis_tool = self._tools["analyze_dependencies"]

        if UNIVERSAL_TOOL_AVAILABLE and UniversalAnalyzeTool is not None:
            try:
                self.universal_analyze_tool: UniversalAnalyzeTool | None = (
                    UniversalAnalyzeTool(project_root)
                )
            except Exception:
                self.universal_analyze_tool = None
        else:
            self.universal_analyze_tool = None

        self.code_file_resource = CodeFileResource()
        self.project_stats_resource = ProjectStatsResource()
        self.project_stats_resource.project_root = project_root

        self.name = MCP_INFO["name"]
        self.version = MCP_INFO["version"]

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
        """Legacy method for analyzing code scale. Delegates to code_scale_handler."""
        return await analyze_code_scale(
            arguments,
            analysis_engine=self.analysis_engine,
            security_validator=self.security_validator,
            universal_analyze_tool=getattr(self, "universal_analyze_tool", None),
            initialization_complete=self._initialization_complete,
        )

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
        """
        Read a resource by URI.

        Args:
            uri: Resource URI to read

        Returns:
            Resource content

        Raises:
            ValueError: If URI is invalid or resource not found
        """
        if uri.startswith("code://file/"):
            # Extract file path from URI
            result = await self.code_file_resource.read_resource(uri)
            return {"content": result}
        elif uri.startswith("code://stats/"):
            # Extract stats type from URI
            result = await self.project_stats_resource.read_resource(uri)
            return {"content": result}
        else:
            raise ValueError(f"Unknown resource URI: {uri}")

    def create_server(self) -> Server:
        """
        Create and configure the MCP server.

        Returns:
            Configured MCP Server instance
        """
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP library not available. Please install mcp package.")

        server: Server = Server(self.name)

        # Register tools using @server decorators (standard MCP pattern)
        @server.list_tools()  # type: ignore[untyped-decorator]
        async def handle_list_tools() -> list[Tool]:
            """List all available tools."""
            logger.info("Client requesting tools list")

            tools = [Tool(**t.get_tool_definition()) for _, t in self._tool_instances]
            tools.append(
                Tool(
                    name="set_project_path",
                    description="SMART Workflow 'Set' step (FIRST): Set the project root path for security boundaries. Call this before any other tool to ensure correct file resolution and security validation.",
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
            )

            logger.info(f"Returning {len(tools)} tools: {[t.name for t in tools]}")
            return tools

        @server.call_tool()  # type: ignore[untyped-decorator]
        async def handle_call_tool(
            name: str, arguments: dict[str, Any]
        ) -> list[TextContent]:
            try:
                self._ensure_initialized()
                logger.info(
                    f"MCP tool call: {name} with args: {list(arguments.keys())}"
                )

                # Security pre-check for file_path arguments
                self._validate_file_path_security(arguments)

                # Dispatch
                if name == "set_project_path":
                    result = self._handle_set_project_path(arguments)
                elif name == "extract_code_section":
                    result = await self._handle_extract_code_section(arguments)
                elif name == "analyze_code_structure":
                    result = await self.table_format_tool.execute(arguments)
                elif name in self._tools:
                    result = await self._tools[name].execute(arguments)
                else:
                    raise ValueError(f"Unknown tool: {name}")

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, ensure_ascii=False),
                    )
                ]

            except Exception as e:
                try:
                    logger.error(f"Tool call error for {name}: {e}")
                except (ValueError, OSError):
                    pass
                error_body = build_agent_friendly_error(name, e)
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(error_body, indent=2, ensure_ascii=False),
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

        # Register SMART workflow prompts so AI agents can self-discover usage patterns
        try:
            from mcp.types import Prompt, PromptArgument

            _smart_prompt_args = [
                PromptArgument(
                    name="file_path",
                    description="Path to the source file to analyze",
                    required=True,
                ),
                PromptArgument(
                    name="question",
                    description="What you want to understand about the code",
                    required=False,
                ),
            ]

            _project_prompt_args = [
                PromptArgument(
                    name="project_root",
                    description="Absolute path to the project root directory",
                    required=True,
                ),
            ]

            @server.list_prompts()  # type: ignore
            async def handle_list_prompts() -> list[Prompt]:
                return [
                    Prompt(
                        name="smart_analyze",
                        description="SMART Workflow: Systematic code analysis for a single file. Recommended for files you haven't seen before.",
                        arguments=_smart_prompt_args,
                    ),
                    Prompt(
                        name="smart_explore",
                        description="SMART Workflow: Explore a new project. Get the full picture before diving into code.",
                        arguments=_project_prompt_args,
                    ),
                ]

            @server.get_prompt()  # type: ignore
            async def handle_get_prompt(
                name: str, arguments: dict[str, str] | None
            ) -> Any:
                args = arguments or {}
                if name == "smart_analyze":
                    file_path = args.get("file_path", "<file_path>")
                    question = args.get(
                        "question", "understand the structure and key logic"
                    )
                    return build_smart_analyze_response(file_path, question)
                elif name == "smart_explore":
                    project_root = args.get("project_root", "<project_root>")
                    return build_smart_explore_response(project_root)
                raise ValueError(f"Unknown prompt: {name}")

        except ImportError:
            # Prompt type unavailable in older MCP versions
            with contextlib.suppress(ValueError, OSError):
                logger.debug(
                    "Prompts API unavailable, skipping SMART prompt registration"
                )
        except Exception as e:
            with contextlib.suppress(ValueError, OSError):
                logger.debug(f"Prompts registration failed: {e}")

        self.server = server
        try:
            logger.info("MCP server created successfully")
        except (ValueError, OSError):
            pass  # Silently ignore logging errors during shutdown
        return server

    def set_project_path(self, project_path: str) -> None:
        """Set the project path for all components."""
        get_shared_cache().clear()
        self.project_stats_resource.set_project_path(project_path)

        for tool in self._tools.values():
            tool.set_project_path(project_path)

        if hasattr(self, "universal_analyze_tool") and self.universal_analyze_tool:
            self.universal_analyze_tool.set_project_path(project_path)

        self.analysis_engine = get_analysis_engine(project_path)
        self.security_validator = SecurityValidator(project_path)

        try:
            logger.info(f"Set project path to: {project_path}")
        except (ValueError, OSError):
            pass

    def _validate_file_path_security(self, arguments: dict[str, Any]) -> None:
        """Pre-check file_path arguments for security violations."""
        if "file_path" not in arguments:
            return

        file_path = arguments["file_path"]
        base_root = getattr(
            getattr(self.security_validator, "boundary_manager", None),
            "project_root",
            None,
        )
        if not PathClass(file_path).is_absolute() and base_root:
            resolved_candidate = str((PathClass(base_root) / file_path).resolve())
        else:
            resolved_candidate = file_path

        shared_cache = get_shared_cache()
        cached = shared_cache.get_security_validation(
            resolved_candidate, project_root=base_root
        )
        if cached is None:
            cached = self.security_validator.validate_file_path(resolved_candidate)
            shared_cache.set_security_validation(
                resolved_candidate, cached, project_root=base_root
            )

        if cached is not None:
            is_valid, error_msg = cached
            if not is_valid:
                raise ValueError(
                    f"Invalid or unsafe file path: {error_msg or file_path}"
                )

    def _handle_set_project_path(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handle the set_project_path tool call."""
        project_path = arguments.get("project_path")
        if not project_path or not isinstance(project_path, str):
            raise ValueError("project_path parameter is required and must be a string")
        if not PathClass(project_path).is_dir():
            raise ValueError(f"Project path does not exist: {project_path}")
        self.set_project_path(project_path)
        return {"status": "success", "project_root": project_path}

    async def _handle_extract_code_section(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle extract_code_section with batch/single mode support."""
        if "requests" in arguments and arguments["requests"] is not None:
            result: dict[str, Any] = await self.read_partial_tool.execute(arguments)
            return result

        if "file_path" not in arguments or "start_line" not in arguments:
            raise ValueError("file_path and start_line parameters are required")

        full_args = {
            "file_path": arguments["file_path"],
            "start_line": arguments["start_line"],
            "end_line": arguments.get("end_line"),
            "start_column": arguments.get("start_column"),
            "end_column": arguments.get("end_column"),
            "format": arguments.get("format", "text"),
            "output_file": arguments.get("output_file"),
            "suppress_output": arguments.get("suppress_output", False),
            "output_format": arguments.get("output_format", "toon"),
            "allow_truncate": arguments.get("allow_truncate", False),
            "fail_fast": arguments.get("fail_fast", False),
        }
        result2: dict[str, Any] = await self.read_partial_tool.execute(full_args)
        return result2

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
            pass  # Silently ignore logging errors during shutdown

        try:
            async with stdio_server() as (read_stream, write_stream):
                logger.info("Server running, waiting for requests...")
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
            pass  # Silently ignore logging errors during shutdown
        sys.exit(0)
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


def main_sync() -> None:
    """Synchronous entry point for setuptools scripts."""
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
