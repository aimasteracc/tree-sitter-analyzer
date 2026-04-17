#!/usr/bin/env python3
"""
API Discovery Tool — MCP Tool

Discovers and catalogs API endpoints from web frameworks:
- Flask: @app.route, @bp.route, Blueprint()
- FastAPI: @app.get, @app.post, @router.*, APIRouter()
- Django: urlpatterns, @api_view, path(), re_path()
- Express: app.get, app.post, router.*, express.Router
- Spring: @GetMapping, @PostMapping, @RequestMapping
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.api_discovery import (
    FrameworkType,
    calculate_metrics,
    discover_endpoints,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ApiDiscoveryTool(BaseMCPTool):
    """
    MCP tool for discovering API endpoints in web frameworks.

    Detects and catalogs API endpoints across multiple web frameworks,
    providing information about routes, HTTP methods, handlers, and locations.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        """Return the tool definition for MCP registration."""
        return {
            "name": "api_discovery",
            "description": (
                "Discover and catalog API endpoints from web frameworks. "
                "\n\n"
                "Supported Frameworks:\n"
                "- Flask: @app.route, @bp.route, Blueprint()\n"
                "- FastAPI: @app.get, @app.post, @router.*, APIRouter()\n"
                "- Django: urlpatterns, @api_view, path(), re_path()\n"
                "- Express.js: app.get, app.post, router.*, express.Router\n"
                "- Spring Boot: @GetMapping, @PostMapping, @RequestMapping\n"
                "\n"
                "Returns endpoint paths, HTTP methods, handler names, file locations, and line numbers."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_root": {
                        "type": "string",
                        "description": "Root directory of the project to analyze",
                    },
                    "frameworks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "enum": ["flask", "fastapi", "django", "express", "spring"],
                        "description": "Frameworks to detect. If omitted, detects all.",
                    },
                    "include_metrics": {
                        "type": "boolean",
                        "description": "Include summary metrics (counts by framework, method, file)",
                        "default": True,
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["toon", "json"],
                        "description": "Output format: toon (compressed) or json (readable)",
                        "default": "json",
                    },
                },
                "required": ["project_root"],
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute the API discovery tool.

        Args:
            arguments: Tool arguments with project_root and optional filters

        Returns:
            Dictionary containing discovered endpoints or error
        """
        project_root = arguments.get("project_root", "")
        frameworks_arg = arguments.get("frameworks")
        include_metrics = arguments.get("include_metrics", True)
        output_format = arguments.get("output_format", "json")

        # Validate project root exists
        root_path = Path(project_root)
        if not root_path.exists():
            return {
                "error": f"Project root does not exist: {project_root}",
                "format": output_format,
            }

        if not root_path.is_dir():
            return {
                "error": f"Project root is not a directory: {project_root}",
                "format": output_format,
            }

        # Parse frameworks filter
        frameworks: set[FrameworkType] | None = None
        if frameworks_arg:
            frameworks = set()
            for fw in frameworks_arg:
                try:
                    frameworks.add(FrameworkType(fw))
                except ValueError:
                    return {
                        "error": (
                            f"Unknown framework: {fw}. "
                            f"Valid options: flask, fastapi, django, express, spring"
                        ),
                        "format": output_format,
                    }

        # Discover endpoints
        try:
            endpoints = discover_endpoints(project_root, frameworks)
        except OSError as e:
            return {
                "error": f"Error reading project files: {e}",
                "format": output_format,
            }

        # Build result
        result: dict[str, Any] = {
            "endpoints": [ep.to_dict() for ep in endpoints],
        }

        if include_metrics:
            result["metrics"] = calculate_metrics(endpoints)

        # Format output
        if output_format == "toon":
            encoder = ToonEncoder()
            compressed = encoder.encode(result)
            return {
                "format": "toon",
                "toon": compressed,
            }
        else:
            return {
                "format": "json",
                "data": result,
            }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate tool arguments.

        Args:
            arguments: Arguments to validate

        Returns:
            True if arguments are valid

        Raises:
            ValueError: If arguments are invalid
        """
        # Check project_root is provided
        project_root = arguments.get("project_root", "")
        if not project_root:
            raise ValueError("project_root is required")

        # Check frameworks if provided
        frameworks_arg = arguments.get("frameworks")
        if frameworks_arg:
            valid_frameworks = {"flask", "fastapi", "django", "express", "spring"}
            for fw in frameworks_arg:
                if fw not in valid_frameworks:
                    raise ValueError(
                        f"Invalid framework: {fw}. "
                        f"Valid options: {', '.join(sorted(valid_frameworks))}"
                    )

        # Check output_format if provided
        output_format = arguments.get("output_format", "json")
        if output_format not in ["toon", "json"]:
            raise ValueError("output_format must be 'toon' or 'json'")

        # Check include_metrics is boolean if provided
        include_metrics = arguments.get("include_metrics")
        if include_metrics is not None and not isinstance(include_metrics, bool):
            raise ValueError("include_metrics must be a boolean")

        return True
