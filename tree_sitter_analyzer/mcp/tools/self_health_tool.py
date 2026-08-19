#!/usr/bin/env python3
"""``health action=self`` / ``--self-health`` — RFC-0025 Layer 5.

Self-proprioception: the analyzer reporting how well it is sensing. Emits
per-``(tool, action)`` p50/p95 latency **split by tier**, exact invocation
counts, and the AST-cache hit rate.

Two honesty rules govern every field here:

1. **Never report a fabricated zero.** An unmeasured percentile is ``null``
   and the surrounding status is ``NO_OBSERVATIONS``. ``CacheService.get_stats()``
   returns ``hit_rate == 0.0`` for zero requests — that 0.0 is translated to
   ``null`` before it reaches a caller, because a zero that means "unmeasured"
   is exactly the belief-shaped output this surface exists to eliminate
   (CLAUDE.md §11).
2. **Never let a derived label read as a measurement.** The report carries
   ``tier_definition`` verbatim so ``cold``/``warm`` cannot be mistaken for a
   cache probe, and ``percentile_method`` so the numbers can be reproduced.

Scope is the **current process** (``scope: "current_process"``). The recorder
has no persistence layer by design, so a fresh single-shot CLI process
honestly reports ``NO_OBSERVATIONS``; a long-lived MCP server accumulates
real observations, and ``scripts/measure_self_health_baseline.py`` drives
routes in-process to produce a durable baseline.
"""

from __future__ import annotations

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
    "and the AST-cache hit rate.\n\n"
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
    "cache probe.\n\n"
    "VERDICT INTEGRITY: agent_summary.verdict is INFO when observations exist "
    "and WARN when none do — no data must not read as a clean bill of health. "
    "Legal vocabulary: SAFE / CAUTION / REVIEW / UNSAFE / INFO / WARN / "
    "ERROR / NOT_FOUND."
)


def _ast_cache_report(project_root: str | None) -> dict[str, Any]:
    """Summarise AST-cache hit statistics for *project_root*.

    Reads the engine's existing public ``get_cache_stats()``. Returns
    ``status == NO_OBSERVATIONS`` with every rate/count ``None`` whenever the
    cache has served zero requests. ``hit_rate`` is a fraction in ``[0, 1]``,
    rounded to 4 places — the upstream ``get_stats()`` reports ``0.0`` for zero
    requests, which is precisely the fabricated zero we translate away here.
    """
    unmeasured: dict[str, Any] = {
        "status": NO_OBSERVATIONS,
        "hit_rate": None,
        "hits": None,
        "misses": None,
        "total_requests": 0,
    }
    try:
        from ...core.analysis_engine import get_analysis_engine

        stats = get_analysis_engine(project_root).get_cache_stats()
    except Exception:  # noqa: BLE001 — a diagnostic must never raise
        return unmeasured
    if not stats:
        return unmeasured

    total = int(stats.get("total_requests") or 0)
    if total <= 0:
        return unmeasured
    hits = int(stats.get("hits") or 0)
    return {
        "status": "OK",
        "hit_rate": round(hits / total, 4),
        "hits": hits,
        "misses": int(stats.get("misses") or 0),
        "total_requests": total,
    }


class SelfHealthTool(BaseMCPTool):
    """MCP tool behind ``health action=self`` and the ``--self-health`` CLI flag."""

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": (
                        "Output format: 'toon' (default, token-efficient) or "
                        "'json'. The MCP-toon / CLI-json split is a locked "
                        "design decision (CLAUDE.md §1)."
                    ),
                    "default": "toon",
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
        output_format = arguments.get("output_format", "toon")
        snapshot = get_latency_recorder().snapshot()
        ast_cache = _ast_cache_report(self.project_root)

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
            "ast_cache": ast_cache,
        }
        summary_line = _build_summary_line(snapshot, ast_cache)
        response["summary_line"] = summary_line
        response["agent_summary"] = {
            "summary_line": summary_line,
            "next_step": _build_next_step(snapshot),
            "verdict": "INFO" if snapshot.routes else "WARN",
        }
        mirror_summary_line(response)

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(response, output_format)


def _build_summary_line(snapshot: LatencySnapshot, ast_cache: dict[str, Any]) -> str:
    """One-line headline. Renders ``n/a`` — never ``0.0`` — when unmeasured."""
    hit_rate = ast_cache.get("hit_rate")
    return format_summary_line(
        "self_health",
        f"status={snapshot.status}",
        f"routes={len(snapshot.routes)}",
        f"invocations={snapshot.total_invocations}",
        f"ast_cache_hit_rate={hit_rate if hit_rate is not None else 'n/a'}",
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
