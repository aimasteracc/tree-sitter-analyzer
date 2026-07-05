"""Canonical verdict vocabulary and normalisation for MCP tools.

F1 (round-37f7): extracted from base_tool to give the verdict vocabulary
a dedicated home with a minimal import surface. ``base_tool`` re-exports
``_LEGAL_VERDICTS`` and ``_canonicalize_verdict`` for backward
compatibility — all existing callers continue to work unchanged.

Why a frozenset and not an Enum: tools pass plain strings on the wire
(JSON has no enum); callers (CLI, hive-mind workers, Cursor, Cline)
branch on string equality. A flat frozenset keeps membership checks O(1)
and avoids a double-source-of-truth.
"""

from __future__ import annotations

from ...utils import setup_logger

logger = setup_logger(__name__)

# Canonical verdict vocabulary shared across every MCP tool + CLI surface.
# Must stay in sync with ``_N_VERDICT_VOCABULARY`` in
# ``tests/unit/mcp/tools/test_tool_response_contract.py``.
_LEGAL_VERDICTS: frozenset[str] = frozenset(
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

# Normalisation table for historical drift values. Keys are lowercased
# input; values are the canonical replacement.
_VERDICT_ALIASES: dict[str, str] = {
    "": "INFO",
    "n/a": "INFO",
    "na": "INFO",
    "success": "INFO",
    "clean": "SAFE",
    "ok": "SAFE",
    "warning": "WARN",
}


def _canonicalize_verdict(value: str | None) -> str:
    """Return a verdict guaranteed to belong to ``_LEGAL_VERDICTS``.

    F1 (round-37f7): a prior dogfood audit found at least five MCP
    tools emitting verdict values outside the canonical vocabulary —
    ``"n/a"`` (agent_workflow / call_graph / ast_cache),
    ``"CLEAN"`` (change_impact no-changes path), and various
    case-shifted spellings (``"warning"``, ``"ok"``). Downstream
    consumers — Claude Code, Cursor, Cline, the queue-ledger CLI —
    branch on the string, so drift becomes silent miscoordination.

    Behaviour:
        - ``None`` / empty / ``"success"`` / ``"n/a"`` / ``"na"`` → ``"INFO"``
        - ``"CLEAN"`` / ``"clean"`` / ``"ok"`` → ``"SAFE"``
        - ``"warning"`` → ``"WARN"``
        - Any value already in :data:`_LEGAL_VERDICTS` → returned
          unchanged (case-preserved).
        - Anything else → ``"INFO"`` with a logged warning. The
          fallback is deliberate: silent rejection (raising) would
          break tools mid-flight; silent acceptance (returning the bad
          value) would re-introduce the bug class. Logging gives ops a
          breadcrumb without taking the response surface down.

    The function never raises — it always returns a string that lives
    in :data:`_LEGAL_VERDICTS`.
    """
    if value is None:
        return "INFO"
    # Defensive runtime check: the signature says ``str | None`` but
    # callers have historically passed integers / booleans by accident.
    raw_value: object = value
    if not isinstance(raw_value, str):
        logger.warning(
            "F1: _canonicalize_verdict received non-string %r — falling back to INFO",
            raw_value,
        )
        return "INFO"
    # Case-preserved fast path for already-legal values.
    if value in _LEGAL_VERDICTS:
        return value
    alias = _VERDICT_ALIASES.get(value.lower().strip())
    if alias is not None:
        return alias
    logger.warning(
        "F1: _canonicalize_verdict received unknown verdict %r — falling back to INFO. "
        "Legal vocabulary: %s",
        value,
        sorted(_LEGAL_VERDICTS),
    )
    return "INFO"


# Public alias required by REQ-3-001.
normalize_verdict = _canonicalize_verdict

__all__ = [
    "_LEGAL_VERDICTS",
    "_VERDICT_ALIASES",
    "_canonicalize_verdict",
    "normalize_verdict",
]
