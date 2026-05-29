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

# PERF-3: tool classes imported lazily by _create_tool_registry() — saves ~316 ms cold start.
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


def _log_safely(log_fn: Any, msg: str, *args: Any) -> None:
    """Invoke log_fn, silencing I/O errors (e.g. during shutdown)."""
    try:
        log_fn(msg, *args)
    except (ValueError, OSError):
        pass


def _create_tool_registry(
    project_root: str | None,
) -> tuple[list[tuple[str, Any]], dict[str, Any]]:
    """Delegates to the single-source registry in ``_tool_registry.py``."""
    from ._tool_registry import create_tool_registry

    return create_tool_registry(project_root)


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

        _log_safely(logger.info, "Starting MCP server initialization...")

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
        _log_safely(
            logger.info,
            "MCP server initialization complete: %s v%s",
            self.name,
            self.version,
        )

    def is_initialized(self) -> bool:
        """Check if the server is fully initialized."""
        return self._initialization_complete

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Backwards-compatible dispatch; resolves intent aliases before lookup."""
        from .intent_aliases import IntentAliasResolver

        tools = getattr(self, "_tools", None) or {}
        resolver = IntentAliasResolver()
        try:
            resolved = resolver.resolve(name)
        except (TypeError, ValueError):
            resolved = name
        tool = tools.get(resolved) or tools.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name}")
        return await tool.execute(arguments)

    def _ensure_initialized(self) -> None:
        """Ensure the server is initialized before processing requests."""
        if not self._initialization_complete:
            raise RuntimeError(
                "Server not fully initialized. Please wait for initialization to complete."
            )

    async def _analyze_code_scale(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Legacy method for analyzing code scale. Delegates to code_scale_handler."""
        _utool = getattr(self, "universal_analyze_tool", None)
        return await analyze_code_scale(
            arguments,
            analysis_engine=self.analysis_engine,
            security_validator=self.security_validator,
            universal_analyze_tool=_utool,
            initialization_complete=self._initialization_complete,
            path_class=PathClass,
        )

    def _calculate_file_metrics(self, file_path: str, language: str) -> dict[str, Any]:
        """Legacy wrapper for file metrics calculation."""
        bm = getattr(self.security_validator, "boundary_manager", None)
        base_root = getattr(bm, "project_root", None)
        return compute_file_metrics(
            file_path, language=language, project_root=base_root
        )

    async def _read_resource(self, uri: str) -> dict[str, Any]:
        """Read a resource by URI; raises ValueError for unknown URIs."""
        if uri.startswith("code://file/"):
            resource = self.code_file_resource
        elif uri.startswith("code://stats/"):
            resource = self.project_stats_resource
        else:
            _err_msg = "Unknown resource URI: " + uri
            raise ValueError(_err_msg)
        result = await resource.read_resource(uri)
        return {"content": result}

    def create_server(self) -> Server:
        """Create, configure, and return the MCP Server instance."""
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
        _log_safely(logger.info, "MCP server created successfully")
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

        _log_safely(logger.info, "Set project path to: %s", project_path)

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
            _p = PathClass(base_root) / file_path
            _resolved = _p.resolve()
            resolved_candidate = str(_resolved)
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

    async def _handle_extract_code_section(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle extract_code_section with batch/single mode support."""
        _tool = self.read_partial_tool
        if "requests" in arguments and arguments["requests"] is not None:
            return await _tool.execute(arguments)  # type: ignore[return-value]

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
        return await _tool.execute(full_args)  # type: ignore[return-value]

    # Public aliases for tool_registration.py companion module
    ensure_initialized = _ensure_initialized
    validate_file_path_security = _validate_file_path_security
    handle_set_project_path = _handle_set_project_path
    handle_extract_code_section = _handle_extract_code_section

    @property
    def tool_instances(self) -> list[Any]:
        """Public accessor for _tool_instances."""
        return self._tool_instances

    @property
    def tools(self) -> dict[str, Any]:
        """Public accessor for _tools."""
        return self._tools

    async def _run_server_loop(self, server: Server, options: Any) -> None:
        """Core stdio server I/O loop."""
        async with stdio_server() as (read_stream, write_stream):
            logger.info("Server running, waiting for requests...")
            await server.run(read_stream, write_stream, options)

    async def run(self) -> None:
        """Run the MCP server via stdio."""
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP library not available. Please install mcp package.")
        server = self.create_server()
        options = build_initialization_options(
            self.name,
            self.version,
            InitializationOptions,
        )
        _log_safely(logger.info, "Starting MCP server: %s v%s", self.name, self.version)
        try:
            await self._run_server_loop(server, options)
        except Exception as e:
            _log_safely(logger.error, "Server error: %s", e)
            raise
        finally:
            _log_safely(logger.info, "MCP server shutting down")


def parse_mcp_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments for MCP server."""
    parser = argparse.ArgumentParser(
        description="Tree-sitter Analyzer MCP Server",
    )

    parser.add_argument(
        "--project-root",
        help="Project root directory for security validation (auto-detected if not specified)",
    )

    return parser.parse_args(args)


async def main() -> None:
    """Main entry point for the MCP server."""
    try:
        _is_pytest = "pytest" in sys.argv[0]
        args = parse_mcp_args([] if _is_pytest else None)

        project_root = resolve_project_root(
            args.project_root,
            cwd_factory=PathClass.cwd,
            path_class=PathClass,
            detect_project_root_func=detect_project_root,
            logger=logger,
        )

        _log_safely(
            logger.info, "MCP server starting with project root: %s", project_root
        )

        server = TreeSitterAnalyzerMCPServer(project_root)
        await server.run()

        # Exit successfully after server run completes
        sys.exit(0)
    except KeyboardInterrupt:
        _log_safely(logger.info, "Server stopped by user")
        sys.exit(0)
    except Exception as e:
        _log_safely(logger.error, "Server failed: %s", e)
        sys.exit(1)
    finally:
        _log_safely(logger.info, "MCP server shutdown complete")


def main_sync() -> None:
    """Synchronous entry point for setuptools scripts."""
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
