#!/usr/bin/env python3
"""
MCP Server implementation for Tree-sitter Analyzer (Refactored)

This module provides the main MCP server that exposes tree-sitter analyzer
functionality through the Model Context Protocol.
"""

import argparse
import asyncio
import sys
from pathlib import Path as PathClass
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp.server.stdio import stdio_server as _stdio_server

    stdio_server: Any = _stdio_server
    from mcp.types import Resource, Tool

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


from ..core.analysis_engine import get_analysis_engine
from ..platform_compat.detector import PlatformDetector
from ..project_detector import detect_project_root
from ..security import SecurityValidator
from ..utils import setup_logger
from . import MCP_INFO
from ._server_helpers import (
    attach_tool_aliases,
    build_initialization_options,
    detect_server_version,
    init_universal_tool,
    resolve_project_root,
)
from .resources import CodeFileResource, ProjectStatsResource
from .server_utils.code_scale_handler import analyze_code_scale
from .server_utils.prompt_registration import register_prompts
from .server_utils.resource_registration import register_resources
from .server_utils.tool_registration import register_tools
from .tools.agent_skills_tool import AgentSkillsTool
from .tools.agent_workflow_tool import AgentWorkflowTool
from .tools.analyze_code_structure_tool import AnalyzeCodeStructureTool
from .tools.analyze_scale_tool import AnalyzeScaleTool
from .tools.change_impact_tool import ChangeImpactTool
from .tools.dependency_analysis_tool import DependencyAnalysisTool
from .tools.file_health_tool import FileHealthTool
from .tools.find_and_grep_tool import FindAndGrepTool
from .tools.list_files_tool import ListFilesTool
from .tools.parser_readiness_tool import ParserReadinessTool
from .tools.project_health_tool import ProjectHealthTool
from .tools.project_overview_tool import ProjectOverviewTool
from .tools.query_tool import QueryTool
from .tools.read_partial_tool import ReadPartialTool
from .tools.refactoring_suggestions_tool import RefactoringSuggestionsTool
from .tools.safe_to_edit_tool import SafeToEditTool
from .tools.search_content_tool import SearchContentTool
from .tools.smart_context_tool import SmartContextTool
from .tools.symbol_lineage_tool import SymbolLineageTool
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


def _create_tool_registry(
    project_root: str | None,
) -> tuple[list[tuple[str, Any]], dict[str, Any]]:
    """Create the tool registry with all MCP tools."""
    tool_instances: list[tuple[str, Any]] = [
        ("check_code_scale", AnalyzeScaleTool(project_root)),
        ("analyze_code_structure", AnalyzeCodeStructureTool(project_root)),
        ("extract_code_section", ReadPartialTool(project_root)),
        ("query_code", QueryTool(project_root)),
        ("list_files", ListFilesTool(project_root)),
        ("search_content", SearchContentTool(project_root)),
        ("find_and_grep", FindAndGrepTool(project_root)),
        ("list_agent_skills", AgentSkillsTool(project_root)),
        ("get_agent_workflow", AgentWorkflowTool(project_root)),
        ("advise_parser_readiness", ParserReadinessTool(project_root)),
        ("get_project_overview", ProjectOverviewTool(project_root)),
        ("check_project_health", ProjectHealthTool(project_root)),
        ("check_file_health", FileHealthTool(project_root)),
        ("analyze_dependencies", DependencyAnalysisTool(project_root)),
        ("analyze_change_impact", ChangeImpactTool(project_root)),
        ("refactoring_suggestions", RefactoringSuggestionsTool(project_root)),
        ("safe_to_edit", SafeToEditTool(project_root)),
        ("smart_context", SmartContextTool(project_root)),
        ("symbol_lineage", SymbolLineageTool(project_root)),
    ]
    return tool_instances, dict(tool_instances)


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

        self._tool_instances, self._tools = _create_tool_registry(project_root)

        attach_tool_aliases(self, self._tools)

        self.universal_analyze_tool = init_universal_tool(
            project_root,
            universal_tool_available=UNIVERSAL_TOOL_AVAILABLE,
            universal_tool_cls=UniversalAnalyzeTool,
        )

        self.code_file_resource = CodeFileResource()
        self.project_stats_resource = ProjectStatsResource()
        self.project_stats_resource.project_root = project_root

        self.name = MCP_INFO["name"]
        self.version = detect_server_version(
            MCP_INFO["version"],
            platform_detector=PlatformDetector,
            logger=logger,
        )

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

    # Analyze source code structure: _analyze_code_scale
    async def _analyze_code_scale(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Legacy method for analyzing code scale. Delegates to code_scale_handler."""
        return await analyze_code_scale(
            arguments,
            analysis_engine=self.analysis_engine,
            security_validator=self.security_validator,
            universal_analyze_tool=getattr(self, "universal_analyze_tool", None),
            initialization_complete=self._initialization_complete,
            path_class=PathClass,
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

        # Register tools, resources, and prompts
        register_tools(server, self)

        # Register resources
        register_resources(server, self)

        # Register SMART workflow prompts so AI agents can self-discover usage patterns
        register_prompts(server)

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

        if cached is None:
            return

        is_valid, error_msg = cached
        if is_valid:
            return

        raise ValueError(f"Invalid or unsafe file path: {error_msg or file_path}")

    def _handle_set_project_path(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handle the set_project_path tool call."""
        project_path = arguments.get("project_path")
        if not project_path or not isinstance(project_path, str):
            raise ValueError("project_path parameter is required and must be a string")
        if not PathClass(project_path).is_dir():
            raise ValueError(f"Project path does not exist: {project_path}")
        self.set_project_path(project_path)
        return {"status": "success", "project_root": project_path}

    # Extract elements from AST: _handle_extract_code_section
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

    # Execute main logic: run
    async def run(self) -> None:
        """
        Run the MCP server.

        This method starts the server and handles stdio communication.
        """
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP library not available. Please install mcp package.")

        server = self.create_server()

        options = build_initialization_options(
            self.name,
            self.version,
            InitializationOptions,
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


# Parse input into structured data: parse_mcp_args
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

        project_root = resolve_project_root(
            args.project_root,
            cwd_factory=PathClass.cwd,
            path_class=PathClass,
            detect_project_root_func=detect_project_root,
            logger=logger,
        )

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
