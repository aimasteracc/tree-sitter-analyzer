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
            result = {"success": True, "mode": "summary", **detector.summary()}
        elif mode == "all":
            routes = detector.detect_all()
            if framework_filter != "all":
                routes = [r for r in routes if r.framework == framework_filter]
            result = {
                "success": True,
                "mode": "all",
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
                "file_path": file_path,
                "route_count": len(routes),
                "routes": [r.to_dict() for r in routes],
            }
        else:
            raise ValueError(f"Unknown mode: {mode}")

        # Top-level summary_line + agent_summary for LLM consumers.
        _attach_route_summary(result, mode)

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)


def _attach_route_summary(result: dict[str, Any], mode: str) -> None:
    """Attach summary_line + agent_summary to a route_detector result.

    Headline depends on mode — summary mode shows the global "N routes across
    M frameworks" line, the lookup/prefix/file modes show their match count.
    """
    if mode == "summary":
        total = int(result.get("total_routes", 0))
        by_framework = result.get("by_framework", {}) or {}
        framework_count = len(by_framework)
        summary_line = f"{total} routes across {framework_count} frameworks"
        next_step = (
            "detect_routes mode=all for full list, or mode=lookup url_pattern=<url> for one URL"
            if total
            else "no routes detected — verify project_root or supported framework usage"
        )
    elif mode == "all":
        count = int(result.get("route_count", 0))
        summary_line = f"{count} routes"
        next_step = (
            "detect_routes mode=lookup url_pattern=<url> to find a specific handler"
        )
    elif mode == "lookup":
        url = result.get("url_pattern", "?")
        count = int(result.get("match_count", 0))
        summary_line = f"lookup {url}: {count} match(es)"
        next_step = (
            "read_partial on the handler file at the matched line range"
            if count
            else "try detect_routes mode=prefix to widen the search"
        )
    elif mode == "prefix":
        prefix = result.get("prefix", "?")
        count = int(result.get("match_count", 0))
        summary_line = f"prefix {prefix}: {count} route(s)"
        next_step = (
            "detect_routes mode=lookup url_pattern=<exact> to drill into one"
            if count
            else "no routes matching this prefix"
        )
    elif mode == "file":
        fp = result.get("file_path", "?")
        count = int(result.get("route_count", 0))
        summary_line = f"file {fp}: {count} route(s)"
        next_step = (
            "analyze_code_structure on the file to map handler bodies"
            if count
            else "file declares no recognized routes"
        )
    else:
        summary_line = f"detect_routes mode={mode}"
        next_step = "review the result fields"

    result["summary_line"] = summary_line
    result["agent_summary"] = {
        "summary_line": summary_line,
        "next_step": next_step,
    }
