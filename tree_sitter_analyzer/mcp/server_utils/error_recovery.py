"""AI-agent-friendly error recovery hints and canonical error envelope builder.

This module is the **central path** for shaping every error response that
leaves the MCP server. The previous version produced a 4-field response
(``success``/``error``/``error_type``/``recovery_hint``); we now extend it to
the full canonical envelope every tool's success path also produces:

    {
        "success": False,
        "error": "<plain message>",
        "error_type": "<machine kind>",         # validation / file_not_found / ...
        "agent_summary": {
            "summary_line": "<one line>",
            "next_step":    "<concrete suggestion>",
            "verdict":      "ERROR",
        },
        "summary_line": "<mirror of agent_summary.summary_line>",
        # Plus identifying fields when available — file_path, symbol, query, roots.
    }

Two public entry points:

* :func:`build_agent_friendly_error` — called when a tool raises an exception
  inside ``handle_call_tool``. Converts the exception into the envelope.
* :func:`ensure_canonical_error_envelope` — called when a tool *returns* a
  ``{success: False, ...}`` dict (find_and_grep, refactoring_suggestions,
  read_partial, query, search_content). Augments it with missing canonical
  keys without dropping any tool-specific fields it already set.

The previous fields (``error_category``, ``recovery_hint``, ``suggested_tool``)
are preserved for backward compatibility, but agents should now branch on
``error_type`` + ``agent_summary``.
"""

from typing import Any

from ..utils.error_sanitizer import (
    project_root_from_env,
    safe_error_message,
)

# (substring, error_type, recovery_hint, suggested_tool)
_ERROR_RECOVERY_HINTS: list[tuple[str, str, str, str]] = [
    (
        "not found",
        "file_not_found",
        "The file does not exist at the given path. Verify the path or use list_files to discover files.",
        "list_files",
    ),
    (
        "no such file",
        "file_not_found",
        "The file does not exist at the given path. Verify the path or use list_files to discover files.",
        "list_files",
    ),
    (
        "unsupported language",
        "language_unsupported",
        "The file extension is not recognized. Check supported languages with --show-supported-languages.",
        "",
    ),
    (
        "project root",
        "project_not_set",
        "Project root has not been set. Call set_project_path first.",
        "set_project_path",
    ),
    (
        "outside project boundary",
        "security_violation",
        "The file is outside the project boundary. Use a path relative to the project root.",
        "",
    ),
    (
        "required",
        "validation",
        "A required parameter is missing. Check the tool schema and provide all required fields.",
        "",
    ),
    (
        "must be",
        "validation",
        "A parameter has an invalid value. Check the tool schema for valid options.",
        "",
    ),
    (
        "memory",
        "resource_exhausted",
        "The operation ran out of memory. Try analyzing a smaller scope or use suppress_output=true.",
        "",
    ),
    (
        "timed out",
        "timeout",
        "The operation timed out. Try reducing the scope (limit, max_count) or targeting a specific file.",
        "",
    ),
    (
        "regex parse error",
        "subprocess",
        "The regex pattern is invalid. Use a valid pattern or pass `glob=True` to match literal globs.",
        "",
    ),
    (
        "permission denied",
        "permission_denied",
        "Permission denied. Check file ownership and that the path is under project_root.",
        "",
    ),
]

# Tool-specific identifier-field maps (mirror of success-path identifiers so
# the envelope carries enough context for the agent to retry/diagnose).
_IDENTIFIER_FIELDS: tuple[str, ...] = ("file_path", "symbol", "query", "roots", "mode")

# Map Python exception class names to canonical machine-readable error_type.
# Anything not listed falls back to ``internal``.
_EXC_CLASS_TO_TYPE: dict[str, str] = {
    "FileNotFoundError": "file_not_found",
    "NotADirectoryError": "file_not_found",
    "IsADirectoryError": "validation",
    "PermissionError": "permission_denied",
    "ValueError": "validation",
    "TypeError": "validation",
    "KeyError": "validation",
    "IndexError": "validation",
    "TimeoutError": "timeout",
    "AnalysisError": "internal",
    "MCPError": "internal",
    "RuntimeError": "internal",
    "OSError": "internal",
    "AttributeError": "internal",
}


def _classify(
    error_msg: str, error_type_hint: str | None = None
) -> tuple[str, str, str]:
    """Pick (error_type, recovery_hint, suggested_tool) for a given message.

    Message text always wins — an "outside project boundary" message becomes
    ``security_violation`` even when raised as a ``ValueError``. The exception
    class is only used as a fallback when no rule matches.
    """
    msg = error_msg.lower()
    for pattern, et, hint, tool in _ERROR_RECOVERY_HINTS:
        if pattern in msg:
            return et, hint, tool
    # Fallback: map exception class name through the canonical table.
    if error_type_hint:
        canonical = _EXC_CLASS_TO_TYPE.get(error_type_hint, "internal")
        return canonical, "Review the error message and adjust your request.", ""
    return "internal", "Review the error message and adjust your request.", ""


def _summary_line(tool_name: str, error_type: str, identifier: str | None) -> str:
    if identifier:
        return f"{tool_name}: {error_type} — {identifier}"
    return f"{tool_name}: {error_type}"


def _pick_identifier(arguments: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """Pull the most informative (key, value) identifier from arguments.

    Order: file_path → symbol → query → first root → mode.
    """
    if not isinstance(arguments, dict):
        return None, None
    for key in _IDENTIFIER_FIELDS:
        val = arguments.get(key)
        if isinstance(val, str) and val:
            return key, val
        if key == "roots" and isinstance(val, list) and val:
            first = val[0]
            if isinstance(first, str) and first:
                return "roots", first
    return None, None


def _build_envelope(
    *,
    tool_name: str,
    error_msg: str,
    error_type: str,
    recovery_hint: str,
    suggested_tool: str,
    identifier_key: str | None,
    identifier_value: str | None,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose the canonical envelope from already-resolved fields."""
    summary_line = _summary_line(tool_name, error_type, identifier_value)
    body: dict[str, Any] = {
        "success": False,
        "error": error_msg,
        "error_type": error_type,
        # Backward-compatible alias kept for callers that pinned this name.
        "error_category": error_type,
        "recovery_hint": recovery_hint,
        "agent_summary": {
            "summary_line": summary_line,
            "next_step": recovery_hint,
            "verdict": "ERROR",
        },
        "summary_line": summary_line,
    }
    if suggested_tool:
        body["suggested_tool"] = suggested_tool
    if identifier_key and identifier_value is not None:
        # Mirror the identifier as a top-level field so agents can branch on
        # the same field name they see on the success path.
        body[identifier_key] = identifier_value
    if extras:
        # Don't let extras stomp on canonical keys — preserve everything else.
        for key, value in extras.items():
            body.setdefault(key, value)
    return body


def build_agent_friendly_error(
    tool_name: str,
    error: Exception,
    *,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical error envelope for an exception raised by a tool.

    Called from the MCP server boundary (``handle_call_tool``) when a tool's
    ``execute`` raises. The ``arguments`` parameter is optional but, when
    provided, lets the envelope mirror the identifying input field
    (``file_path``/``symbol``/``query``/``roots``/``mode``) onto the response.
    """
    error_msg = safe_error_message(error, project_root_from_env())
    error_type_hint = type(error).__name__
    # Heuristic classification by message text, with the exception class as
    # fallback hint when no rule fires.
    error_type, recovery_hint, suggested_tool = _classify(error_msg, error_type_hint)

    identifier_key, identifier_value = _pick_identifier(arguments)

    return _build_envelope(
        tool_name=tool_name,
        error_msg=error_msg,
        error_type=error_type,
        recovery_hint=recovery_hint,
        suggested_tool=suggested_tool,
        identifier_key=identifier_key,
        identifier_value=identifier_value,
    )


_CANONICAL_KEYS: tuple[str, ...] = (
    "success",
    "error",
    "error_type",
    "agent_summary",
    "summary_line",
)

# K12: keys that carry an echoed file_path that should be normalized so
# ``./X`` and ``X`` produce byte-identical responses. ``file_path`` is the
# canonical name; ``source_file`` is the trace_impact alias; ``path`` is
# kept narrow on purpose (lots of unrelated dicts use "path" for non-file
# values, so we only touch the keys we know reach the response root).
_FILE_PATH_ECHO_KEYS: tuple[str, ...] = ("file_path", "source_file")


def _normalize_path_string(raw: str) -> str:
    """Strip leading ``./`` and convert separators for K12 echo parity.

    Mirrors :meth:`BaseMCPTool._normalize_file_path` so the central
    dispatch post-hook normalizes the same way as direct callers.
    """
    if not isinstance(raw, str) or not raw:
        return raw
    normalized = raw.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _normalize_echoed_file_path(response: dict[str, Any]) -> None:
    """Normalize echoed ``file_path`` / ``source_file`` in place (K12)."""
    for key in _FILE_PATH_ECHO_KEYS:
        value = response.get(key)
        if isinstance(value, str) and value:
            normalized = _normalize_path_string(value)
            if normalized != value:
                response[key] = normalized


def ensure_canonical_success_envelope(
    tool_name: str,
    response: dict[str, Any],
    *,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Augment a tool's success-path response with the canonical envelope keys.

    Finding 6: round-16b dogfood showed that 7 tools were returning responses
    with ``summary_line=None`` (FileHealthTool, RefactoringSuggestionsTool,
    SmartContextTool, AnalyzeCodeStructureTool, ProjectOverviewTool,
    CodeGraphCallTool, ProjectHealthTool). Some emit ``agent_summary`` but
    never mirror its ``summary_line`` to the top level; others omit
    ``agent_summary`` entirely.

    Run this at the MCP-server dispatch boundary, after a tool's
    ``execute`` returns and before the result is JSON-serialised. It is
    purely additive — if the tool already populated ``summary_line`` or
    ``agent_summary`` we keep its value.

    Skips:
    - error responses (``success is False``) — those flow through
      :func:`ensure_canonical_error_envelope` instead.
    - TOON-formatted blobs (``format == 'toon'``) — those are already
      shipped as ``toon_content`` plus the metadata copy.
    """
    # Errors handled by the error envelope path.
    if response.get("success") is False:
        return response

    # K12: normalize echoed file_path so ``./X`` and ``X`` produce
    # byte-identical responses. Pre-K12 the raw argument was echoed
    # unchanged — same content_hash, different file_path string, which
    # confused downstream dedup/caching/display layers.
    _normalize_echoed_file_path(response)

    agent_summary = response.get("agent_summary")
    summary_line_value = response.get("summary_line")

    # Step 1: mirror agent_summary.summary_line → top-level if missing.
    if not isinstance(summary_line_value, str) or not summary_line_value:
        if isinstance(agent_summary, dict):
            candidate = agent_summary.get("summary_line")
            if isinstance(candidate, str) and candidate:
                response["summary_line"] = candidate
                summary_line_value = candidate

    # Step 2: synthesize a minimal summary_line + agent_summary when the
    # tool didn't produce either. Use tool name + the most informative
    # identifier from the response or arguments.
    if not isinstance(summary_line_value, str) or not summary_line_value:
        identifier_key: str | None = None
        identifier_value: str | None = None
        for key in _IDENTIFIER_FIELDS:
            val = response.get(key)
            if isinstance(val, str) and val:
                identifier_key, identifier_value = key, val
                break
        if identifier_value is None:
            identifier_key, identifier_value = _pick_identifier(arguments)
        synthesized = (
            f"{tool_name}: {identifier_value}"
            if identifier_value
            else f"{tool_name}: ok"
        )
        response["summary_line"] = synthesized
        summary_line_value = synthesized

    # Step 3: ensure agent_summary is at least a dict with the
    # mirrored summary_line and a generic next_step.
    if not isinstance(agent_summary, dict):
        agent_summary = {}
    agent_summary.setdefault("summary_line", summary_line_value)
    agent_summary.setdefault("next_step", "")
    agent_summary.setdefault("verdict", "n/a")
    response["agent_summary"] = agent_summary

    return response


def ensure_canonical_error_envelope(
    tool_name: str,
    response: dict[str, Any],
    *,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Augment a tool's existing ``{success: False, ...}`` dict in place.

    Tools that already return their own error dict (find_and_grep,
    refactoring_suggestions, read_partial, query, search_content) flow
    through here so we don't lose their tool-specific fields (returncode,
    available_keys, suggestions, etc.) while still getting the canonical
    envelope keys (``error_type``, ``agent_summary``, ``summary_line``).
    """
    if response.get("success") is not False:
        return response

    error_msg = response.get("error") or response.get("message") or "Unknown error"
    if not isinstance(error_msg, str):
        error_msg = str(error_msg)

    error_type = response.get("error_type")
    if not isinstance(error_type, str) or not error_type:
        error_type, recovery_hint, suggested_tool = _classify(error_msg)
    else:
        # error_type is already set — re-classify to fill recovery_hint only.
        _, recovery_hint, suggested_tool = _classify(error_msg, error_type)

    # Find an identifier — prefer values already on the response, then
    # fall back to the request arguments.
    identifier_key: str | None = None
    identifier_value: str | None = None
    for key in _IDENTIFIER_FIELDS:
        val = response.get(key)
        if isinstance(val, str) and val:
            identifier_key, identifier_value = key, val
            break
        if key == "roots" and isinstance(val, list) and val:
            first = val[0]
            if isinstance(first, str) and first:
                identifier_key, identifier_value = "roots", first
                break
    if identifier_key is None:
        identifier_key, identifier_value = _pick_identifier(arguments)

    summary_line = response.get("summary_line")
    if not isinstance(summary_line, str) or not summary_line:
        summary_line = _summary_line(tool_name, error_type, identifier_value)
        response["summary_line"] = summary_line

    response.setdefault("error_type", error_type)
    response.setdefault("error_category", error_type)
    response.setdefault("recovery_hint", recovery_hint)
    if suggested_tool:
        response.setdefault("suggested_tool", suggested_tool)
    if identifier_key and identifier_value is not None:
        response.setdefault(identifier_key, identifier_value)

    agent_summary = response.get("agent_summary")
    if not isinstance(agent_summary, dict):
        agent_summary = {}
    agent_summary.setdefault("summary_line", summary_line)
    agent_summary.setdefault("next_step", recovery_hint)
    agent_summary.setdefault("verdict", "ERROR")
    response["agent_summary"] = agent_summary

    return response
