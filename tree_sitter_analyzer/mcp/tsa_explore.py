"""Prototype ``tsa_explore`` umbrella tool — Phase 1b tool-menu-size experiment.

PROTOTYPE ONLY — NOT wired into the production MCP server (server.py).
Do NOT import this module from server.py or any production path.

This module implements a single ``tsa_explore`` async function that routes
natural-language queries to the appropriate TSA facade (nav / search /
structure / health) based on a ``task_type`` hint or keyword inference.

task_type → facade routing (from TOOL-MENU-EXPERIMENT-FINDINGS.md §Methodology):
  entrypoint-tracing  → search (symbol) + nav (context)
  call-chain          → nav (callee_tree)
  module-boundary     → structure (sitemap)
  change-impact       → nav (impact) + search (symbol)
  subsystem-overview  → structure (sitemap) + health (overview)

Phase 2 Case B engineering: wire this module into server.py as a registered MCP
tool ONLY after Phase 1b live-agent results show a measurable effect.
See: benchmarks/codegraph_compare/TOOL-MENU-EXPERIMENT-FINDINGS.md
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Routing table: task_type → ordered list of (facade_name, action, extra_args)
# ---------------------------------------------------------------------------
# Each entry is called in order; results are collected into a combined response.
# The first entry is the primary source; subsequent entries enrich the answer.
# ---------------------------------------------------------------------------

_ROUTING: dict[str, list[tuple[str, str, dict[str, Any]]]] = {
    "entrypoint-tracing": [
        ("search", "symbol", {}),
        ("nav", "context", {}),
    ],
    "call-chain": [
        ("nav", "callee_tree", {"max_depth": 3}),
    ],
    "module-boundary": [
        ("structure", "sitemap", {"mode": "module"}),
    ],
    "change-impact": [
        ("nav", "impact", {"mode": "blast_radius"}),
        ("search", "symbol", {}),
    ],
    "subsystem-overview": [
        ("structure", "sitemap", {"mode": "module"}),
        ("health", "overview", {}),
    ],
}

# ---------------------------------------------------------------------------
# Keyword → task_type heuristic (applied when task_type is not supplied)
# ---------------------------------------------------------------------------

_KEYWORD_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\b(entry.?point|bootstrap|main|startup|request.?handler|route)\b", re.I),
        "entrypoint-tracing",
    ),
    (
        re.compile(r"\b(call.?chain|call.?stack|execution.?path|trace|invoke|calls)\b", re.I),
        "call-chain",
    ),
    (
        re.compile(r"\b(module|boundary|interface|import|export|package|namespace|layer)\b", re.I),
        "module-boundary",
    ),
    (
        re.compile(r"\b(change.?impact|blast.?radius|affect|ripple|downstream|depend)\b", re.I),
        "change-impact",
    ),
    (
        re.compile(r"\b(subsystem|overview|architecture|landscape|map|survey|summary)\b", re.I),
        "subsystem-overview",
    ),
]

_DEFAULT_TASK_TYPE = "entrypoint-tracing"


def _infer_task_type(query: str) -> str:
    """Return the best-matching task_type for *query* using keyword heuristics.

    Falls back to ``"entrypoint-tracing"`` when no keyword pattern matches —
    that route uses ``nav/context`` which handles the widest variety of
    free-form questions.
    """
    for pattern, task_type in _KEYWORD_PATTERNS:
        if pattern.search(query):
            return task_type
    return _DEFAULT_TASK_TYPE


# ---------------------------------------------------------------------------
# Symbol extraction heuristic
# ---------------------------------------------------------------------------


def _extract_symbol(query: str) -> str | None:
    """Heuristic: extract the most likely symbol identifier from *query*.

    Resolution order:
    1. Quoted identifiers — ``'foo'``, ``"Foo"``, `` `foo` ``
    2. CamelCase words — ``IndexShard``, ``ParseError``
    3. snake_case identifiers — ``build_cache``, ``handle_request``

    Returns ``None`` when the query appears to be pure natural language with
    no obvious identifier.  Callers fall back to the full query string.
    """
    quoted = re.search(r"['\"`](\w+)['\"`]", query)
    if quoted:
        return quoted.group(1)
    camel = re.search(r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b", query)
    if camel:
        return camel.group(1)
    snake = re.search(r"\b([a-z][a-z0-9]+(?:_[a-z0-9]+)+)\b", query)
    if snake:
        return snake.group(1)
    return None


# ---------------------------------------------------------------------------
# Facade builder cache (keyed by project_root)
# ---------------------------------------------------------------------------
# Facades are expensive to construct (they instantiate inner tools + caches).
# Cache per project_root so repeated calls in the same process reuse them.

_facade_cache: dict[str | None, dict[str, Any]] = {}


def _get_facades(project_root: str | None) -> dict[str, Any]:
    """Return {facade_name: FacadeTool} for *project_root*, building lazily.

    Uses module-level caching so the heavy facade construction (inner tool
    instantiation, call-graph setup) happens at most once per project root
    per process lifetime.
    """
    if project_root in _facade_cache:
        return _facade_cache[project_root]

    # Lazy imports match the existing codebase convention (PERF-3).
    from .tools.health_facade import build_health_facade
    from .tools.nav_facade import build_nav_facade
    from .tools.search_facade import build_search_facade
    from .tools.structure_facade import build_structure_facade

    facades: dict[str, Any] = {
        "nav": build_nav_facade(project_root),
        "search": build_search_facade(project_root),
        "structure": build_structure_facade(project_root),
        "health": build_health_facade(project_root),
    }
    _facade_cache[project_root] = facades
    return facades


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def tsa_explore(
    query: str,
    task_type: str | None = None,
    project_root: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Route a natural-language code query to the appropriate TSA facade(s).

    This is the single MCP tool surface for Condition B of the tool-menu-size
    experiment.  It replaces the 8-facade surface (nav, search, structure,
    health, edit, project, index, viz) with one call that internally routes to
    the correct backend.

    Parameters
    ----------
    query:
        Natural-language description of what to investigate, or a symbol name.
        Used both as the routing signal (when *task_type* is absent) and as the
        ``task``/``query``/``symbol`` argument forwarded to each facade action.
    task_type:
        Optional benchmark category hint.  One of:
        ``"entrypoint-tracing"``, ``"call-chain"``, ``"module-boundary"``,
        ``"change-impact"``, ``"subsystem-overview"``.
        When absent, inferred from *query* keywords via ``_infer_task_type``.
    project_root:
        Absolute path to the project root.  When absent, the facades use
        whatever project root their inner tools already have set.
    **kwargs:
        Extra parameters forwarded verbatim to each facade call
        (e.g. ``max_depth``, ``max_nodes``, ``output_format``).

    Returns
    -------
    dict with keys:
        ``task_type``  — resolved task type used for routing
        ``query``      — the original query string
        ``results``    — list of per-facade result dicts (in routing order)
        ``success``    — True when at least one facade call succeeded
        ``error``      — present only when *all* facade calls failed
    """
    effective_task_type = task_type or _infer_task_type(query)
    route = _ROUTING.get(effective_task_type, _ROUTING[_DEFAULT_TASK_TYPE])

    symbol = _extract_symbol(query)
    facades = _get_facades(project_root)

    results: list[dict[str, Any]] = []
    any_success = False

    for facade_name, action, extra_args in route:
        facade = facades.get(facade_name)
        if facade is None:
            results.append(
                {
                    "facade": facade_name,
                    "action": action,
                    "success": False,
                    "error": f"facade '{facade_name}' not available",
                }
            )
            continue

        # Build the args dict for this facade call.
        call_args: dict[str, Any] = {"action": action}
        call_args.update(extra_args)
        call_args.update(kwargs)

        # Inject query/symbol using the convention each action expects.
        if action == "context":
            call_args.setdefault("task", query)
        elif action == "symbol":
            call_args.setdefault("query", query)
        elif action in ("callee_tree", "caller_tree", "impact"):
            # These actions require a symbol identifier.
            call_args.setdefault("symbol", symbol or query)
        elif action in ("sitemap", "overview"):
            # These actions take no positional query param.
            pass
        else:
            call_args.setdefault("symbol", symbol or query)

        try:
            raw = await facade.execute(call_args)
            entry: dict[str, Any] = {
                "facade": facade_name,
                "action": action,
            }
            if isinstance(raw, dict):
                entry.update(raw)
                entry.setdefault("success", True)
            else:
                # F5 bespoke routes may return a bare int (exit code).
                entry["result"] = raw
                entry["success"] = True
            results.append(entry)
            any_success = True
        except Exception as exc:  # nosec B110 — prototype; collect errors, never raise
            results.append(
                {
                    "facade": facade_name,
                    "action": action,
                    "success": False,
                    "error": str(exc),
                }
            )

    response: dict[str, Any] = {
        "task_type": effective_task_type,
        "query": query,
        "results": results,
        "success": any_success,
    }
    if not any_success:
        response["error"] = "all facade calls failed; see results for details"
    return response
