"""Typed envelope for MCP tool responses (ARCH-A5).

Every ``BaseMCPTool.execute()`` returns a JSON-serialisable dict. Before
this module the shape was governed by convention only: ``success`` was
expected to exist, ``error`` *might* exist on failures, payload keys
were tool-specific. External consumers (Claude Code, Cursor, Cline, and
the project's own CLI) end up depending on this implicit shape, which
means any tool quietly changing it breaks downstream parsers.

Goals
-----

* **Document** the response contract that 23 MCP tools already follow.
* **Enforce** the minimum invariants (``success`` is bool; if False,
  ``error`` is a str) via a contract test that introspects every tool.
* **Don't** force every tool to wrap its payload in a ``data`` key —
  back-compat with the current consumers is more valuable than a
  prettier envelope. The TypedDict is intentionally permissive (other
  keys allowed via ``__extra_items__`` in spirit; we just type the
  guaranteed ones).

Usage
-----

A tool's ``execute()`` may still return a plain ``dict[str, Any]``.
The TypedDict is the *recommended* annotation when you want call-site
type-checking, e.g.::

    async def execute(self, args: dict[str, Any]) -> ToolResponse:
        return {"success": True, "payload": {...}}
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    # No runtime cost — just for the contract test's introspection.
    pass


#: Canonical verdict vocabulary used across every tsa-landing-eligible
#: tool. Agents branching on verdict expect EXACTLY one of these strings —
#: anything else (CLEAN, LOOKS_GOOD, READY, etc.) silently falls through
#: to default-INFO behavior and turns into a real bug at the agent layer.
CANONICAL_VERDICTS: frozenset[str] = frozenset(
    {
        "SAFE",
        "CAUTION",
        "REVIEW",
        "UNSAFE",
        "INFO",
        "WARN",
        "ERROR",
        "NOT_FOUND",
    }
)


class ToolResponse(TypedDict, total=False):
    """The shape every MCP tool response should follow.

    All keys are optional in the TypedDict sense so partial dicts still
    type-check, but the contract test below makes ``success`` mandatory
    for runtime acceptance.
    """

    success: bool
    """Whether the tool ran end-to-end without raising. Mandatory."""

    verdict: str
    """Canonical agent-facing verdict for branching. MUST be one of the
    strings in :data:`CANONICAL_VERDICTS`. Optional today (the contract
    test only requires it when the key is present and rejects non-canonical
    values), but every landing-surface tool now sets it."""

    error: str
    """Human-readable failure description. MUST be present when
    ``success`` is False; absent when ``success`` is True."""

    mode: str
    """Optional sub-mode label for tools that expose multiple modes
    (e.g. detect_routes has summary/all/lookup/prefix/file)."""


def validate_tool_response(payload: Any, tool_name: str = "<unknown>") -> None:
    """Raise ``AssertionError`` if ``payload`` doesn't honour the
    ``ToolResponse`` minimum invariants.

    The contract test calls this on every tool's actual response. It is
    deliberately a hard ``AssertionError`` (not ``ValueError``) because
    the only legitimate caller is pytest.
    """
    assert isinstance(payload, dict), (
        f"{tool_name}: ToolResponse must be a dict, got {type(payload).__name__}"
    )
    assert "success" in payload, (
        f"{tool_name}: ToolResponse must include a 'success' key"
    )
    success = payload["success"]
    assert isinstance(success, bool), (
        f"{tool_name}: ToolResponse['success'] must be bool, got "
        f"{type(success).__name__}"
    )
    if not success:
        # Failures MUST surface an error. Successes may omit one entirely.
        assert "error" in payload, (
            f"{tool_name}: ToolResponse with success=False must include 'error'"
        )
        assert isinstance(payload["error"], str), (
            f"{tool_name}: ToolResponse['error'] must be str, got "
            f"{type(payload['error']).__name__}"
        )
    # When ``verdict`` is present it MUST be a canonical value. Tools that
    # emit non-canonical strings (CLEAN, NEEDS_REVIEW, LOOKS_GOOD, READY,
    # ...) cause silent agent miscoordination — pains #9, #93 in the UX log.
    if "verdict" in payload:
        verdict = payload["verdict"]
        assert isinstance(verdict, str), (
            f"{tool_name}: ToolResponse['verdict'] must be str, got "
            f"{type(verdict).__name__}"
        )
        assert verdict in CANONICAL_VERDICTS, (
            f"{tool_name}: ToolResponse['verdict']={verdict!r} is not in "
            f"the canonical set {sorted(CANONICAL_VERDICTS)}"
        )


#: ``completeness`` values an agent may branch on (RFC-0040 / RFC-0041).
COMPLETENESS_STATUSES: frozenset[str] = frozenset({"complete", "incomplete", "unknown"})

#: Verdicts a ``success: False`` response may carry. A failure that says
#: ``SAFE`` or ``INFO`` tells an agent that branches on ``verdict`` to proceed.
FAILURE_VERDICTS: frozenset[str] = frozenset({"ERROR", "NOT_FOUND"})

#: ``(total, listed)`` integer pairs: when both are present and the total is
#: larger, the response listed fewer items than exist and must not claim
#: ``truncated: False``.
TRUNCATION_COUNT_PAIRS: tuple[tuple[str, str], ...] = (
    ("total_count", "returned_count"),
    ("total_matches", "returned_matches"),
    ("caller_count", "callers_listed"),
)

#: Every rule name :func:`envelope_violations` can report.
ENVELOPE_RULES: frozenset[str] = frozenset(
    {
        "base",
        "agent-summary-shape",
        "verdict-canonical",
        "verdict-mirror",
        "failure-verdict",
        "success-verdict",
        "error-code",
        "completeness-status",
        "completeness-reasons",
        "completeness-reason-code",
        "truncation",
    }
)

#: ``truncated``-style flags that must be booleans when present.
_TRUNCATION_FLAGS: tuple[str, ...] = ("truncated", "skipped_files_truncated")


def _real(value: Any) -> str | None:
    """A verdict string that is actually set (``n/a`` is the unset placeholder)."""
    return value if isinstance(value, str) and value and value != "n/a" else None


@functools.cache
def known_completeness_reasons() -> frozenset[str]:
    """The closed set of completeness reason codes producers may emit.

    Imported lazily: the reason vocabularies live next to their producers
    (``nav action=callers``, the unified query language and the index
    snapshot) and this module must stay importable without them.
    """
    from ...index_completeness import INDEX_COMPLETENESS_REASONS
    from ...uql.coverage import UQL_REASONS
    from .callers_reasons import COMPLETENESS_REASONS

    return frozenset(COMPLETENESS_REASONS | UQL_REASONS | INDEX_COMPLETENESS_REASONS)


def _verdict_violations(payload: dict[str, Any]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    top = _real(payload.get("verdict"))
    summary = payload.get("agent_summary")
    if summary is not None and not isinstance(summary, dict):
        found.append(
            (
                "agent-summary-shape",
                f"agent_summary must be a dict, got {type(summary).__name__}",
            )
        )
        summary = None
    inner = _real(summary.get("verdict")) if summary else None
    if inner is not None and inner not in CANONICAL_VERDICTS:
        found.append(
            ("verdict-canonical", f"agent_summary.verdict={inner!r} is not canonical")
        )
    if top is not None and inner is not None and top != inner:
        found.append(
            ("verdict-mirror", f"verdict={top!r} but agent_summary.verdict={inner!r}")
        )
    effective = top or inner
    success = payload.get("success")
    if success is False and effective is not None and effective not in FAILURE_VERDICTS:
        found.append(
            (
                "failure-verdict",
                f"success=False with verdict={effective!r}; expected one of "
                f"{sorted(FAILURE_VERDICTS)}",
            )
        )
    if success is True and effective == "ERROR":
        found.append(("success-verdict", "success=True with verdict='ERROR'"))
    return found


def _error_code_violations(payload: dict[str, Any]) -> list[tuple[str, str]]:
    if payload.get("success") is not False:
        return []
    for key in ("error_code", "error_type"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return []
    return [
        (
            "error-code",
            "success=False without a machine-readable error_code/error_type",
        )
    ]


def _completeness_violations(payload: dict[str, Any]) -> list[tuple[str, str]]:
    if "completeness" not in payload:
        return []
    status = payload["completeness"]
    if status not in COMPLETENESS_STATUSES:
        return [
            (
                "completeness-status",
                f"completeness={status!r} is not one of {sorted(COMPLETENESS_STATUSES)}",
            )
        ]
    reasons = payload.get("completeness_reasons")
    primary = payload.get("completeness_reason")
    if reasons is not None and not isinstance(reasons, list):
        return [("completeness-reasons", "completeness_reasons must be a list")]
    listed = list(reasons or [])
    if primary is not None and not listed:
        listed = [primary]
    found: list[tuple[str, str]] = []
    if status == "complete" and listed:
        found.append(
            (
                "completeness-reasons",
                f"completeness='complete' carries reasons {listed}",
            )
        )
    if status != "complete" and not listed:
        found.append(
            ("completeness-reasons", f"completeness={status!r} names no reason code")
        )
    if primary is not None and reasons and primary != reasons[0]:
        found.append(
            (
                "completeness-reasons",
                f"completeness_reason={primary!r} is not completeness_reasons[0]",
            )
        )
    known = known_completeness_reasons()
    # UQL reports pipeline-level reasons as ``<stage>:<CODE>``; the code
    # after the stage prefix must still come from the known set.
    unknown = sorted({str(r) for r in listed if str(r).rpartition(":")[2] not in known})
    if unknown:
        found.append(
            ("completeness-reason-code", f"unknown completeness reason codes {unknown}")
        )
    return found


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _truncation_violations(payload: dict[str, Any]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for flag in _TRUNCATION_FLAGS:
        if flag in payload and not isinstance(payload[flag], bool):
            found.append(
                (
                    "truncation",
                    f"{flag} must be bool, got {type(payload[flag]).__name__}",
                )
            )
    truncated = payload.get("truncated")
    for total_key, listed_key in TRUNCATION_COUNT_PAIRS:
        total = _count(payload.get(total_key))
        listed = _count(payload.get(listed_key))
        if total is None or listed is None:
            continue
        if listed > total:
            found.append(
                ("truncation", f"{listed_key}={listed} exceeds {total_key}={total}")
            )
        elif listed < total and truncated is False:
            found.append(
                (
                    "truncation",
                    f"truncated=False but {listed_key}={listed} < {total_key}={total}",
                )
            )
    return found


def envelope_violations(
    payload: Any, tool_name: str = "<unknown>"
) -> list[tuple[str, str]]:
    """Every envelope rule ``payload`` breaks, as ``(rule, message)`` pairs.

    Runs :func:`validate_tool_response` (rule ``base``) and the agent-envelope
    rules on top of it: verdict / ``agent_summary`` consistency, a machine
    code on failure, completeness reason codes from the known set, and
    truncation fields that agree with the counts beside them. Returns an
    empty list for a conforming response; never raises.
    """
    try:
        validate_tool_response(payload, tool_name)
    except AssertionError as error:
        return [("base", str(error))]
    return [
        *_verdict_violations(payload),
        *_error_code_violations(payload),
        *_completeness_violations(payload),
        *_truncation_violations(payload),
    ]


__all__ = [
    "CANONICAL_VERDICTS",
    "COMPLETENESS_STATUSES",
    "ENVELOPE_RULES",
    "FAILURE_VERDICTS",
    "TRUNCATION_COUNT_PAIRS",
    "ToolResponse",
    "envelope_violations",
    "known_completeness_reasons",
    "validate_tool_response",
]
