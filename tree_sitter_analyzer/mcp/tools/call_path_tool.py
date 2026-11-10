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

import sqlite3
from typing import Any

from ...call_path import CallPathFinder
from ...call_path_pinned import NAME_KEYED_REASON
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
                    "enum": ["json"],
                    "description": "Output format: JSON",
                    "default": "json",
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
        if self.project_root:
            from ...index_snapshot import certified_index_read

            try:
                with certified_index_read(self.project_root) as owner:
                    if owner is not None:
                        return await self._execute_bound(
                            arguments, owner.query_cache(), owner.read_source
                        )
            except (OSError, ValueError, RuntimeError, sqlite3.DatabaseError):
                pass
        return await self._execute_bound(arguments, None, None)

    async def _execute_bound(
        self, arguments: dict[str, Any], bound_cache: Any, source_reader: Any
    ) -> dict[str, Any]:
        source_function = arguments["source_function"]
        target_function = arguments["target_function"]
        source_file = arguments.get("source_file")
        target_file = arguments.get("target_file")
        max_depth = int(arguments.get("max_depth", 10))
        max_paths = int(arguments.get("max_paths", 5))
        direction = arguments.get("direction", "bidirectional")
        output_format = arguments.get("output_format", "json")

        finder = (
            CallPathFinder(self.project_root or ".", cache=bound_cache)
            if bound_cache is not None
            else self._get_finder()
        )
        from ..utils.format_helper import apply_output_format_to_response

        # #1942: a `Class.method` endpoint is resolved to one definition and the
        # search runs between definitions, or the answer fails closed.
        qualified = self._qualified_answer(
            finder, bound_cache, source_reader, arguments, max_depth, max_paths
        )
        if qualified is not None:
            return apply_output_format_to_response(qualified, output_format)

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
            # Canonical verdict for agents that branch on it (tool_response.
            # CANONICAL_VERDICTS); the specific outcome stays in path_status.
            "verdict": "INFO" if result.paths else "NOT_FOUND",
            "path_status": "PATH_FOUND" if result.paths else "NO_PATH",
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
            bound_cache,
            source_reader if result.data_source == "sql" else None,
        )

        return apply_output_format_to_response(result_dict, output_format)

    def _qualified_answer(
        self,
        finder: CallPathFinder,
        bound_cache: Any,
        source_reader: Any,
        arguments: dict[str, Any],
        max_depth: int,
        max_paths: int,
    ) -> dict[str, Any] | None:
        """The definition-to-definition answer, or None for two bare names."""
        from . import call_path_endpoints as endpoints

        source = str(arguments["source_function"])
        target = str(arguments["target_function"])
        if not (endpoints.is_qualified(source) or endpoints.is_qualified(target)):
            return None
        cache = bound_cache if bound_cache is not None else finder._try_get_cache()
        if cache is None or not cache.has_call_edges():
            return None
        from ...call_path_pinned import SymbolBook

        conn = cache.get_conn()
        book = SymbolBook(conn)
        ends = [
            endpoints.resolve(book, "source", source, arguments.get("source_file")),
            endpoints.resolve(book, "target", target, arguments.get("target_file")),
        ]
        if any(end.status != "resolved" for end in ends):
            return {
                **endpoints.failure_response(ends),
                "source": source,
                "target": target,
            }
        result = endpoints.pinned_response(
            conn, book, ends[0], ends[1], max_depth, max_paths
        )
        bodies = self._pinned_bodies(book, result, source_reader)
        if result["paths"]:
            result["source_bodies"] = bodies
            result["bodies_truncated"] = any(b.get("truncated") for b in bodies)
            result["next_step"] = (
                f"Path: {result['path_count']} path(s) between the resolved "
                f"definitions, {len(bodies)} function bodies inlined in "
                "source_bodies. Hops with callee_resolution=name_only go through "
                "a receiver the index could not bind: read that call site."
            )
        else:
            for block in result["dead_end"].values():
                body = next(
                    (
                        b
                        for b in bodies
                        if (b["file"], b["start_line"])
                        == (block["file"], block["line"])
                    ),
                    None,
                )
                if body is not None:
                    block["body"] = body
        return result

    def _pinned_bodies(
        self, book: Any, result: dict[str, Any], source_reader: Any
    ) -> list[dict[str, Any]]:
        """Verbatim bodies of the definitions in ``result`` (certified reads only)."""
        if source_reader is None:
            return []
        from . import call_path_enrich as enrich
        from .call_path_endpoints import path_definitions

        budget = [enrich.MAX_TOTAL_BODY_LINES]
        bodies: list[dict[str, Any]] = []
        for definition in path_definitions(book, result):
            try:
                text = source_reader(definition.file)
            except (OSError, ValueError, RuntimeError):
                continue
            if not isinstance(text, str):
                continue
            block = enrich._read_body(
                self.project_root or ".",
                {
                    "name": definition.label,
                    "file": definition.file,
                    "line": definition.line,
                    "end_line": definition.end_line,
                },
                budget,
                source_text=text,
            )
            if block is not None:
                bodies.append(block)
        return bodies

    def _enrich_with_bodies(
        self,
        result_dict: dict[str, Any],
        paths: list[dict[str, Any]],
        source_function: str,
        target_function: str,
        source_file: str | None,
        target_file: str | None,
        bound_cache: Any = None,
        source_reader: Any = None,
    ) -> None:
        """Inline source bodies + a deterrent ``next_step`` into the envelope.

        Best-effort: any failure leaves the bare-coordinate response intact
        rather than crashing the tool. The cache is reused from the finder.
        """
        from . import call_path_enrich as enrich

        finder = self._finder
        cache = bound_cache
        if cache is None and finder is not None:
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
                        project_root,
                        cache,
                        paths,
                        endpoint_hints,
                        source_reader=source_reader,
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
                if bodies
                else f"Path: {n} path(s) returned as coordinates; read source as needed."
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
                    source_reader=source_reader,
                )
            except Exception:  # pragma: no cover - defensive
                dead_end = {}
        result_dict["dead_end"] = dead_end
        has_body = any(
            isinstance(endpoint, dict) and "body" in endpoint
            for endpoint in dead_end.values()
        )
        # #1942: a name-keyed search does not track the calls it could not bind,
        # so its NO_PATH is not evidence of absence.
        result_dict["completeness"] = "unknown"
        result_dict["completeness_reason"] = NAME_KEYED_REASON
        result_dict["completeness_reasons"] = [NAME_KEYED_REASON]
        result_dict["next_step"] = (
            "No static path between these names; "
            + (
                "inspect certified endpoint bodies and neighbours. "
                if has_body
                else "inspect the endpoint coordinates and neighbours. "
            )
            + "This search matches functions by name and does not track unbound "
            "calls, so it is not evidence of absence: ask with `Class.method` "
            "endpoints for a definition search that reports its open sites."
        )
