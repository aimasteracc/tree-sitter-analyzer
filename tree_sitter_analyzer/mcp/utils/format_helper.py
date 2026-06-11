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


#: RFC-0012 Phase 2: dict keys whose value is a dict but must NOT be stripped
#: by the value-kind bulk rule.  These are small, structurally stable dicts
#: that consumers branch on directly without parsing ``toon_content``.
#:
#: ``agent_summary`` — injected by the MCP boundary's
#: ``ensure_canonical_success_envelope``; kept here so the tool-level
#: ``apply_toon_format_to_response`` call (before the boundary runs) preserves
#: it for any caller that reads the raw execute() result.
#:
#: ``errors_summary`` — batch executor control signal ``{"errors": N}``;
#: agents branch on error count without parsing the blob. ~13 B.
#:
#: ``limits`` — batch executor configuration dict ``{"max_files": N, ...}``;
#: agents inspect request limits without parsing the blob. ~96 B.
TOON_DICT_PASSTHROUGH: frozenset[str] = frozenset(
    {
        "agent_summary",
        "errors_summary",
        "limits",
    }
)


#: Known large-string fields that are already encoded in ``toon_content`` and
#: must be stripped from the top level.  These cannot be caught by the
#: value-kind rule (which only fires on lists/dicts) because their value is
#: a ``str``.  Keep this list minimal — strings are cheap; only include fields
#: where the string is a large rendered artefact (diagram text, table output,
#: raw file content).
TOON_LARGE_STRING_FIELDS: frozenset[str] = frozenset(
    {
        "content",  # Raw file content (read_partial_tool, extract_code_section)
        "mermaid",  # Mermaid diagram string (viz action=uml / action=graph)
        "partial_content_result",  # Formatted partial file content (read_partial_tool)
        "table_output",  # Formatted table output (legacy text blob)
    }
)


def _copy_metadata_fields(
    result: dict[str, Any],
    toon_response: dict[str, Any],
) -> None:
    """Copy non-bulk metadata fields from result into toon_response.

    RFC-0012 Phase 2 — value-kind rule (replaces per-name denylist):

    * Skip any key whose value is a **non-empty list** — it is already encoded
      inside ``toon_content`` and keeping it at top level doubles the payload.
    * Skip any key whose value is a **non-empty dict** UNLESS the key is in
      :data:`TOON_DICT_PASSTHROUGH` — same rationale.
    * Skip keys in :data:`TOON_LARGE_STRING_FIELDS` — known large rendered
      strings (mermaid diagrams, table output) that are already in
      ``toon_content``.
    * Empty lists/dicts pass through (near-zero cost; shape-stable).
    * All other scalars (str, int, float, bool, None) pass through.
    * The ``format``/``toon_content`` keys are internal and never copied.

    This approach is **future-proof**: any new tool field that emits a bulk
    list or dict is automatically stripped, regardless of its name.  The old
    per-name denylist had been extended 6 times and still missed fields
    (direct_callers, transitive_callers, risk, subclasses — issue #439).
    """
    for key, value in result.items():
        if key in {"format", "toon_content"}:
            continue
        if key in TOON_LARGE_STRING_FIELDS:
            # Known large-string artefacts — strip regardless of value type
            continue
        if isinstance(value, list) and value:
            # Non-empty list → bulk data, strip it
            continue
        if isinstance(value, dict) and value and key not in TOON_DICT_PASSTHROUGH:
            # Non-empty dict not in the passthrough set → bulk data, strip it
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

    When output_format is 'toon', formats the result as TOON and strips all
    non-empty list/dict fields from the top level (RFC-0012 Phase 2 value-kind
    rule) — they are already encoded inside ``toon_content`` and duplicating
    them doubles the payload.  Only scalars and the small
    :data:`TOON_DICT_PASSTHROUGH` dicts survive alongside ``toon_content`` so
    callers can branch on ``success``/``verdict``/``error`` without parsing the
    TOON blob.

    RFC-0012 Phase 1: when ``compact_only`` is True, the TOON response is
    further reduced to :data:`TOON_CONTROL_SURFACE` (plus ``toon_content``),
    dropping even the passthrough dicts.  Note: on the MCP server path the
    canonical post-hook re-adds ``agent_summary`` and ``summary_line``, so the
    boundary re-applies :func:`reduce_to_control_surface` (idempotent) — see
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
        # Format the full result as TOON (encodes the full payload once).
        toon_content = format_as_toon(result)

        toon_response = {
            "format": "toon",
            "toon_content": toon_content,
        }

        # RFC-0012 Phase 2 — value-kind rule: copy only scalars and the small
        # passthrough dicts; strip all non-empty lists and non-passthrough
        # non-empty dicts (they are already inside toon_content).
        _copy_metadata_fields(result, toon_response)

        # RFC-0012 Phase 1: opt-in compaction strips the metadata that is
        # already inside toon_content, leaving only the branchable control
        # surface.
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
