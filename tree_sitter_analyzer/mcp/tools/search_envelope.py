"""Shared envelope normalizer for search/navigation MCP tools.

Adds canonical top-level keys to a tool response without removing or
renaming any existing fields:

- ``displayed_count`` — ``len(results)``
- ``total_count``     — pre-truncation count if known, else mirrors ``count``
- ``elapsed_ms``      — hoisted from nested ``meta`` if missing at top level
- ``truncated``       — hoisted from nested ``meta`` if missing at top level
- ``summary_line``    — mirror of ``agent_summary.summary_line`` when present
- ``verdict``         — mirror of ``agent_summary.verdict`` when present (r37w)

This is purely additive: every existing key on the input dict survives.
"""

from __future__ import annotations

from typing import Any


def normalize_envelope(
    result: dict[str, Any],
    *,
    total_count: int | None = None,
    summary_line: str | None = None,
) -> dict[str, Any]:
    """Add canonical envelope aliases to ``result`` in place and return it.

    Parameters
    ----------
    result:
        The tool response dict. Mutated in place.
    total_count:
        Optional pre-truncation count. When ``None``, falls back to
        ``result["count"]`` and finally to ``len(result["results"])``.
    summary_line:
        Optional top-level summary line. When ``None``, uses
        ``result["agent_summary"]["summary_line"]`` if present.
    """
    results = result.get("results")
    if isinstance(results, list) and "displayed_count" not in result:
        result["displayed_count"] = len(results)

    if "total_count" not in result:
        if total_count is not None:
            result["total_count"] = total_count
        elif isinstance(result.get("count"), int):
            result["total_count"] = result["count"]
        elif isinstance(results, list):
            result["total_count"] = len(results)

    meta = result.get("meta") if isinstance(result.get("meta"), dict) else None
    if "elapsed_ms" not in result and meta is not None and "elapsed_ms" in meta:
        result["elapsed_ms"] = meta["elapsed_ms"]
    if "truncated" not in result and meta is not None and "truncated" in meta:
        result["truncated"] = bool(meta["truncated"])

    if "summary_line" not in result:
        if summary_line is not None:
            result["summary_line"] = summary_line
        else:
            agent_summary = result.get("agent_summary")
            if isinstance(agent_summary, dict) and isinstance(
                agent_summary.get("summary_line"), str
            ):
                result["summary_line"] = agent_summary["summary_line"]

    # r37w: top-level verdict mirror. The r37u envelope contract requires
    # ``result["verdict"]`` to equal ``result["agent_summary"]["verdict"]``
    # (not None) whenever the agent_summary carries a verdict. Doing it
    # in the central normalizer fixes the four search/navigation drifters
    # (search_content, query, find_and_grep, list_files) in one shot.
    if "verdict" not in result or result.get("verdict") is None:
        agent_summary = result.get("agent_summary")
        if isinstance(agent_summary, dict) and isinstance(
            agent_summary.get("verdict"), str
        ):
            result["verdict"] = agent_summary["verdict"]

    return result
