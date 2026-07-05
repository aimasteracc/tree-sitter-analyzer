"""ToolResponse envelope factory + verdict validation (ARCH-A5 follow-up).

Why this exists
---------------
Every MCP tool today hand-rolls a ``{"success": ..., "verdict": ..., ...}``
dict at the end of ``execute()``. The contract test
(:func:`tree_sitter_analyzer.mcp.tools.tool_response.validate_tool_response`)
catches non-canonical verdict strings at *runtime*, but only when a test
actually executes the tool. A bug landed for months in
``codegraph_visualize`` (it returned ``verdict='OK'`` instead of canonical
``INFO``) because no test exercised that specific code path — the
contract sweep didn't know about the tool yet, and the dogfood pass that
eventually surfaced it ran weeks later.

The factory in this module makes the same class of bug impossible at
*construction* time: passing a non-canonical verdict to
:func:`build_response` raises :class:`InvalidVerdictError` immediately,
not next time someone runs the right test.

Goals
-----

* Validate verdict strings at build time, not at the next test sweep.
* Stay 100% back-compatible — the envelope shape is unchanged. Tools
  that migrate keep returning the same JSON-serialisable dict.
* Make the failure message actionable. Tell the caller which verdict
  they tried, what's canonical, and which helper to use for errors.

Usage
-----

::

    from ._response_builder import build_response, build_error

    return build_response(
        verdict="INFO",
        mode=mode,
        callees=entries,
        callee_count=len(entries),
    )

    # Or for failures:
    return build_error(error="Project root not set", verdict="ERROR")
"""

from __future__ import annotations

from typing import Any

#: Single source of truth for the verdict vocabulary. Mirrors
#: :data:`tree_sitter_analyzer.mcp.tools.tool_response.CANONICAL_VERDICTS`
#: — the two MUST stay in sync. We re-declare here (rather than import)
#: so the factory has no incoming dependency on the validator, keeping
#: this module a leaf in the import graph.
CANONICAL_VERDICTS: frozenset[str] = frozenset(
    {
        "SAFE",
        "REVIEW",
        "CAUTION",
        "UNSAFE",
        "INFO",
        "WARN",
        "ERROR",
        "NOT_FOUND",
    }
)


class InvalidVerdictError(ValueError):
    """Raised when a tool tries to emit a verdict outside the canonical set.

    Inherits ``ValueError`` so callers that ``except ValueError`` for
    argument validation also catch this. The factory is the only known
    raise site; tools that pass a canonical string never see it.
    """


def build_response(
    *,
    verdict: str,
    success: bool = True,
    warnings: list[str] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Construct a tool response envelope with verdict validation.

    Args:
        verdict: must be a member of :data:`CANONICAL_VERDICTS`. Anything
            else (``"OK"``, lowercase ``"safe"``, empty string, ...) is
            rejected with :class:`InvalidVerdictError`.
        success: ``True`` for normal returns, ``False`` for failures.
            Failure responses should also set ``error=<str>`` via
            ``**fields``; :func:`build_error` is the convenience wrapper.
        warnings: optional list of human-readable warning strings (e.g.
            stale-cache hints). The key is omitted entirely when the list
            is empty or ``None`` so the envelope stays minimal.
        **fields: tool-specific payload keys, merged into the envelope.
            Order: ``success`` and ``verdict`` come first so the
            JSON-serialised form is reader-friendly; everything else
            follows in insertion order.

    Returns:
        ``{"success": <bool>, "verdict": <str>, [<warnings>?,] **fields}``

    Raises:
        InvalidVerdictError: if ``verdict`` is not in
            :data:`CANONICAL_VERDICTS`. The message names the bad string
            and lists the canonical set, so the caller can fix the
            verdict directly without grepping for the definition.
    """
    if verdict not in CANONICAL_VERDICTS:
        raise InvalidVerdictError(
            f"verdict={verdict!r} not in canonical set "
            f"{sorted(CANONICAL_VERDICTS)}. "
            f"Use build_error() for error responses."
        )
    envelope: dict[str, Any] = {"success": success, "verdict": verdict, **fields}
    if warnings:
        envelope["warnings"] = list(warnings)
    return envelope


def build_error(
    *,
    error: str,
    verdict: str = "ERROR",
    **fields: Any,
) -> dict[str, Any]:
    """Construct an error envelope with default ``verdict="ERROR"``.

    Args:
        error: human-readable failure description (required). Becomes
            the ``error`` field of the envelope.
        verdict: usually ``"ERROR"`` (default) but ``"NOT_FOUND"`` is
            valid for "looked but didn't find" failures. Validated the
            same way as :func:`build_response`.
        **fields: extra payload keys (e.g. ``mode``, ``available_functions``).

    Returns:
        ``{"success": False, "verdict": <str>, "error": <str>, **fields}``
    """
    return build_response(verdict=verdict, success=False, error=error, **fields)


def build_error_response(
    tool_name: str,
    error: str,
    verdict: str = "ERROR",
    **fields: Any,
) -> dict[str, Any]:
    """Construct an error envelope with ``tool_name`` included.

    Args:
        tool_name: the MCP tool name; included as ``tool`` in the envelope.
        error: human-readable failure description.
        verdict: usually ``"ERROR"`` (default) or ``"NOT_FOUND"``.
        **fields: extra payload keys merged into the envelope.

    Returns:
        ``{"success": False, "verdict": <str>, "tool": <str>, "error": <str>, **fields}``
    """
    return build_error(error=error, verdict=verdict, tool=tool_name, **fields)


def build_success_response(
    tool_name: str,
    data: dict[str, Any],
    verdict: str = "INFO",
    duration_ms: float | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Construct a success envelope with ``tool_name`` and optional timing.

    Args:
        tool_name: the MCP tool name; included as ``tool`` in the envelope.
        data: tool-specific payload dict, merged into the envelope.
        verdict: canonical verdict string (default ``"INFO"``).
        duration_ms: optional wall-clock execution time in milliseconds.
        **fields: extra payload keys merged after ``data``.

    Returns:
        ``{"success": True, "verdict": <str>, "tool": <str>, [**data], [duration_ms?,] **fields}``
    """
    extra: dict[str, Any] = {"tool": tool_name, **data, **fields}
    if duration_ms is not None:
        extra["duration_ms"] = duration_ms
    return build_response(verdict=verdict, **extra)


def build_agent_summary(
    verdict: str,
    message: str,
    recommendations: list[str] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Construct an agent-readable summary envelope.

    Args:
        verdict: canonical verdict string (e.g. ``"INFO"``, ``"WARN"``).
        message: human/agent-readable summary message.
        recommendations: optional list of actionable recommendation strings.
        **fields: extra payload keys merged into the envelope.

    Returns:
        ``{"success": True, "verdict": <str>, "message": <str>, [recommendations?,] **fields}``
    """
    extra: dict[str, Any] = {"message": message, **fields}
    if recommendations:
        extra["recommendations"] = list(recommendations)
    return build_response(verdict=verdict, **extra)


__all__ = [
    "CANONICAL_VERDICTS",
    "InvalidVerdictError",
    "build_response",
    "build_error",
    "build_error_response",
    "build_success_response",
    "build_agent_summary",
]
