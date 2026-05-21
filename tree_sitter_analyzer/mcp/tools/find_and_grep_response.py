"""Response builders for find_and_grep result modes."""

from __future__ import annotations

from typing import Any

from ..utils.format_helper import (
    apply_toon_format_to_response,
    attach_toon_content_to_response,
)
from . import fd_rg_utils
from .find_and_grep_agent_summary import (
    build_agent_summary_from_meta,
    count_match_files,
)
from .find_and_grep_helpers import handle_output
from .search_envelope import normalize_envelope


class FindAndGrepRespondMixin:
    """Build response payloads for grouped, summary, and full match modes."""

    file_output_manager: Any

    def _respond_grouped(
        self,
        arguments: dict[str, Any],
        matches: list[dict[str, Any]],
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        """Return matches grouped by file path."""
        grouped = fd_rg_utils.group_matches_by_file(matches)
        if arguments.get("summary_only", False):
            grouped["summary"] = fd_rg_utils.summarize_search_results(matches)
        grouped["meta"] = meta
        grouped["output_format"] = arguments.get("output_format", "toon")
        grouped["agent_summary"] = build_agent_summary_from_meta(
            arguments,
            mode="group_by_file",
            count=len(matches),
            meta=meta,
            file_count=count_match_files(matches),
        )
        normalize_envelope(grouped, total_count=len(matches))

        suppressed = handle_output(
            grouped, arguments, self.file_output_manager, matches
        )
        if suppressed:
            return normalize_envelope(suppressed)

        output_format = arguments.get("output_format", "toon")
        if output_format == "toon":
            return attach_toon_content_to_response(grouped)
        return grouped

    def _respond_summary(
        self,
        arguments: dict[str, Any],
        matches: list[dict[str, Any]],
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a summary-only response without full match data."""
        result: dict[str, Any] = {
            "success": True,
            "summary_only": True,
            "count": len(matches),
            "results": [],
            "summary": fd_rg_utils.summarize_search_results(matches),
            "meta": meta,
            "output_format": arguments.get("output_format", "toon"),
            "agent_summary": build_agent_summary_from_meta(
                arguments,
                mode="summary",
                count=len(matches),
                meta=meta,
                file_count=count_match_files(matches),
            ),
        }
        normalize_envelope(result, total_count=len(matches))

        suppressed = handle_output(result, arguments, self.file_output_manager, matches)
        if suppressed:
            return normalize_envelope(suppressed)

        return result

    def _respond_full(
        self,
        arguments: dict[str, Any],
        matches: list[dict[str, Any]],
        meta: dict[str, Any],
        output_format: str,
    ) -> dict[str, Any]:
        """Return full match results with optional next_steps."""
        result: dict[str, Any] = {
            "success": True,
            "count": len(matches),
            "meta": meta,
            "output_format": output_format,
            "agent_summary": build_agent_summary_from_meta(
                arguments,
                mode="normal",
                count=len(matches),
                meta=meta,
                file_count=count_match_files(matches),
            ),
        }

        suppress_output = arguments.get("suppress_output", False)
        output_file = arguments.get("output_file")

        if not (suppress_output and output_file):
            result["results"] = matches
            if matches and not suppress_output:
                result["next_steps"] = _build_next_steps(matches)

        normalize_envelope(result, total_count=len(matches))

        suppressed = handle_output(result, arguments, self.file_output_manager, matches)
        if suppressed:
            return normalize_envelope(suppressed)

        return apply_toon_format_to_response(result, output_format)


def _build_next_steps(matches: list[dict[str, Any]]) -> list[str]:
    """Build next_steps suggestions for AI agents."""
    files_with_matches: set[str] = set()
    for match in matches:
        file_path = match.get("file") or match.get("path", {})
        if isinstance(file_path, dict):
            file_path = file_path.get("text", "")
        if file_path:
            files_with_matches.add(file_path)

    steps: list[str] = []
    if len(files_with_matches) == 1:
        file_path = next(iter(files_with_matches))
        steps.append(
            f"analyze_code_structure(file_path='{file_path}') to see full structure"
        )
    elif len(files_with_matches) <= 3:
        steps.append("check_code_scale on matching files to prioritize analysis")
    if len(matches) > 5:
        steps.append("Use group_by_file=true for a clearer overview")
    return steps
