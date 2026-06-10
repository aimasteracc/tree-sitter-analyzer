#!/usr/bin/env python3
"""
Format Helper for MCP Tools

Provides utility functions for formatting MCP tool output in different formats
(JSON, TOON) with consistent behavior across all tools.
"""

import json
from typing import Any

from ...utils import setup_logger

logger = setup_logger(__name__)


#: RFC-0012: the minimal scalar control surface an agent branches on WITHOUT
#: parsing the ``toon_content`` blob. Everything else in a TOON response is
#: recoverable from ``toon_content``, so under ``compact_only`` we keep only
#: these keys alongside the blob and drop the duplicated metadata.
#:
#: ``summary_line`` is included deliberately: the MCP boundary's
#: ``ensure_canonical_success_envelope`` re-populates it on every success
#: anyway (so dropping it is futile), it is a single cheap scalar, and it is
#: the highest-value one-line triage signal.
TOON_CONTROL_SURFACE: frozenset[str] = frozenset(
    {
        "success",
        "format",
        "toon_content",
        "verdict",
        "error",
        "error_type",
        "output_format",
        "summary_line",
        # Cheap branchable identifiers/affordances an agent should not have to
        # parse the TOON blob for (review nit): the recovery ``hint`` on error
        # envelopes is the sharpest edge; ``file_path`` / ``pr_url`` /
        # ``pr_number`` echo the call's subject.
        "hint",
        "file_path",
        "pr_url",
        "pr_number",
        # The legacy-shim migration warning (legacy_shim.dispatch_legacy injects
        # ``deprecation`` AFTER the facade built toon_content). It is the shim's
        # only in-band signal for agents that cannot read server stderr, so it
        # must survive compaction (Codex P2 #393).
        "deprecation",
    }
)


def reduce_to_control_surface(result: dict[str, Any]) -> dict[str, Any]:
    """Drop TOON-response metadata already encoded inside ``toon_content``.

    RFC-0012 Phase 1. Keeps only :data:`TOON_CONTROL_SURFACE` keys (plus the
    ``toon_content`` blob). It is a no-op unless ``result`` is a TOON response
    (``format == "toon"``), and it is **idempotent** — applying it twice equals
    applying it once — so it is safe to run both inside a tool's ``execute`` and
    again at the MCP boundary after canonical-envelope normalization re-adds
    metadata.
    """
    if not isinstance(result, dict) or result.get("format") != "toon":
        return result
    return {k: v for k, v in result.items() if k in TOON_CONTROL_SURFACE}


def format_output(data: dict[str, Any], output_format: str = "json") -> str:
    """
    Format data according to the specified output format.

    Args:
        data: Dictionary data to format
        output_format: Output format ('json' or 'toon')

    Returns:
        Formatted string representation of the data
    """
    if output_format == "toon":
        return format_as_toon(data)
    else:
        return format_as_json(data)


def format_as_json(data: dict[str, Any]) -> str:
    """
    Format data as JSON string.

    Args:
        data: Dictionary data to format

    Returns:
        JSON formatted string
    """
    return json.dumps(data, indent=2, ensure_ascii=False)


def format_as_toon(data: dict[str, Any]) -> str:
    """
    Format data as TOON string.

    Args:
        data: Dictionary data to format

    Returns:
        TOON formatted string
    """
    try:
        from ...formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        return formatter.format(data)
    except ImportError as e:
        logger.warning("ToonFormatter not available, falling back to JSON: %s", e)
        return format_as_json(data)
    except Exception as e:
        logger.warning("TOON formatting failed, falling back to JSON: %s", e)
        return format_as_json(data)


def _get_formatter_for_toon() -> Any:
    """Return ToonFormatter or JsonFormatter fallback on import failure."""
    try:
        from ...formatters.toon_formatter import ToonFormatter

        return ToonFormatter()
    except ImportError:
        logger.warning("ToonFormatter not available, using JSON formatter")
        return JsonFormatter()


def get_formatter(output_format: str = "json") -> Any:
    """
    Get a formatter instance for the specified format.

    Args:
        output_format: Output format ('json' or 'toon')

    Returns:
        Formatter instance with format() method
    """
    if output_format == "toon":
        return _get_formatter_for_toon()
    return JsonFormatter()


class JsonFormatter:
    """Simple JSON formatter implementing the format() interface."""

    def format(self, data: Any) -> str:
        """Format data as JSON string."""
        return json.dumps(data, indent=2, ensure_ascii=False)


def apply_output_format(
    result: dict[str, Any],
    output_format: str = "json",
    return_formatted_string: bool = False,
) -> dict[str, Any] | str:
    """
    Apply output format to a result dictionary.

    This function can either:
    1. Return the original dict (for MCP protocol compatibility)
    2. Return a formatted string (for file output or direct display)

    Args:
        result: Result dictionary from MCP tool execution
        output_format: Output format ('json' or 'toon')
        return_formatted_string: If True, return formatted string instead of dict

    Returns:
        Either the original dict or a formatted string
    """
    if return_formatted_string:
        return format_output(result, output_format)
    else:
        # For MCP protocol, we return the dict as-is
        # The format is applied when saving to file or displaying
        return result


def format_for_file_output(
    data: dict[str, Any], output_format: str = "json"
) -> tuple[str, str]:
    """
    Format data for file output and return content with appropriate extension.

    Args:
        data: Dictionary data to format
        output_format: Output format ('json' or 'toon')

    Returns:
        Tuple of (formatted_content, file_extension)
    """
    if output_format == "toon":
        content = format_as_toon(data)
        extension = ".toon"
    else:
        content = format_as_json(data)
        extension = ".json"

    return content, extension


def _copy_metadata_fields(
    result: dict[str, Any],
    toon_response: dict[str, Any],
    redundant_fields: set[str],
    conditionally_redundant_list_fields: set[str],
) -> None:
    """Copy non-redundant metadata fields from result into toon_response."""
    for key, value in result.items():
        if key in redundant_fields:
            continue
        if key in conditionally_redundant_list_fields and isinstance(value, list):
            # Only strip when the field is genuinely an array of
            # content; scalar aliases (int/str) pass through.
            continue
        if key in {"format", "toon_content"}:
            continue
        toon_response[key] = value


def apply_toon_format_to_response(
    result: dict[str, Any],
    output_format: str = "json",
    *,
    compact_only: bool = False,
) -> dict[str, Any]:
    """
    Apply TOON format to MCP tool response if requested.

    When output_format is 'toon', formats the result as TOON and removes
    redundant data fields (results, matches, content, etc.) to maximize
    token savings. Only metadata fields are preserved alongside toon_content
    so callers can still inspect ``success``/``error``/``file_path`` without
    parsing the TOON blob.

    RFC-0012 Phase 1: when ``compact_only`` is True, the TOON response is
    further reduced to :data:`TOON_CONTROL_SURFACE` (plus ``toon_content``),
    dropping metadata that is *already* encoded in the blob — eliminating the
    JSON/TOON duplication that made metadata-heavy responses larger than plain
    JSON. Default ``False`` preserves the legacy (duplicating) shape verbatim,
    so no existing caller or golden test changes until it opts in. Note: on the
    MCP server path the canonical post-hook re-adds metadata, so the boundary
    re-applies :func:`reduce_to_control_surface` (idempotent) — see
    ``handle_call_tool``.

    Also performs the verdict safety-net: if the tool returned a success
    response without a ``verdict`` field, INFO is injected so agents
    branching on verdict get a sane default rather than ``None``. Tools
    that already set verdict are left alone. Pain pass 4: this catches
    tools added by future contributors who forget the field.

    Args:
        result: Original result dictionary from MCP tool
        output_format: Output format ('json' or 'toon')
        compact_only: When True (and output is TOON), keep only the control
            surface alongside ``toon_content`` (RFC-0012).

    Returns:
        Modified result dict with TOON content if requested, otherwise original
    """
    # Verdict safety-net runs regardless of output_format so JSON callers
    # also see the default. Only inject when success is True; failure
    # responses are handled by the explicit ERROR branch in the validator.
    is_dict = isinstance(result, dict)
    is_success = is_dict and result.get("success") is True
    no_verdict = is_dict and "verdict" not in result
    if is_dict and is_success and no_verdict:
        result = {**result, "verdict": "INFO"}

    if output_format != "toon":
        return result

    try:
        # Format the full result as TOON
        toon_content = format_as_toon(result)

        # Drop only the redundant *data* fields — these are already present in
        # toon_content and would duplicate tokens. Metadata fields (success,
        # error, file_path, agent_summary, ...) stay so callers can branch on
        # status without parsing the TOON payload.
        redundant_fields = {
            "results",  # Search/query results
            "matches",  # Search matches
            "content",  # File content
            "partial_content_result",  # Partial read results
            "analysis_result",  # Code analysis results
            "data",  # Generic data field
            "items",  # List items
            "files",  # File listings
            "table_output",  # Formatted table output
        }
        # O4 (round-30): ``lines`` is treated as bulk *content* only when
        # it is actually a list/array (e.g. raw line content from
        # ``extract_code_section``). When a tool emits ``lines`` as a
        # scalar alias for ``line_count`` (N9 added this for file_health),
        # the field is metadata, not duplicated content — keep it so
        # JSON↔TOON callers see the same dict shape.
        conditionally_redundant_list_fields = {"lines"}

        toon_response = {
            "format": "toon",
            "toon_content": toon_content,
        }

        # Preserve metadata, but never stomp the format/toon_content keys.
        _copy_metadata_fields(
            result, toon_response, redundant_fields, conditionally_redundant_list_fields
        )

        # RFC-0012: opt-in compaction strips the metadata that is already inside
        # toon_content, leaving only the branchable control surface.
        if compact_only:
            return reduce_to_control_surface(toon_response)

        return toon_response

    except Exception as e:
        logger.warning("Failed to apply TOON format, returning JSON: %s", e)
        return result


def attach_toon_content_to_response(result: dict[str, Any]) -> dict[str, Any]:
    """
    Attach TOON formatted content to a response *without removing* any existing fields.

    This is useful for structured outputs (e.g. group_by_file) where callers/tests rely
    on the original JSON structure, while still allowing clients to display TOON.
    """
    try:
        toon_content = format_as_toon(result)
        enriched = result.copy()
        enriched["format"] = "toon"
        enriched["toon_content"] = toon_content
        return enriched
    except Exception as e:
        logger.warning("Failed to attach TOON content, returning JSON: %s", e)
        return result
