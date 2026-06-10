#!/usr/bin/env python3
"""``nav`` facade — Wave B consolidation of code-navigation inner tools.

Folds eight navigation capabilities (plus two scope-discriminated actions)
behind one ``action`` parameter:

============  =============================================  ==========================
action        inner / route                                  scope/notes
============  =============================================  ==========================
navigate      ``codegraph_navigate``                         symbol go-to-definition
call_path     ``codegraph_call_path``                        BFS path between functions
xref          ``codegraph_xref``                             cross-reference lookup
resolve       ``codegraph_resolve``                          symbol resolver
lineage       ``symbol_lineage``                             class/function lineage
impact        ``codegraph_impact``                           blast-radius / risk
trace         ``trace_impact``                               impact trace
callers       BESPOKE — scope=point → callers_tool (R4)     point = direct callers
              BESPOKE — scope=graph → call_graph mode=callers
callees       BESPOKE — scope=point → callees_tool (R4)     point = direct callees
              BESPOKE — scope=graph → call_graph mode=callees
============  =============================================  ==========================

R4 (PRD §0 Errata): ``callers``/``callees`` are scope-discriminated.
  - ``scope=point`` (default) → ``codegraph_callers``/``codegraph_callees`` for
    direct 1-hop lookup (fast, ``function_name`` required).
  - ``scope=graph`` → ``codegraph_call_graph mode=callers|callees`` for full
    traversal (BFS, ``function_name`` required for callers/callees modes).

Both callers/callees closures read ``scope`` BEFORE the framework strips it,
and they are registered via ``register_bespoke_inner`` (G3) so project-root
rebinds propagate correctly.

R3: ``symbol`` → ``function_name`` normalization is applied automatically by
``FacadeTool._project_args`` for action_map routes, and defensively by
``FacadeTool._clean_bespoke_args`` for bespoke routes — so callers passing
``symbol=`` instead of ``function_name=`` are handled transparently.

All nav actions are read-only; a single honest ``readOnlyHint=True`` is valid
(unlike ``edit``/``project`` facades that span mutating actions).
"""

from __future__ import annotations

from typing import Any

from .facade_tool import FacadeTool

_NAV_ANNOTATIONS: dict[str, Any] = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

_NAV_DESCRIPTION = (
    "Code-intelligence (codegraph-compatible) navigation facade. "
    "Covers codegraph_navigate, codegraph_callers, codegraph_callees, "
    "codegraph_call_path, codegraph_xref, codegraph_impact, codegraph_context, "
    "codegraph_trace, and symbol lineage/resolve in one tool. "
    "START HERE for any 'how does X work' / trace / call-flow / "
    "understand-a-class question: call action=context FIRST (ONE call composes "
    "definition + callers + callees + code for a task), then action=callee_tree "
    "or caller_tree for the FULL traversal tree in ONE call. These replace many "
    "search/navigate/Read round-trips — do NOT loop search or per-symbol "
    "navigate; reach for the tree/context actions instead.\n"
    "Pick a capability via `action`:\n"
    "- action=navigate — go-to-definition / symbol navigation "
    "(codegraph_navigate equivalent). "
    "Params: symbol (required), mode (full|references|callers|callees).\n"
    "- action=call_path — BFS execution path between two functions "
    "('how does A reach B?', codegraph_call_path equivalent). "
    "Params: source_function, target_function, source_file, target_file, "
    "direction (forward|backward|bidirectional), max_depth, max_paths.\n"
    "- action=xref — cross-reference lookup (who uses this symbol or file, "
    "codegraph_xref equivalent). "
    "Params: symbol, mode (symbol|file), file_path.\n"
    "- action=resolve — go-to-definition + find-all-references for a symbol. "
    "Params: symbol (required), mode (resolve|references), output_format.\n"
    "- action=lineage — class/function inheritance and override lineage. "
    "Params: symbol (required), output_format.\n"
    "- action=impact — blast-radius / risk scoring for a function or set of "
    "functions (codegraph_impact equivalent). "
    "Risk score computed from PRODUCTION edges only; tests bucket "
    "(test_callers_count, test_callees_count) always present. "
    "Params: mode (function_impact|blast_radius|risk_score), "
    "function_name, function_names, file_path, depth, "
    "include_tests (bool, default false — when true adds "
    "test_caller_files/test_callee_files to tests bucket).\n"
    "- action=trace — full impact trace from a symbol outward "
    "(codegraph_trace equivalent). "
    "Params: symbol (required), output_format.\n"
    "- action=context — one-call focused context for a task/symbol: composes "
    "search + definition + callers + callees in a single capped response "
    "(codegraph_context equivalent). "
    "Params: task (required — natural-language description or symbol name), "
    "max_nodes, max_code_blocks, output_format.\n"
    "- action=callers — who calls a function (codegraph_callers equivalent).\n"
    "  scope=point (default) → direct 1-hop callers (fast). "
    "Params: function_name/symbol (required), file_path, output_format.\n"
    "  scope=graph → full call-graph traversal (callers mode). "
    "Params: function_name/symbol (required), file_path, depth, output_format.\n"
    "- action=callees — what a function calls (codegraph_callees equivalent).\n"
    "  scope=point (default) → direct 1-hop callees (fast). "
    "Params: function_name/symbol (required), file_path, output_format.\n"
    "  scope=graph → full call-graph traversal (callees mode). "
    "Params: function_name/symbol (required), file_path, depth, output_format.\n"
    "- action=callee_tree — depth-limited NESTED tree of everything a function "
    "transitively calls, in ONE call (no per-node iteration). Prefer this over "
    "looping action=callees. Params: symbol (required), file_path, max_depth "
    "(default 3, cap 10), max_nodes (default 150), output_format.\n"
    "- action=caller_tree — depth-limited NESTED tree of everything that "
    "transitively calls a function (blast radius), in ONE call. Params: symbol "
    "(required), file_path, max_depth, max_nodes, output_format."
)


def build_nav_facade(project_root: str | None = None) -> FacadeTool:
    """Construct the ``nav`` facade wired to live inner tool instances.

    Imports are inlined to keep cold-start cost off the import path for callers
    that don't build the facade (matches the lazy-import convention used across
    the tool registry).
    """
    from ._call_tree_tool import CodeGraphCalleeTreeTool, CodeGraphCallerTreeTool
    from .call_graph_tool import CodeGraphCallTool
    from .call_path_tool import CodeGraphCallPathTool
    from .callees_tool import CodeGraphCalleesTool
    from .callers_tool import CodeGraphCallersTool
    from .codegraph_context_tool import CodeGraphContextTool
    from .codegraph_impact_tool import CodeGraphImpactTool
    from .codegraph_navigate_tool import CodeGraphNavigateTool
    from .codegraph_xref_tool import CodeGraphXRefTool
    from .symbol_lineage_tool import SymbolLineageTool
    from .symbol_resolve_tool import CodeGraphSymbolResolveTool
    from .trace_impact_tool import TraceImpactTool

    # ------------------------------------------------------------------
    # R4 bespoke inners — scope-discriminated callers/callees
    #
    # ``scope`` is a facade control key that the framework strips BEFORE
    # projecting args to an inner schema.  Because we need to READ scope
    # to choose the inner, we use bespoke closures that receive the full
    # cleaned-args dict (control keys minus ``action`` stripped, R3 copy
    # applied) and inspect ``scope`` themselves.
    #
    # All four instances are registered via ``register_bespoke_inner``
    # (called after facade construction below) so G3 rebind reaches them.
    # ------------------------------------------------------------------

    callers_point = CodeGraphCallersTool(project_root)
    callers_graph = CodeGraphCallTool(project_root)
    callees_point = CodeGraphCalleesTool(project_root)
    callees_graph = CodeGraphCallTool(project_root)
    context_inner = CodeGraphContextTool(project_root)

    async def _context_route(args: dict[str, Any]) -> Any:
        """Bespoke context route: normalize symbol/query → task (fix ③).

        ``CodeGraphContextTool`` requires ``task`` (a natural-language string).
        The nav description exposes ``symbol``/``query`` as convenience aliases
        because callers naturally think in symbol names. This bespoke closure
        applies the normalization BEFORE delegating to the inner so callers
        passing ``symbol="MyClass"`` or ``query="execute"`` don't trip the
        ``ValueError: task is required`` guard.
        Resolution order: explicit ``task`` > ``symbol`` > ``query``.
        """
        # Build the projected args set that context inner accepts.
        # RFC-0006: include_graph added for progressive disclosure opt-in.
        inner_keys = (
            "task",
            "max_nodes",
            "max_code_blocks",
            "output_format",
            "include_graph",
        )
        context_args: dict[str, Any] = {
            k: v for k, v in args.items() if k in inner_keys
        }
        # Normalize: if ``task`` not provided, fall back to ``symbol`` or ``query``.
        if not context_args.get("task"):
            fallback = args.get("symbol") or args.get("query")
            if fallback:
                context_args["task"] = str(fallback)
        return await context_inner.execute(context_args)

    async def _callers_route(args: dict[str, Any]) -> Any:
        """R4: scope=point → direct callers; scope=graph → call-graph traversal."""
        scope = args.pop("scope", "point")
        if scope == "graph":
            # Inject mode=callers for the call-graph inner; project to its schema.
            graph_args = {
                k: v
                for k, v in args.items()
                if k in ("function_name", "file_path", "depth", "output_format")
            }
            graph_args["mode"] = "callers"
            return await callers_graph.execute(graph_args)
        # scope=point (default): use the dedicated callers tool.
        point_args = {
            k: v
            for k, v in args.items()
            if k in ("function_name", "file_path", "output_format")
        }
        return await callers_point.execute(point_args)

    async def _callees_route(args: dict[str, Any]) -> Any:
        """R4: scope=point → direct callees; scope=graph → call-graph traversal."""
        scope = args.pop("scope", "point")
        if scope == "graph":
            graph_args = {
                k: v
                for k, v in args.items()
                if k in ("function_name", "file_path", "depth", "output_format")
            }
            graph_args["mode"] = "callees"
            return await callees_graph.execute(graph_args)
        point_args = {
            k: v
            for k, v in args.items()
            if k in ("function_name", "file_path", "output_format")
        }
        return await callees_point.execute(point_args)

    facade = FacadeTool(
        facade_name="nav",
        action_map={
            "navigate": CodeGraphNavigateTool(project_root),
            "call_path": CodeGraphCallPathTool(project_root),
            "xref": CodeGraphXRefTool(project_root),
            "resolve": CodeGraphSymbolResolveTool(project_root),
            "lineage": SymbolLineageTool(project_root),
            "impact": CodeGraphImpactTool(project_root),
            "trace": TraceImpactTool(project_root),
            # Tree primitives (mycelium RFC-0020/0021 parity): one call →
            # depth-limited NESTED tree, so the agent stops iterating
            # callees/callers per node (the IndexShard dogfood loss root cause).
            "callee_tree": CodeGraphCalleeTreeTool(project_root),
            "caller_tree": CodeGraphCallerTreeTool(project_root),
        },
        bespoke_map={
            # Composed one-call context (search + node + callers + callees).
            # Bespoke so we can normalize symbol/query → task before delegating
            # to CodeGraphContextTool (which requires ``task``). Moved from
            # action_map so the normalization closure fires on every call.
            "context": _context_route,
            "callers": _callers_route,
            "callees": _callees_route,
        },
        description=_NAV_DESCRIPTION,
        annotations=_NAV_ANNOTATIONS,
        project_root=project_root,
    )

    # G3: register all bespoke inners so set_project_path reaches them.
    facade.register_bespoke_inner(context_inner)
    facade.register_bespoke_inner(callers_point)
    facade.register_bespoke_inner(callers_graph)
    facade.register_bespoke_inner(callees_point)
    facade.register_bespoke_inner(callees_graph)

    return facade
