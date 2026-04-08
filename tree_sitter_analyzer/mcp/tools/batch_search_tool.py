#!/usr/bin/env python3
"""
batch_search MCP Tool

Execute multiple ripgrep searches simultaneously in parallel.
"""

from __future__ import annotations

from typing import Any

from . import fd_rg_utils
from .base_tool import BaseMCPTool

_BATCH_MAX_MATCHES_PER_QUERY = 20


class BatchSearchTool(BaseMCPTool):
    """MCP tool that runs multiple ripgrep searches concurrently."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "batch_search",
            "description": (
                "Execute multiple ripgrep searches simultaneously in parallel — significantly "
                "faster than calling search_content multiple times sequentially.\n\n"
                "WHEN TO USE:\n"
                "- When you need to search for 3 or more different patterns at once (e.g., find "
                "all usages of Class A, Class B, and Class C in one operation)\n"
                "- When exploring a codebase and need multiple cross-cutting searches simultaneously\n"
                "- When refactoring and need to verify several symbol usages at once\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For a single search — use search_content instead (no parallel overhead)\n"
                "- For two searches — the overhead is not worth it; use search_content twice\n"
                "- Do not use this as a substitute for find_and_grep when you need file-type "
                "filtering first\n"
                "\n"
                "IMPORTANT: Each query in the batch runs independently. Results are returned "
                "together once all searches complete. Maximum 10 queries per batch."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "description": "List of search queries to execute in parallel",
                        "items": {
                            "type": "object",
                            "properties": {
                                "pattern": {
                                    "type": "string",
                                    "description": "Regex or literal pattern to search for",
                                },
                                "label": {
                                    "type": "string",
                                    "description": "Human-readable label for this search (for organizing results)",
                                },
                                "roots": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Directories to search in",
                                },
                                "literal": {
                                    "type": "boolean",
                                    "description": "If true, treat pattern as literal string (not regex)",
                                },
                                "case_sensitive": {
                                    "type": "boolean",
                                    "description": "Case sensitive search",
                                },
                            },
                            "required": ["pattern"],
                        },
                        "minItems": 2,
                        "maxItems": 10,
                    }
                },
                "required": ["queries"],
                "additionalProperties": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        queries = arguments.get("queries")
        if not isinstance(queries, list):
            raise ValueError("queries must be an array")
        if len(queries) < 2:
            raise ValueError(
                "batch_search requires at least 2 queries; use search_content for a single search"
            )
        if len(queries) > 10:
            raise ValueError("batch_search supports at most 10 queries per batch")
        for i, q in enumerate(queries):
            if not isinstance(q, dict):
                raise ValueError(f"queries[{i}] must be an object")
            if "pattern" not in q or not isinstance(q["pattern"], str) or not q["pattern"]:
                raise ValueError(f"queries[{i}].pattern must be a non-empty string")
        return True

    def _build_command_for_query(self, query: dict[str, Any]) -> list[str]:
        """Build a ripgrep command for a single query dict."""
        pattern: str = query["pattern"]
        literal: bool = bool(query.get("literal", False))
        case_sensitive: bool | None = query.get("case_sensitive")
        roots: list[str] | None = query.get("roots")

        # Resolve case mode
        if case_sensitive is True:
            case = "sensitive"
        elif case_sensitive is False:
            case = "insensitive"
        else:
            case = "smart"

        # Resolve roots: validate each if provided, else default to project_root or cwd
        resolved_roots: list[str] = []
        if roots:
            for r in roots:
                try:
                    resolved_roots.append(self.resolve_and_validate_directory_path(r))
                except ValueError:
                    resolved_roots.append(r)
        elif self.project_root:
            resolved_roots = [self.project_root]

        return fd_rg_utils.build_rg_command(
            query=pattern,
            case=case,
            fixed_strings=literal,
            word=False,
            multiline=False,
            include_globs=None,
            exclude_globs=None,
            follow_symlinks=False,
            hidden=False,
            no_ignore=False,
            max_filesize=None,
            context_before=None,
            context_after=None,
            encoding=None,
            max_count=None,
            timeout_ms=None,
            roots=resolved_roots if resolved_roots else None,
            files_from=None,
        )

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute all queries in parallel and aggregate results."""
        self.validate_arguments(arguments)

        queries: list[dict[str, Any]] = arguments["queries"]

        # Build commands for all queries
        commands: list[list[str]] = [self._build_command_for_query(q) for q in queries]

        # Run all commands in parallel
        raw_results = await fd_rg_utils.run_parallel_rg_searches(
            commands, timeout_ms=fd_rg_utils.DEFAULT_RG_TIMEOUT_MS
        )

        # Process each result
        query_results: list[dict[str, Any]] = []
        total_matches = 0

        for query, (rc, stdout, _stderr) in zip(queries, raw_results, strict=True):
            pattern: str = query["pattern"]
            label: str = query.get("label", pattern)

            if rc in (0, 1):
                matches = fd_rg_utils.parse_rg_json_lines_to_matches(stdout)
            else:
                matches = []

            match_count = len(matches)
            total_matches += match_count

            truncated = match_count > _BATCH_MAX_MATCHES_PER_QUERY
            display_matches = matches[:_BATCH_MAX_MATCHES_PER_QUERY]

            query_results.append(
                {
                    "label": label,
                    "pattern": pattern,
                    "match_count": match_count,
                    "matches": display_matches,
                    "truncated": truncated,
                }
            )

        return {
            "queries": query_results,
            "total_matches": total_matches,
            "execution_note": f"{len(queries)} searches executed in parallel",
        }
