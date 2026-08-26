#!/usr/bin/env python3
"""``health action=self`` / ``--self-health`` — RFC-0025 Layer 5.

Self-proprioception: the analyzer reporting how well it is sensing. Emits
per-``(tool, action)`` p50/p95 latency **split by tier**, exact invocation
counts, the in-process **analysis-cache** hit rate, and the on-disk **AST
index** state.

Two caches, two fields, deliberately not conflated:

* ``analysis_cache`` — the in-process ``cachetools`` L1/L2/L3 LRU/TTL cache
  held by :class:`UnifiedAnalysisEngine`. Has real hit/miss counters.
* ``ast_index`` — the on-disk ``.ast-cache/index.db``. Reports presence, size
  and indexed-file count; its ``hit_rate`` is ``null`` with
  ``hit_rate_status: UNAVAILABLE_NOT_INSTRUMENTED`` because the on-disk index
  keeps no hit/miss counters.

The first cut of this tool published the *analysis* cache's numbers under the
name ``ast_cache``. It was provably insensitive to the thing it named: with
``.ast-cache/`` deleted and with a 200 KB ``index.db`` present, the field
returned byte-identical values. A self-report that misnames what it senses is
a false-negative generator, not a health check.

Three honesty rules govern every field here:

1. **Never report a fabricated zero.** An unmeasured percentile is ``null``
   and the surrounding status is ``NO_OBSERVATIONS``. ``CacheService.get_stats()``
   returns ``hit_rate == 0.0`` for zero requests — that 0.0 is translated to
   ``null`` before it reaches a caller, because a zero that means "unmeasured"
   is exactly the belief-shaped output this surface exists to eliminate
   (CLAUDE.md §11). ``total_requests`` obeys the same rule: it is ``null``,
   never ``0``, when the cache could not be read.
2. **Never let a derived label read as a measurement.** The report carries
   ``tier_definition`` verbatim so ``cold``/``warm`` cannot be mistaken for a
   cache probe, and ``percentile_method`` so the numbers can be reproduced.
3. **Never emit a self-contradictory payload.** When two analysis engines are
   live under different spellings of one project root, the cache block reports
   ``status: AMBIGUOUS`` / ``reason: MULTIPLE_ENGINE_ROOTS`` rather than the
   zeros of whichever engine happened to be addressed.

Scope is the **current process** (``scope: "current_process"``). The recorder
has no persistence layer by design, so a fresh single-shot CLI process
honestly reports ``NO_OBSERVATIONS``; a long-lived MCP server accumulates
real observations, and ``scripts/measure_self_health_baseline.py`` drives
routes in-process to produce a durable baseline.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any

from ...latency import (
    NO_OBSERVATIONS,
    PERCENTILE_METHOD,
    TIER_DEFINITION,
    LatencySnapshot,
    get_latency_recorder,
)
from .base_tool import BaseMCPTool, format_summary_line, mirror_summary_line

#: Report scope. In-process only — see the module docstring.
SCOPE_CURRENT_PROCESS = "current_process"

_DESCRIPTION = (
    "Self-proprioception: how fast and how well THIS analyzer process is "
    "answering (RFC-0025 Layer 5). Returns per-(tool, action) p50/p95 "
    "latency split by tier (cold / warm / cached), exact invocation counts, "
    "the in-process analysis-cache hit rate, and the on-disk AST-index state "
    "(.ast-cache/index.db presence, size, indexed-file count).\n\n"
    "WHEN TO USE:\n"
    "- Before trusting any latency claim about this tool — this is the "
    "measurement, the README is the claim.\n"
    "- To decide whether a slow answer was a cold index build or a genuine "
    "regression (compare the cold vs warm tier rows).\n"
    "- After a long session, to see which routes are actually hot.\n"
    "\n"
    "WHEN NOT TO USE:\n"
    "- Not a project-quality grade — use action=project for that.\n"
    "- Not a cross-process history. Scope is the current process only; there "
    "is no persistence. A fresh CLI process reports NO_OBSERVATIONS, which is "
    "the honest answer, not a bug.\n"
    "\n"
    "HONESTY CONTRACT: an unmeasured percentile is `null` and the enclosing "
    "status is `NO_OBSERVATIONS` — never 0.0, never an estimate. `cold`/`warm` "
    "is a process-lifetime definition (see `tier_definition`), NOT a measured "
    "cache probe. `analysis_cache` is the in-process LRU/TTL cache; "
    "`ast_index` is the on-disk .ast-cache/index.db and its hit_rate is null "
    "(`UNAVAILABLE_NOT_INSTRUMENTED`) because that index keeps no hit/miss "
    "counters — the two are never substituted for each other.\n\n"
    "VERDICT INTEGRITY: agent_summary.verdict is INFO when observations exist "
    "and WARN when none do — no data must not read as a clean bill of health. "
    "Legal vocabulary: SAFE / CAUTION / REVIEW / UNSAFE / INFO / WARN / "
    "ERROR / NOT_FOUND."
)


def _unmeasured_cache(status: str, reason: str | None) -> dict[str, Any]:
    """Build an all-``None`` cache block.

    ``total_requests`` is ``None``, not ``0``: a zero here would be
    indistinguishable from a genuinely idle cache, which is the same
    fabricated-zero failure this module exists to eliminate. ``reason``
    distinguishes *unreadable* from *idle*.
    """
    return {
        "status": status,
        "reason": reason,
        "hit_rate": None,
        "hits": None,
        "misses": None,
        "total_requests": None,
    }


def _engine_root_conflict(project_root: str | None) -> str | None:
    """Detect two live analysis engines keyed on different spellings of one root.

    ``UnifiedAnalysisEngine.__new__`` keys its singleton on
    ``project_root or "default"`` with no normalisation, so ``'.'`` and the
    absolute path are *different* engines with *different* ``CacheService``
    instances. Reading the wrong one produces a self-contradictory payload:
    ``NO_OBSERVATIONS`` over a demonstrably busy cache.

    This only *detects* the disagreement and returns a stable reason code.
    Normalising the singleton key is a documented foundational change
    (CLAUDE.md §2 — it broke 164 tests on macOS when last attempted) and must
    land as its own commit with a macOS gate, never bundled here.
    """
    try:
        from ...core.analysis_engine import UnifiedAnalysisEngine

        keys = list(UnifiedAnalysisEngine._instances)  # noqa: SLF001 — read-only
    except Exception:  # noqa: BLE001 — a diagnostic must never raise
        return None
    if len(keys) < 2:
        return None
    mine = project_root or "default"
    target = os.path.realpath(project_root) if project_root else os.path.realpath(".")
    for key in keys:
        if key == mine:
            continue
        other = os.path.realpath(".") if key == "default" else os.path.realpath(key)
        if other == target:
            return "MULTIPLE_ENGINE_ROOTS"
    return None


def _per_root_cache_stats() -> list[dict[str, Any]]:
    """Per-engine cache counters, so an AMBIGUOUS verdict still carries data."""
    rows: list[dict[str, Any]] = []
    try:
        from ...core.analysis_engine import UnifiedAnalysisEngine

        instances = dict(UnifiedAnalysisEngine._instances)  # noqa: SLF001
    except Exception:  # noqa: BLE001 — a diagnostic must never raise
        return rows
    for key, engine in instances.items():
        entry: dict[str, Any] = {"root_key": key}
        try:
            stats = engine.get_cache_stats()
        except Exception as exc:  # noqa: BLE001
            entry["reason"] = f"CACHE_STATS_UNREADABLE:{type(exc).__name__}"
            rows.append(entry)
            continue
        if not stats:
            entry["reason"] = "CACHE_NOT_INITIALIZED"
            rows.append(entry)
            continue
        total = int(stats.get("total_requests") or 0)
        entry["hits"] = int(stats.get("hits") or 0)
        entry["misses"] = int(stats.get("misses") or 0)
        entry["total_requests"] = total
        entry["hit_rate"] = (
            round(int(stats.get("hits") or 0) / total, 4) if total > 0 else None
        )
        rows.append(entry)
    return sorted(rows, key=lambda row: str(row["root_key"]))


def _analysis_cache_report(project_root: str | None) -> dict[str, Any]:
    """Summarise the **in-process analysis cache** (``CacheService``).

    This is the ``cachetools`` L1/L2/L3 LRU/TTL cache held by
    :class:`UnifiedAnalysisEngine` — parse/analysis results for the current
    process. It is **NOT** the on-disk AST index; that is reported separately
    by :func:`_ast_index_report`. The two were conflated in the first cut of
    this tool: the field was named ``ast_cache`` while reading these numbers,
    and it was provably insensitive to whether ``.ast-cache/index.db`` existed
    at all.

    ``hit_rate`` is a fraction in ``[0, 1]`` rounded to 4 places. Upstream
    ``get_stats()`` reports ``0.0`` for zero requests; that fabricated zero is
    translated to ``None`` here.
    """
    conflict = _engine_root_conflict(project_root)
    if conflict is not None:
        # Reporting only "AMBIGUOUS" would be honest but useless. Carry the
        # per-root breakdown so the operator can see the real numbers behind
        # the ambiguity instead of having to reproduce it.
        ambiguous = _unmeasured_cache("AMBIGUOUS", conflict)
        ambiguous["roots"] = _per_root_cache_stats()
        return ambiguous
    try:
        from ...core.analysis_engine import get_analysis_engine

        stats = get_analysis_engine(project_root).get_cache_stats()
    except Exception as exc:  # noqa: BLE001 — a diagnostic must never raise
        return _unmeasured_cache(
            "UNAVAILABLE", f"CACHE_STATS_UNREADABLE:{type(exc).__name__}"
        )
    if not stats:
        return _unmeasured_cache("UNAVAILABLE", "CACHE_NOT_INITIALIZED")

    total = int(stats.get("total_requests") or 0)
    if total <= 0:
        return _unmeasured_cache(NO_OBSERVATIONS, "NO_REQUESTS_YET")
    hits = int(stats.get("hits") or 0)
    return {
        "status": "OK",
        "reason": None,
        "hit_rate": round(hits / total, 4),
        "hits": hits,
        "misses": int(stats.get("misses") or 0),
        "total_requests": total,
    }


def _ast_index_report(project_root: str | None) -> dict[str, Any]:
    """Report the real on-disk AST index (``.ast-cache/index.db``).

    What is genuinely cheap here is *existence*, *size* and *indexed file
    count* (one ``COUNT(*)`` on ``ast_index``). A hit rate is **not**
    available: the on-disk index keeps no hit/miss counters, so rather than
    substituting the in-process cache's rate — the exact mistake this block
    replaces — ``hit_rate`` is ``None`` with an explicit reason.
    """
    root = project_root or "."
    db_path = os.path.join(root, ".ast-cache", "index.db")
    report: dict[str, Any] = {
        "path": db_path,
        "present": False,
        "size_bytes": None,
        "indexed_files": None,
        "hit_rate": None,
        "hit_rate_status": "UNAVAILABLE_NOT_INSTRUMENTED",
    }
    if not os.path.isfile(db_path):
        report["status"] = "ABSENT"
        return report
    report["present"] = True
    try:
        report["size_bytes"] = os.path.getsize(db_path)
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = connection.execute("SELECT COUNT(*) FROM ast_index").fetchone()
        finally:
            connection.close()
        indexed = int(row[0]) if row else None
        report["indexed_files"] = indexed
        # "present but holding nothing" is a real and distinct state: this repo
        # ships a 200 KB schema-only index.db with ast_index empty. Calling that
        # OK would read as "warm" to an agent, which is the same false-negative
        # class as the misnamed field this block replaced.
        report["status"] = "EMPTY" if indexed == 0 else "OK"
    except Exception as exc:  # noqa: BLE001 — a diagnostic must never raise
        report["status"] = "UNREADABLE"
        report["reason"] = f"INDEX_UNREADABLE:{type(exc).__name__}"
    return report


class SelfHealthTool(BaseMCPTool):
    """MCP tool behind ``health action=self`` and the ``--self-health`` CLI flag."""

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "output_format": {
                    "type": "string",
                    "enum": ["json"],
                    "description": (
                        "Output format: 'toon' (default, token-efficient) or "
                        "'json'. The MCP-toon / CLI-json split is a locked "
                        "design decision (CLAUDE.md §1)."
                    ),
                    "default": "json",
                },
            },
            "additionalProperties": False,
        }

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "self_health",
            "description": _DESCRIPTION,
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Build the self-health report. Identical payload on CLI and MCP."""
        output_format = arguments.get("output_format", "json")
        snapshot = get_latency_recorder().snapshot()
        analysis_cache = _analysis_cache_report(self.project_root)
        ast_index = _ast_index_report(self.project_root)

        response: dict[str, Any] = {
            "success": True,
            "scope": SCOPE_CURRENT_PROCESS,
            "instrumentation_enabled": snapshot.enabled,
            "observations_status": snapshot.status,
            "percentile_method": PERCENTILE_METHOD,
            "tier_definition": TIER_DEFINITION,
            "window": snapshot.window,
            "total_invocations": snapshot.total_invocations,
            "routes": [route.as_report_row() for route in snapshot.routes],
            "analysis_cache": analysis_cache,
            "ast_index": ast_index,
        }
        summary_line = _build_summary_line(snapshot, analysis_cache, ast_index)
        response["summary_line"] = summary_line
        response["agent_summary"] = {
            "summary_line": summary_line,
            "next_step": _build_next_step(snapshot),
            "verdict": "INFO" if snapshot.routes else "WARN",
        }
        mirror_summary_line(response)

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(response, output_format)


def _build_summary_line(
    snapshot: LatencySnapshot,
    analysis_cache: dict[str, Any],
    ast_index: dict[str, Any],
) -> str:
    """One-line headline. Renders ``n/a`` — never ``0.0`` — when unmeasured."""
    hit_rate = analysis_cache.get("hit_rate")
    indexed = ast_index.get("indexed_files")
    return format_summary_line(
        "self_health",
        f"status={snapshot.status}",
        f"routes={len(snapshot.routes)}",
        f"invocations={snapshot.total_invocations}",
        f"analysis_cache_hit_rate={hit_rate if hit_rate is not None else 'n/a'}",
        f"ast_index={ast_index.get('status')}",
        f"indexed_files={indexed if indexed is not None else 'n/a'}",
    )


def _build_next_step(snapshot: LatencySnapshot) -> str:
    """Route the caller to the action that makes the report meaningful."""
    if not snapshot.routes:
        if not snapshot.enabled:
            return (
                "Latency instrumentation is disabled "
                "(TSA_LATENCY_INSTRUMENTATION is set to a falsey value). "
                "Unset it and re-run the routes you want measured."
            )
        return (
            "No routes have been observed in this process yet, so no latency "
            "claim about it is supportable. Scope is the current process: run "
            "`uv run python scripts/measure_self_health_baseline.py` to "
            "produce a durable baseline, or query this on a long-lived MCP "
            "server after real traffic."
        )
    return (
        "Compare the cold and warm rows per route: a route with no warm "
        "benefit is a standing-index candidate. Pin these numbers with "
        "`uv run python scripts/measure_self_health_baseline.py`."
    )
