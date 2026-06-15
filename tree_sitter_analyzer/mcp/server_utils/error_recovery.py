"""AI-agent-friendly error recovery hints and canonical error envelope builder.

This module is the **central path** for shaping every error response that
leaves the MCP server. The previous version produced a 4-field response
(``success``/``error``/``error_type``/``recovery_hint``); we now extend it to
the full canonical envelope every tool's success path also produces:

    {
        "success": False,
        "error": "<plain message>",
        "error_type": "<machine kind>",         # validation / file_not_found / ...
        "verdict": "ERROR",                      # top-level mirror (Wave 1a) —
                                                 # equals agent_summary.verdict
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
        "The file does not exist at the given path. Verify the path or use project action=files to discover files.",
        "project action=files",
    ),
    (
        "no such file",
        "file_not_found",
        "The file does not exist at the given path. Verify the path or use project action=files to discover files.",
        "project action=files",
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
        # #668: blast_radius's "function_names is required ..." message contains
        # "required", so it must precede the generic "required" rule below or the
        # agent-facing recovery_hint/next_step loses the file-level xref guidance.
        "blast_radius mode",
        "validation",
        "blast_radius needs function_names (a list of function names). For file-level dependents, use nav action=xref mode=file instead.",
        "nav action=xref mode=file",
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
        # invalid_enum_error() format (#449): "Invalid <param>: '<got>'.
        # Valid values: a, b, c" — the enumerated message already tells the
        # agent what to send; the hint just points back at it.
        "valid values:",
        "validation",
        "A parameter has an invalid value. The error message lists the valid values — pick one and retry.",
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
        # Wave 1a (audit search-01/viz-01/project-02): mirror verdict to the
        # TOP LEVEL — not just inside agent_summary — so an agent reading
        # ``result["verdict"]`` (the r37w contract) gets a value on errors,
        # exactly as it does on the success path.
        "verdict": "ERROR",
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
    "verdict",  # Wave 1a: top-level verdict is now part of the canonical shape
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


def _ensure_language_echo(
    response: dict[str, Any], arguments: dict[str, Any] | None
) -> None:
    """Ensure single-file responses echo ``language: <detected>`` (M14).

    Round-26 dogfood found ``refactor`` and ``file_health`` returning
    ``language: None`` on ``.ts`` files even though both apply TypeScript-
    specific analysis internally. ``analyze_scale`` echoes the detected
    language correctly — agents that cross-checked the two saw a
    contradiction. We detect-and-echo here so every tool that runs on a
    single file converges on the same lowercase language string without
    each tool having to add its own per-call snippet.

    Skip rules:
    - response already carries a non-empty ``language`` (tool emitted it).
    - response has no ``file_path`` echo (we have nothing to detect from).
    - detection returns ``unknown`` — leave the key unset so callers can
      branch on ``language is None`` without ambiguity.
    """
    # Tool already echoed a usable language — don't overwrite.
    existing = response.get("language")
    if isinstance(existing, str) and existing and existing != "unknown":
        return

    file_path_value = response.get("file_path")
    if not isinstance(file_path_value, str) or not file_path_value:
        # Fall back to the request argument when the tool didn't echo
        # ``file_path`` (rare, but keeps the hook from breaking edge cases).
        if isinstance(arguments, dict):
            arg_value = arguments.get("file_path")
            if isinstance(arg_value, str) and arg_value:
                file_path_value = arg_value
        if not isinstance(file_path_value, str) or not file_path_value:
            return

    try:
        from ...language_detector import detect_language_from_file

        detected = detect_language_from_file(file_path_value)
    except Exception:  # nosec B110 — language detection is best-effort
        return

    if not detected or detected == "unknown":
        # Don't write a misleading value — leave the key absent.
        return

    response["language"] = detected


def ensure_canonical_success_envelope(
    tool_name: str,
    response: dict[str, Any],
    *,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Augment a tool's success-path response with the canonical envelope keys.

    r37bu (dogfood): tool flagged this at 110 lines. Refactor extracts
    each of the 4 envelope steps into a focused helper. Behaviour
    preserved (Finding 6 / K12 / M14 / M10 contracts all intact).
    """
    if response.get("success") is False:
        # Errors flow through ensure_canonical_error_envelope instead.
        return response

    # K12: normalize echoed file_path so ``./X`` and ``X`` produce
    # byte-identical responses (downstream dedup/caching/display).
    _normalize_echoed_file_path(response)

    # M14: every single-file tool echoes ``language: <detected>``.
    _ensure_language_echo(response, arguments)

    summary_line_value = _populate_summary_line(response, tool_name, arguments)
    agent_summary = _populate_agent_summary_block(response, summary_line_value)

    # M10: mirror verdict between top-level and agent_summary.
    _mirror_verdict(response, agent_summary)

    # Final default: if neither side set ``verdict`` (and mirror found
    # nothing to copy), populate the agent-side with ``"n/a"`` so the
    # envelope shape stays stable.
    agent_summary.setdefault("verdict", "n/a")
    return response


# #672/#678: the no-identifier summary-line suffix is "ok" ONLY for success-like
# verdicts (or an absent verdict). Every other canonical verdict — WARN, ERROR,
# NOT_FOUND, CAUTION, REVIEW, UNSAFE, and anything added later — gets its own
# lowercased suffix, via an ALLOWLIST (not a denylist), so a new non-success
# verdict can never silently synthesize a lying "<tool>: ok" (Codex #678 P2:
# viz action=similarity can return CAUTION/REVIEW with no identifier).
_SUCCESS_LIKE_VERDICTS: frozenset[str] = frozenset({"INFO", "SAFE", "OK", "SUCCESS"})


def _verdict_suffix(response: dict[str, Any]) -> str:
    """Pick the no-identifier summary-line suffix from the response verdict.

    Reads the top-level ``verdict`` first, then ``agent_summary.verdict``.
    Returns ``"ok"`` for a success-like or absent verdict; otherwise the
    verdict lowercased (``NOT_FOUND`` -> ``"not found"``).
    """
    verdict = response.get("verdict")
    if not isinstance(verdict, str) or not verdict:
        agent_summary = response.get("agent_summary")
        if isinstance(agent_summary, dict):
            verdict = agent_summary.get("verdict")
    if not isinstance(verdict, str) or not verdict or verdict in _SUCCESS_LIKE_VERDICTS:
        return "ok"
    return verdict.lower().replace("_", " ")


def _populate_summary_line(
    response: dict[str, Any],
    tool_name: str,
    arguments: dict[str, Any] | None,
) -> str:
    """Mirror agent_summary.summary_line → top-level, or synthesize when both missing.

    r37bu: extracted from ``ensure_canonical_success_envelope``. Returns
    the final ``summary_line`` value (always a non-empty string).
    """
    agent_summary = response.get("agent_summary")
    current = response.get("summary_line")

    # Step 1: mirror agent_summary.summary_line → top-level if missing.
    if (not isinstance(current, str) or not current) and isinstance(
        agent_summary, dict
    ):
        candidate = agent_summary.get("summary_line")
        if isinstance(candidate, str) and candidate:
            response["summary_line"] = candidate
            return candidate

    if isinstance(current, str) and current:
        return current

    # Step 2: synthesize from tool_name + the most informative identifier.
    identifier_value: str | None = None
    for key in _IDENTIFIER_FIELDS:
        val = response.get(key)
        if isinstance(val, str) and val:
            identifier_value = val
            break
    if identifier_value is None:
        _identifier_key, identifier_value = _pick_identifier(arguments)
    if identifier_value:
        synthesized = f"{tool_name}: {identifier_value}"
    else:
        # #672: the fallback suffix MUST reflect the verdict — saying "ok" on a
        # WARN/ERROR/NOT_FOUND response (e.g. index action=status with an empty
        # cache) lies to an agent that gates on summary_line. Only success-like
        # verdicts (or none) get "ok".
        synthesized = f"{tool_name}: {_verdict_suffix(response)}"
    response["summary_line"] = synthesized
    return synthesized


def _populate_agent_summary_block(
    response: dict[str, Any], summary_line_value: str
) -> dict[str, Any]:
    """Ensure ``agent_summary`` is a dict with mirrored summary_line + next_step.

    r37bu: extracted from ``ensure_canonical_success_envelope``. Does NOT
    default ``verdict`` — that runs after the M10 mirror so a single-side
    population gets copied correctly before the n/a fallback.
    """
    agent_summary = response.get("agent_summary")
    if not isinstance(agent_summary, dict):
        agent_summary = {}
    agent_summary.setdefault("summary_line", summary_line_value)
    # Wave 1b batch B (audit nav-03/04, search-05, project-03, viz-05, health-04):
    # many tools set a rich TOP-LEVEL ``next_step`` but leave
    # ``agent_summary.next_step`` empty. Mirror the top-level value into the
    # agent_summary (the documented place agents read) rather than defaulting to
    # "" — only when agent_summary has no real next_step of its own.
    if not agent_summary.get("next_step"):
        top_next = response.get("next_step")
        agent_summary["next_step"] = (
            top_next if isinstance(top_next, str) and top_next else ""
        )
    response["agent_summary"] = agent_summary
    return agent_summary


def _real_verdict(value: Any) -> str | None:
    """Return ``value`` only if it is a *real* verdict.

    ``"n/a"`` is the canonical post-hook placeholder for "no verdict set"
    (see :func:`_mirror_verdict`), so it — like ``""``/``None`` — counts as
    missing. Keeps the error-path verdict resolution consistent with the
    success-path mirror logic.
    """
    return value if isinstance(value, str) and value and value != "n/a" else None


def _mirror_verdict(response: dict[str, Any], agent_summary: dict[str, Any]) -> None:
    """Mirror ``verdict`` between top-level and ``agent_summary`` (M10).

    Behaviour table::

        top         agent       → outcome
        ---         -----       --------
        ""/None     "X"         top = "X"
        "X"         ""/None     agent = "X"
        "X"         "n/a"       agent = "X"  (treat ``n/a`` as missing)
        "n/a"       "X"         top = "X"    (treat ``n/a`` as missing)
        ""/None     ""/None     leave (caller defaults to ``n/a`` later)
        "X"         "Y"         leave both (intentional divergence)
    """
    top_value = response.get("verdict")
    agent_value = agent_summary.get("verdict")
    # ``n/a`` is the post-hook's stable placeholder — treat it as "not
    # really set" so a tool that emits a real verdict at one surface
    # still mirrors over the placeholder at the other surface.
    top_is_real = isinstance(top_value, str) and top_value and top_value != "n/a"
    agent_is_real = (
        isinstance(agent_value, str) and agent_value and agent_value != "n/a"
    )
    if top_is_real and not agent_is_real:
        agent_summary["verdict"] = top_value
        return
    if agent_is_real and not top_is_real:
        response["verdict"] = agent_value


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
    # Wave 1a (audit search-01/viz-01/project-02): verdict must be present at
    # BOTH the top level and in agent_summary, and the two must agree. Prefer
    # a real verdict the tool already set (top level first, then agent_summary)
    # so a specific verdict like NOT_FOUND is preserved; the "n/a" placeholder
    # counts as missing (consistent with _mirror_verdict); otherwise ERROR.
    verdict = (
        _real_verdict(response.get("verdict"))
        or _real_verdict(agent_summary.get("verdict"))
        or "ERROR"
    )
    response["verdict"] = verdict
    agent_summary["verdict"] = verdict
    response["agent_summary"] = agent_summary

    return response
