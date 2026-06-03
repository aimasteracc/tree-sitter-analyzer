#!/usr/bin/env python3
"""
CodeGraph Call Path MCP Tool

Find execution paths between two functions via BFS on call edges.
Answers "how does execution reach from function A to function B?"

Unlike callers (all X that call Y) and callees (all Y that X calls),
this tool traces the *specific path* through the call graph.

Supports three search strategies:
  - forward: BFS from source following callees
  - backward: BFS from target following callers
  - bidirectional: BFS from both ends, meet in the middle (fastest)
"""

from __future__ import annotations

from typing import Any

from ...call_path import CallPathFinder
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeGraphCallPathTool(BaseMCPTool):
    """MCP Tool for finding execution paths between two functions."""

    def __init__(self, project_root: str | None = None) -> None:
        self._finder: CallPathFinder | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._finder = None

    def _get_finder(self) -> CallPathFinder:
        if self._finder is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            self._finder = CallPathFinder(self.project_root)
        return self._finder

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_call_path",
            "description": (
                "Find execution paths between two functions via BFS on call edges "
                "(CodeGraph parity). Traces the call chain from source to target. "
                "Unlike callers/callees (direct edges), this finds the full path. "
                "No other built-in tool provides inter-function path tracing."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source_function": {
                    "type": "string",
                    "description": "Name of the starting function",
                },
                "target_function": {
                    "type": "string",
                    "description": "Name of the destination function",
                },
                "source_file": {
                    "type": "string",
                    "description": (
                        "Optional file path to disambiguate the source function"
                    ),
                },
                "target_file": {
                    "type": "string",
                    "description": (
                        "Optional file path to disambiguate the target function"
                    ),
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum BFS depth (default 10)",
                    "default": 10,
                },
                "max_paths": {
                    "type": "integer",
                    "description": "Maximum number of paths to return (default 5)",
                    "default": 5,
                },
                "direction": {
                    "type": "string",
                    "enum": ["forward", "backward", "bidirectional"],
                    "description": (
                        "Search direction: 'forward' (callees from source), "
                        "'backward' (callers from target), "
                        "'bidirectional' (both, fastest)"
                    ),
                    "default": "bidirectional",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                    "default": "toon",
                },
            },
            "required": ["source_function", "target_function"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if "source_function" not in arguments:
            raise ValueError("source_function is required")
        if "target_function" not in arguments:
            raise ValueError("target_function is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        source_function = arguments["source_function"]
        target_function = arguments["target_function"]
        source_file = arguments.get("source_file")
        target_file = arguments.get("target_file")
        max_depth = int(arguments.get("max_depth", 10))
        max_paths = int(arguments.get("max_paths", 5))
        direction = arguments.get("direction", "bidirectional")
        output_format = arguments.get("output_format", "toon")

        finder = self._get_finder()
        result = finder.find_path(
            source_function=source_function,
            target_function=target_function,
            source_file=source_file,
            target_file=target_file,
            max_depth=max_depth,
            max_paths=max_paths,
            direction=direction,
        )

        paths = [p.to_dict() for p in result.paths]
        result_dict: dict[str, Any] = {
            "success": True,
            "verdict": "PATH_FOUND" if result.paths else "NO_PATH",
            "data_source": result.data_source,
            "source": source_function,
            "target": target_function,
            "path_count": len(result.paths),
            "truncated": result.truncated,
            "paths": paths,
        }

        # ------------------------------------------------------------------
        # Enrich coordinates -> content (turn-saving): inline verbatim source
        # bodies so the consuming agent can answer without per-hop Read calls.
        # See call_path_enrich for the cost rationale and output caps.
        # ------------------------------------------------------------------
        self._enrich_with_bodies(
            result_dict,
            paths,
            source_function,
            target_function,
            source_file,
            target_file,
        )

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result_dict, output_format)

    def _enrich_with_bodies(
        self,
        result_dict: dict[str, Any],
        paths: list[dict[str, Any]],
        source_function: str,
        target_function: str,
        source_file: str | None,
        target_file: str | None,
    ) -> None:
        """Inline source bodies + a deterrent ``next_step`` into the envelope.

        Best-effort: any failure leaves the bare-coordinate response intact
        rather than crashing the tool. The cache is reused from the finder.
        """
        from . import call_path_enrich as enrich

        finder = self._finder
        cache = None
        if finder is not None:
            try:
                cache = finder._try_get_cache()
            except Exception:
                cache = None

        project_root = self.project_root or "."

        if paths:
            bodies: list[dict[str, Any]] = []
            truncated_body = False
            if cache is not None:
                endpoint_hints: dict[str, str] = {}
                if source_file:
                    endpoint_hints[source_function] = source_file
                if target_file:
                    endpoint_hints[target_function] = target_file
                try:
                    bodies, truncated_body = enrich.inline_path_bodies(
                        project_root, cache, paths, endpoint_hints
                    )
                except Exception:  # pragma: no cover - defensive
                    bodies, truncated_body = [], False
            result_dict["source_bodies"] = bodies
            result_dict["bodies_truncated"] = truncated_body
            n = result_dict.get("path_count", 0)
            suffix = (
                " Some bodies truncated (see full_at) — Read only those if needed."
                if truncated_body
                else ""
            )
            result_dict["next_step"] = (
                f"Path: {n} path(s), {len(bodies)} function bodies inlined in "
                "source_bodies below — answer directly, no Read needed." + suffix
            )
            return

        # Dead end: no static path (dynamic dispatch or missing edge).
        dead_end: dict[str, Any] = {}
        if cache is not None:
            try:
                dead_end = enrich.build_dead_end(
                    project_root,
                    cache,
                    source_function,
                    target_function,
                    source_file,
                    target_file,
                )
            except Exception:  # pragma: no cover - defensive
                dead_end = {}
        result_dict["dead_end"] = dead_end
        result_dict["next_step"] = (
            "No static path (dynamic dispatch or missing edge). Both endpoints' "
            "bodies + their direct callers/callees are inlined in dead_end — "
            "answer from these, no Read needed."
        )
