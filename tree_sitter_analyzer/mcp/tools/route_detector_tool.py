#!/usr/bin/env python3
"""
Framework Route Detector MCP Tool

Exposes URL→Handler route detection via MCP protocol.
Supports Flask, Django, FastAPI, Express, and Spring Boot.

CodeGraph parity: equivalent to CodeGraph's route-map feature.
"""

import os
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
        """Dispatch route detection by ``mode``.

        r37bj (dogfood): tool flagged this at 130 lines. Refactor splits
        each mode into a focused builder method. M4 file-mode validation
        + M6 canonical envelope keys preserved exactly.
        """
        self.validate_arguments(arguments)
        mode = arguments.get("mode", "summary")
        output_format = arguments.get("output_format", "toon")
        framework_filter = arguments.get("framework", "all")
        detector = self._get_detector()

        if mode == "summary":
            result = self._build_summary_response(detector)
        elif mode == "all":
            result = self._build_all_response(detector, framework_filter)
        elif mode == "lookup":
            result = self._build_lookup_response(
                detector, arguments["url_pattern"], framework_filter
            )
        elif mode == "prefix":
            result = self._build_prefix_response(
                detector, arguments["url_pattern"], framework_filter
            )
        elif mode == "file":
            file_result = self._build_file_response(
                detector, arguments["file_path"], output_format
            )
            if file_result.get("success") is False:
                return file_result
            result = file_result
        else:
            raise ValueError(f"Unknown mode: {mode}")

        _attach_route_summary(result, mode)
        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    @staticmethod
    def _build_summary_response(detector: Any) -> dict[str, Any]:
        """M6: ``mode=summary`` exposes the canonical key set (incl. empty ``routes``)."""
        summary_data = detector.summary()
        return {
            "success": True,
            "mode": "summary",
            "total_routes": summary_data["total_routes"],
            "route_count": summary_data["total_routes"],  # deprecated alias
            "routes": [],
            "by_framework": summary_data["by_framework"],
            "by_method": summary_data["by_method"],
            "file_count": summary_data["file_count"],
        }

    @staticmethod
    def _build_all_response(detector: Any, framework_filter: str) -> dict[str, Any]:
        """M6: ``mode=all`` adds full ``routes`` list + recomputed aggregates."""
        routes = detector.detect_all()
        if framework_filter != "all":
            routes = [r for r in routes if r.framework == framework_filter]
        by_framework: dict[str, int] = {}
        by_method: dict[str, int] = {}
        for r in routes:
            by_framework[r.framework] = by_framework.get(r.framework, 0) + 1
            by_method[r.http_method] = by_method.get(r.http_method, 0) + 1
        return {
            "success": True,
            "mode": "all",
            "total_routes": len(routes),
            "route_count": len(routes),  # deprecated alias
            "routes": [r.to_dict() for r in routes],
            "by_framework": by_framework,
            "by_method": by_method,
            "file_count": len({r.file_path for r in routes}),
        }

    @staticmethod
    def _build_lookup_response(
        detector: Any, url: str, framework_filter: str
    ) -> dict[str, Any]:
        """``mode=lookup`` returns exact URL pattern matches."""
        matches = detector.lookup_handler(url)
        if framework_filter != "all":
            matches = [r for r in matches if r.framework == framework_filter]
        return {
            "success": True,
            "mode": "lookup",
            "url_pattern": url,
            "match_count": len(matches),
            "routes": [r.to_dict() for r in matches],
        }

    @staticmethod
    def _build_prefix_response(
        detector: Any, prefix: str, framework_filter: str
    ) -> dict[str, Any]:
        """``mode=prefix`` returns routes whose URL pattern starts with ``prefix``."""
        matches = detector.lookup_url_prefix(prefix)
        if framework_filter != "all":
            matches = [r for r in matches if r.framework == framework_filter]
        return {
            "success": True,
            "mode": "prefix",
            "prefix": prefix,
            "match_count": len(matches),
            "routes": [r.to_dict() for r in matches],
        }

    def _build_file_response(
        self,
        detector: Any,
        raw_file_path: str,
        output_format: str,
    ) -> dict[str, Any]:
        """``mode=file`` — validates path (M4) then runs single-file detection."""
        file_path = self.resolve_and_validate_file_path(raw_file_path)
        error = _validate_file_mode_path(file_path, raw_file_path, output_format)
        if error is not None:
            return error
        routes = detector.detect_file(file_path)
        return {
            "success": True,
            "mode": "file",
            "file_path": file_path,
            "route_count": len(routes),
            "routes": [r.to_dict() for r in routes],
        }


def _pluralize(count: int, singular: str, plural: str | None = None) -> str:
    """Return ``count + " " + (singular|plural)`` with English plural rules.

    r37r (dogfood): ``detect_routes`` summary_line used to print
    ``"2 routes across 1 frameworks"`` — count 1 with the plural "frameworks"
    is a grammar bug that makes the tool look unpolished. This helper
    centralises the rule (n != 1 → plural) so every count rendered into a
    summary_line is correct.
    """
    word = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {word}"


def _attach_route_summary(result: dict[str, Any], mode: str) -> None:
    """Attach summary_line + agent_summary to a route_detector result.

    Headline depends on mode — summary mode shows the global "N route(s) across
    M framework(s)" line, the lookup/prefix/file modes show their match count.
    """
    if mode == "summary":
        total = int(result.get("total_routes", 0))
        by_framework = result.get("by_framework", {}) or {}
        framework_count = len(by_framework)
        summary_line = (
            f"{_pluralize(total, 'route')} across "
            f"{_pluralize(framework_count, 'framework')}"
        )
        next_step = (
            "detect_routes mode=all for full list, or mode=lookup url_pattern=<url> for one URL"
            if total
            else "no routes detected — verify project_root or supported framework usage"
        )
    elif mode == "all":
        # M6: prefer the canonical ``total_routes`` key. Fallback to the
        # deprecated ``route_count`` alias keeps older fixtures that still
        # build the result dict by hand from working.
        count = int(result.get("total_routes", result.get("route_count", 0)))
        summary_line = _pluralize(count, "route")
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
    # N2 (round-27): emit ``verdict`` so the cross-tool envelope contract
    # (``TestEnvelopeContractSnapshot``) is satisfied. detect_routes is
    # purely informational — it discovers route declarations, it does
    # NOT make a safety judgement — so ``INFO`` is the canonical label
    # (matches the verdict vocabulary used by other informational
    # tools). Agents that branch on ``verdict`` see a consistent shape
    # regardless of which tool ran.
    # r37w (envelope ratchet): mirror to top-level so the r37u contract
    # holds (``result["verdict"]`` must equal
    # ``result["agent_summary"]["verdict"]``, not None).
    result["verdict"] = "INFO"
    result["agent_summary"] = {
        "summary_line": summary_line,
        "next_step": next_step,
        "verdict": "INFO",
    }


def _validate_file_mode_path(
    file_path: str,
    raw_file_path: str,
    output_format: str,
) -> dict[str, Any] | None:
    """M4: reject missing / dir / non-regular paths with a structured envelope.

    r37bj: extracted from ``execute``'s ``mode=file`` branch so the
    dispatch reads as a flat ``if error: return error`` guard.
    """
    if not os.path.exists(file_path):
        return _validation_error_envelope(
            f"file not found: {raw_file_path}",
            mode="file",
            output_format=output_format,
            file_path=raw_file_path,
        )
    if os.path.isdir(file_path):
        return _validation_error_envelope(
            (
                f"path is a directory: {raw_file_path} — use mode='all' "
                "for a project-wide scan, or pass an individual file"
            ),
            mode="file",
            output_format=output_format,
            file_path=raw_file_path,
        )
    if not os.path.isfile(file_path):
        return _validation_error_envelope(
            f"not a regular file: {raw_file_path}",
            mode="file",
            output_format=output_format,
            file_path=raw_file_path,
        )
    return None


def _validation_error_envelope(
    message: str,
    *,
    mode: str,
    output_format: str,
    file_path: str | None = None,
) -> dict[str, Any]:
    """M4 (round-26): canonical validation-error envelope for detect_routes.

    Mirrors the ``--file-health`` / ``--code-patterns`` / ``--safe-to-edit``
    error shape so agents that consume any of those can reuse the same
    parser. ``error_type='validation'`` is the standard bucket used by
    the dispatcher's exception classifier for user-input failures.
    """
    summary_line = f"detect_routes: error — {message}"
    response: dict[str, Any] = {
        "success": False,
        "mode": mode,
        "error_type": "validation",
        "error": message,
        "summary_line": summary_line,
        # r37w: top-level verdict mirror (envelope contract).
        "verdict": "ERROR",
        "agent_summary": {
            "summary_line": summary_line,
            "next_step": "Fix the input path and retry.",
            "verdict": "ERROR",
        },
    }
    if file_path is not None:
        response["file_path"] = file_path

    from ..utils.format_helper import apply_toon_format_to_response

    return apply_toon_format_to_response(response, output_format)
