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
from typing import Any, cast

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

from ..constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from ..core.analysis_engine import get_analysis_engine
from ..platform_compat.detector import PlatformDetector
from ..project_detector import detect_project_root
from ..security import SecurityValidator
from ..utils import setup_logger
from . import MCP_INFO
from .resources import CodeFileResource, ProjectStatsResource
from .tools.analyze_code_structure_tool import AnalyzeCodeStructureTool
from .tools.analyze_scale_tool import AnalyzeScaleTool
from .tools.find_and_grep_tool import FindAndGrepTool
from .tools.list_files_tool import ListFilesTool
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
            # Gracefully handle logging failures during initialization
            pass

        self.analysis_engine = get_analysis_engine(project_root)
        self.security_validator = SecurityValidator(project_root)
        # Use unified analysis engine instead of deprecated AdvancedAnalyzer

        # Initialize MCP tools with security validation (core tools + fd/rg tools)
        self.query_tool = QueryTool(project_root)  # query_code
        self.read_partial_tool = ReadPartialTool(project_root)  # extract_code_section
        self.analyze_code_structure_tool = AnalyzeCodeStructureTool(
            project_root
        )  # analyze_code_structure
        self.table_format_tool = (
            self.analyze_code_structure_tool
        )  # Alias for backward compatibility
        self.analyze_scale_tool = AnalyzeScaleTool(project_root)  # check_code_scale
        # New fd/rg tools
        self.list_files_tool = ListFilesTool(project_root)  # list_files
        self.search_content_tool = SearchContentTool(project_root)  # search_content
        self.find_and_grep_tool = FindAndGrepTool(project_root)  # find_and_grep

        # Optional universal tool to satisfy initialization tests
        # Allow tests to control initialization by checking if UniversalAnalyzeTool is available
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
        # Add project_root attribute for test compatibility
        self.project_stats_resource.project_root = project_root

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
            # Gracefully handle logging failures during initialization
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
        """
        Legacy method for analyzing code scale.
        Used by existing tests that mock server internals.
        """
        # For initialization-specific tests, we should raise MCPError instead of RuntimeError
        if not self._initialization_complete:
            from .utils.error_handler import MCPError

            raise MCPError("Server is still initializing")

        # For specific initialization tests we allow delegating to universal tool
        if "file_path" not in arguments:
            universal_tool = getattr(self, "universal_analyze_tool", None)
            if universal_tool is not None:
                try:
                    result = await universal_tool.execute(arguments)
                    return dict(result)  # Ensure proper type casting
                except ValueError:
                    # Re-raise ValueError as-is for test compatibility
                    raise
            else:
                raise ValueError("file_path is required")

        file_path = arguments["file_path"]
        language = arguments.get("language")
        include_complexity = arguments.get("include_complexity", True)
        include_details = arguments.get("include_details", False)

        # Use PathClass which is mocked in some tests
        base_root = getattr(
            getattr(self.security_validator, "boundary_manager", None),
            "project_root",
            None,
        )
        if not PathClass(file_path).is_absolute() and base_root:
            resolved_path = str((PathClass(base_root) / file_path).resolve())
        else:
            resolved_path = file_path

        # Security validation
        shared_cache = get_shared_cache()
        cached = shared_cache.get_security_validation(
            resolved_path, project_root=base_root
        )
        if cached is None:
            cached = self.security_validator.validate_file_path(resolved_path)
            shared_cache.set_security_validation(
                resolved_path, cached, project_root=base_root
            )
        is_valid, error_msg = cached
        if not is_valid:
            raise ValueError(f"Invalid file path: {error_msg}")

        # Use PathClass for existence check to respect mocks
        if not PathClass(resolved_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Detect language if not specified
        from ..language_detector import detect_language_from_file

        if not language:
            language = detect_language_from_file(resolved_path, project_root=base_root)

        # Create analysis request
        from ..core.analysis_engine import AnalysisRequest

        request = AnalysisRequest(
            file_path=resolved_path,
            language=language,
            include_complexity=include_complexity,
            include_details=include_details,
        )

        # Perform analysis
        analysis_result = await self.analysis_engine.analyze(request)

        if analysis_result is None or not analysis_result.success:
            error_msg = (
                analysis_result.error_message or "Unknown error"
                if analysis_result
                else "Unknown error"
            )
            raise RuntimeError(f"Failed to analyze file: {file_path} - {error_msg}")

        # Get element counts from the unified elements list
        elements = analysis_result.elements or []

        # Count elements by type using the new unified system
        classes_count = len(
            [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_CLASS)]
        )
        methods_count = len(
            [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)]
        )
        fields_count = len(
            [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)]
        )
        imports_count = len(
            [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_IMPORT)]
        )
        packages_count = len(
            [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_PACKAGE)]
        )
        total_elements = (
            classes_count
            + methods_count
            + fields_count
            + imports_count
            + packages_count
        )

        # Calculate unified file metrics (cached by content hash)
        file_metrics = compute_file_metrics(
            resolved_path, language=language, project_root=base_root
        )
        lines_code = file_metrics["code_lines"]
        lines_comment = file_metrics["comment_lines"]
        lines_blank = file_metrics["blank_lines"]

        result = {
            "file_path": file_path,
            "language": language,
            "metrics": {
                "lines_total": analysis_result.line_count,
                "lines_code": lines_code,
                "lines_comment": lines_comment,
                "lines_blank": lines_blank,
                "elements": {
                    "classes": classes_count,
                    "methods": methods_count,
                    "fields": fields_count,
                    "imports": imports_count,
                    "packages": packages_count,
                    "total": total_elements,
                },
            },
        }

        if include_complexity:
            # Add complexity metrics if available
            methods = [
                e for e in elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
            ]
            if methods:
                complexities = [getattr(m, "complexity_score", 0) for m in methods]
                result["metrics"]["complexity"] = {
                    "total": sum(complexities),
                    "average": round(
                        sum(complexities) / len(complexities) if complexities else 0, 2
                    ),
                    "max": max(complexities) if complexities else 0,
                }

        if include_details:
            # Convert elements to serializable format
            detailed_elements = []
            for elem in elements:
                if hasattr(elem, "__dict__"):
                    detailed_elements.append(elem.__dict__)
                else:
                    detailed_elements.append({"element": str(elem)})
            result["detailed_elements"] = detailed_elements

        return cast(dict[str, Any], result)

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
            try:
                # Ensure server is fully initialized
                self._ensure_initialized()

                # Log tool call
                logger.info(
                    f"MCP tool call: {name} with args: {list(arguments.keys())}"
                )

                # Validate file path security (server-side early rejection for compatibility)
                # Note: Tools also validate paths, but they use shared caching to avoid redundant work.
                if "file_path" in arguments:
                    file_path = arguments["file_path"]

                    # Best-effort resolve against project root for boundary enforcement
                    base_root = getattr(
                        getattr(self.security_validator, "boundary_manager", None),
                        "project_root",
                        None,
                    )
                    if not PathClass(file_path).is_absolute() and base_root:
                        resolved_candidate = str(
                            (PathClass(base_root) / file_path).resolve()
                        )
                    else:
                        resolved_candidate = file_path

                    shared_cache = get_shared_cache()
                    cached = shared_cache.get_security_validation(
                        resolved_candidate, project_root=base_root
                    )
                    if cached is None:
                        cached = self.security_validator.validate_file_path(
                            resolved_candidate
                        )
                        shared_cache.set_security_validation(
                            resolved_candidate, cached, project_root=base_root
                        )

                    if cached is not None:
                        is_valid, error_msg = cached
                        if not is_valid:
                            raise ValueError(
                                f"Invalid or unsafe file path: {error_msg or file_path}"
                            )

                # Handle tool calls with simplified parameter handling
                if name == "check_code_scale":
                    # Delegate to analyze_scale_tool which handles both single and batch modes
                    result = await self.analyze_scale_tool.execute(arguments)

                elif name == "analyze_code_structure":
                    if "file_path" not in arguments:
                        raise ValueError("file_path parameter is required")

                    result = await self.table_format_tool.execute(arguments)

                elif name == "extract_code_section":
                    # Design principle: keep server routing thin; tool owns schema/validation.
                    # Support both:
                    # - single mode: file_path + start_line (+ end_line/columns)
                    # - batch mode: requests[] (multi-file x multi-range)
                    if "requests" in arguments and arguments["requests"] is not None:
                        # Pass through as-is; ReadPartialTool handles exclusivity, limits, security validation, and TOON policy.
                        result = await self.read_partial_tool.execute(arguments)
                    else:
                        # Backward-compatible single-mode validation (keep legacy error semantics)
                        if (
                            "file_path" not in arguments
                            or "start_line" not in arguments
                        ):
                            raise ValueError(
                                "file_path and start_line parameters are required"
                            )

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
                        result = await self.read_partial_tool.execute(full_args)

                elif name == "set_project_path":
                    project_path = arguments.get("project_path")
                    if not project_path or not isinstance(project_path, str):
                        raise ValueError(
                            "project_path parameter is required and must be a string"
                        )
                    if not PathClass(project_path).is_dir():
                        raise ValueError(f"Project path does not exist: {project_path}")
                    self.set_project_path(project_path)
                    result = {"status": "success", "project_root": project_path}

                elif name == "query_code":
                    result = await self.query_tool.execute(arguments)

                elif name == "list_files":
                    result = await self.list_files_tool.execute(arguments)

                elif name == "search_content":
                    result = await self.search_content_tool.execute(arguments)

                elif name == "find_and_grep":
                    result = await self.find_and_grep_tool.execute(arguments)

                else:
                    raise ValueError(f"Unknown tool: {name}")

                # Return result
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

        # Some clients may request prompts; explicitly return empty list
        # Some clients may request prompts; explicitly return empty list
        try:
            from mcp.types import Prompt

            @server.list_prompts()  # type: ignore
            async def handle_list_prompts() -> list[Prompt]:
                logger.info("Client requested prompts list (returning empty)")
                return []

        except Exception as e:
            # If Prompt type is unavailable, log at debug level and continue safely
            with contextlib.suppress(ValueError, OSError):
                logger.debug(f"Prompts API unavailable or incompatible: {e}")

        self.server = server
        try:
            logger.info("MCP server created successfully")
        except (ValueError, OSError):
            pass  # Silently ignore logging errors during shutdown
        return server

    def set_project_path(self, project_path: str) -> None:
        """
        Set the project path for all components

        Args:
            project_path: Path to the project directory
        """
        # Invalidate shared caches once when the project root changes.
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
            pass  # Silently ignore logging errors during shutdown

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
