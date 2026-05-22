#!/usr/bin/env python3
"""
Framework Route Detector MCP Tool

Exposes URL→Handler route detection via MCP protocol.
Supports Flask, Django, FastAPI, Express, and Spring Boot.

CodeGraph parity: equivalent to CodeGraph's route-map feature.
"""

from typing import Any

from ...route_detector import RouteDetector
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class RouteDetectorTool(BaseMCPTool):
    """MCP Tool for framework route detection."""

    def __init__(self, project_root: str | None = None) -> None:
        self._detector: RouteDetector | None = None
        super().__init__(project_root)

    # ARCH-A4: hook fires from both __init__ and set_project_path, so the
    # one-line reset covers both lifecycles without a separate override.
    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._detector = None

    def _get_detector(self) -> RouteDetector:
        if self._detector is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            self._detector = RouteDetector(self.project_root)
        return self._detector

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "detect_routes",
            "description": (
                "Detect HTTP route declarations across web frameworks "
                "(Flask, Django, FastAPI, Express, Spring Boot). "
                "Modes: all (list all routes), summary (stats), "
                "lookup (find handler for URL), prefix (routes matching prefix), "
                "file (routes in a specific file). "
                "No other built-in tool provides URL→Handler mapping."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["all", "summary", "lookup", "prefix", "file"],
                    "description": "Query mode (default: summary)",
                    "default": "summary",
                },
                "url_pattern": {
                    "type": "string",
                    "description": "URL pattern to look up (for lookup/prefix modes)",
                },
                "file_path": {
                    "type": "string",
                    "description": "File path to scan (for file mode)",
                },
                "framework": {
                    "type": "string",
                    "enum": ["flask", "django", "fastapi", "express", "spring", "all"],
                    "description": "Filter by framework (default: all)",
                    "default": "all",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                    "default": "toon",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "summary")
        if mode == "lookup" and "url_pattern" not in arguments:
            raise ValueError("url_pattern is required for mode 'lookup'")
        if mode == "prefix" and "url_pattern" not in arguments:
            raise ValueError("url_pattern is required for mode 'prefix'")
        if mode == "file" and "file_path" not in arguments:
            raise ValueError("file_path is required for mode 'file'")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        mode = arguments.get("mode", "summary")
        output_format = arguments.get("output_format", "toon")
        framework_filter = arguments.get("framework", "all")
        detector = self._get_detector()

        if mode == "summary":
            summary = detector.summary()
            # pain #4 (tsa-landing dogfood): summary mode had no verdict.
            # Map to NOT_FOUND when the project has zero routes (so agents
            # know not to call follow-up route-related tools), else INFO.
            verdict = "INFO" if summary.get("total_routes", 0) > 0 else "NOT_FOUND"
            result = {
                "success": True,
                "mode": "summary",
                "verdict": verdict,
                **summary,
            }
        elif mode == "all":
            routes = detector.detect_all()
            if framework_filter != "all":
                routes = [r for r in routes if r.framework == framework_filter]
            result = {
                "success": True,
                "mode": "all",
                "verdict": "INFO" if routes else "NOT_FOUND",
                "route_count": len(routes),
                "routes": [r.to_dict() for r in routes],
            }
        elif mode == "lookup":
            url = arguments["url_pattern"]
            matches = detector.lookup_handler(url)
            if framework_filter != "all":
                matches = [r for r in matches if r.framework == framework_filter]
            result = {
                "success": True,
                "mode": "lookup",
                "verdict": "INFO" if matches else "NOT_FOUND",
                "url_pattern": url,
                "match_count": len(matches),
                "routes": [r.to_dict() for r in matches],
            }
        elif mode == "prefix":
            prefix = arguments["url_pattern"]
            matches = detector.lookup_url_prefix(prefix)
            if framework_filter != "all":
                matches = [r for r in matches if r.framework == framework_filter]
            result = {
                "success": True,
                "mode": "prefix",
                "verdict": "INFO" if matches else "NOT_FOUND",
                "prefix": prefix,
                "match_count": len(matches),
                "routes": [r.to_dict() for r in matches],
            }
        elif mode == "file":
            # Validate the user-supplied path stays inside project_root and
            # resolve any symlinks before we hand the path to the detector.
            file_path = self.resolve_and_validate_file_path(arguments["file_path"])
            routes = detector.detect_file(file_path)
            result = {
                "success": True,
                "mode": "file",
                "verdict": "INFO" if routes else "NOT_FOUND",
                "file_path": file_path,
                "route_count": len(routes),
                "routes": [r.to_dict() for r in routes],
            }
        else:
            raise ValueError(f"Unknown mode: {mode}")

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)
