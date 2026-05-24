#!/usr/bin/env python3
"""
Query Command

Handles query execution functionality.
"""

from typing import Any

from ...core.query_service import QueryService
from ...output_manager import output_data, output_error, output_info, output_json
from .base_command import BaseCommand

# TOON formatter for CLI output
try:
    from ...formatters.toon_formatter import ToonFormatter

    _toon_available = True
except ImportError:
    _toon_available = False


class QueryCommand(BaseCommand):
    """Command for executing queries."""

    def __init__(self, args: Any) -> None:
        """Initialize the query command with QueryService."""
        super().__init__(args)
        self.query_service = QueryService()

    async def execute_query(
        self, language: str, query: str, query_name: str = "custom"
    ) -> list[dict] | None:
        """Execute a specific tree-sitter query using QueryService."""
        try:
            # Get filter expression if provided
            filter_expression = getattr(self.args, "filter", None)

            if query_name != "custom":
                # Use predefined query key
                results = await self.query_service.execute_query(
                    self.args.file_path,
                    language,
                    query_key=query_name,
                    filter_expression=filter_expression,
                )
            else:
                # Use custom query string
                results = await self.query_service.execute_query(
                    self.args.file_path,
                    language,
                    query_string=query,
                    filter_expression=filter_expression,
                )

            return results

        except Exception as e:
            output_error(f"Query execution failed: {e}")
            return None

    async def execute_async(self, language: str) -> int:
        """Run the requested query and emit the canonical response envelope.

        r37d7 (dogfood): 107 lines → ~20 lines of phase dispatch.
        Sub-helpers: ``_resolve_query`` (key vs. string, security checks),
        ``_build_query_envelope`` (r37ac canonical envelope) and
        ``_emit_query_results`` (json / toon / text fan-out).
        """
        query_resolution = self._resolve_query(language)
        if isinstance(query_resolution, int):
            return query_resolution
        query_to_execute, query_name = query_resolution

        results = await self.execute_query(language, query_to_execute, query_name)
        if results is None:
            return 1

        envelope = self._build_query_envelope(
            language=language,
            query_to_execute=query_to_execute,
            query_name=query_name,
            results=results,
        )
        self._emit_query_results(envelope, results)
        return 0

    def _resolve_query(self, language: str) -> tuple[str, str] | int:
        """Return ``(query_to_execute, query_name)`` or an exit code on error.

        Honours ``--query-key`` (validated against ``get_available_queries``)
        first, then ``--query-string`` (regex-checked via SecurityValidator).
        Returns an integer exit code (``1``) when no query is specified or
        validation fails — caller threads this back to the CLI return code.
        """
        if hasattr(self.args, "query_key") and self.args.query_key:
            sanitized_query_key = self.security_validator.sanitize_input(
                self.args.query_key, max_length=100
            )
            available_queries = self.query_service.get_available_queries(language)
            if sanitized_query_key not in available_queries:
                output_error(
                    f"Query '{sanitized_query_key}' not found for language '{language}'"
                )
                output_info(
                    f"Available queries: {', '.join(sorted(available_queries))}"
                )
                output_info("Use --list-queries to see all available query keys.")
                return 1
            return sanitized_query_key, sanitized_query_key
        if hasattr(self.args, "query_string") and self.args.query_string:
            is_safe, error_msg = self.security_validator.regex_checker.validate_pattern(
                self.args.query_string
            )
            if not is_safe:
                output_error(f"Unsafe query pattern: {error_msg}")
                return 1
            return self.args.query_string, "custom"
        output_error("No query specified.")
        return 1

    def _build_query_envelope(
        self,
        *,
        language: str,
        query_to_execute: str,
        query_name: str,
        results: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Wrap ``results`` in the r37ac canonical envelope.

        Previously ``--query-key`` emitted a bare list to stdout, causing
        agents calling ``result.get("verdict")`` to crash with
        ``AttributeError`` because ``list`` has no ``.get``. The envelope
        is the same shape produced by the other CLI surfaces (matches
        on r37y/r37z/r37aa).
        """
        match_count = len(results) if results else 0
        summary_line = (
            f"{self.args.file_path} ({language}) query="
            f"{query_name or query_to_execute[:40]}: "
            f"matches={match_count}"
        )
        return {
            "success": True,
            "file_path": self.args.file_path,
            "language": language,
            "query": query_name or query_to_execute,
            "results": results if results else [],
            "match_count": match_count,
            "summary_line": summary_line,
            "verdict": "INFO",
            "agent_summary": {
                "summary_line": summary_line,
                "next_step": (
                    "extract_code_section (MCP) on the listed line ranges to "
                    "read full bodies, or refine the query for fewer matches."
                ),
                "verdict": "INFO",
            },
        }

    def _emit_query_results(
        self,
        envelope: dict[str, Any],
        results: list[dict[str, Any]] | None,
    ) -> None:
        """Output ``envelope`` via json / toon / text per ``--output-format``."""
        if self.args.output_format == "json":
            output_json(envelope)
            return
        if self.args.output_format == "toon" and _toon_available:
            use_tabs = getattr(self.args, "toon_use_tabs", False)
            formatter = ToonFormatter(use_tabs=use_tabs)
            print(formatter.format(envelope))
            return
        if not results:
            output_info("\nINFO: No results found matching the query.")
            return
        for i, query_result in enumerate(results, 1):
            name = query_result.get("name")
            name_suffix = f": {name}" if name else ""
            output_data(
                f"\n{i}. {query_result['capture_name']}{name_suffix} "
                f"({query_result['node_type']})"
            )
            output_data(
                f"   Position: Line {query_result['start_line']}-"
                f"{query_result['end_line']}"
            )
            output_data(f"   Content:\n{query_result['content']}")
