#!/usr/bin/env python3
"""
Framework Middleware & Interceptor Detection MCP Tool.

Discovers middleware chains across Flask/Django/FastAPI/Express/Spring.
Extends route detection to cover the full request pipeline.
"""

from typing import Any

from ...middleware_detector import MiddlewareDetector
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class MiddlewareDetectorTool(BaseMCPTool):
    """MCP Tool for detecting framework middleware and interceptors."""

    def __init__(self, project_root: str | None = None) -> None:
        self._detector: MiddlewareDetector | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._detector = None

    def _get_detector(self) -> MiddlewareDetector:
        if self._detector is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            self._detector = MiddlewareDetector(self.project_root)
        return self._detector

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "detect_middleware",
            "description": (
                "Detect middleware/interceptor chains across web frameworks. "
                "Finds Flask hooks (@before_request/@after_request), Django MIDDLEWARE "
                "settings, FastAPI @middleware decorators, Express app.use() middleware, "
                "and Spring @ControllerAdvice/Filter/HandlerInterceptor. "
                "Extends route detection to cover the full request pipeline."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["all", "summary", "lookup"],
                    "description": (
                        "Detection mode: 'all' (full list), 'summary' (counts by "
                        "framework/type), 'lookup' (filter by URL prefix)"
                    ),
                    "default": "all",
                },
                "url_prefix": {
                    "type": "string",
                    "description": "URL prefix to filter middleware (for 'lookup' mode)",
                },
                "framework": {
                    "type": "string",
                    "enum": ["all", "flask", "django", "fastapi", "express", "spring"],
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
            "required": [],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        mode = arguments.get("mode", "all")
        url_prefix = arguments.get("url_prefix", "")
        framework_filter = arguments.get("framework", "all")
        output_format = arguments.get("output_format", "toon")
        detector = self._get_detector()

        if mode == "summary":
            result: dict[str, Any] = {
                "success": True,
                **detector.summary(),
            }
        elif mode == "lookup" and url_prefix:
            mws = detector.lookup_by_url_prefix(url_prefix)
            result = {
                "success": True,
                "url_prefix": url_prefix,
                "middleware_count": len(mws),
                "middlewares": [m.to_dict() for m in mws],
            }
        else:
            mws = detector.detect_all()
            if framework_filter != "all":
                mws = [m for m in mws if m.framework == framework_filter]
            result = {
                "success": True,
                "middleware_count": len(mws),
                "middlewares": [m.to_dict() for m in mws],
            }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)
