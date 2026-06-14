#!/usr/bin/env python3
"""``search`` facade — PoC for the FacadeTool framework (P0 geode layer).

Folds five search capabilities behind one ``action`` parameter:

==========  ====================================  ==================================
action      inner / route                         engine
==========  ====================================  ==================================
symbol      ``codegraph_symbol_search``           BM25 FTS5 symbol lookup
query       ``query_code`` (QueryTool)            tree-sitter ``.scm`` query DSL  (F3)
content     ``search_content`` (BESPOKE, F5)      ripgrep text search (dict|int)
grep        ``find_and_grep``                     fd + ripgrep (dict|int)
batch       ``batch_search``                      multi-query batch
==========  ====================================  ==================================

F3 (PRD §0): ``query`` (tree-sitter ``.scm`` DSL) and ``symbol`` (BM25 FTS)
are DISTINCT actions with zero shared params and different engines — they must
NOT be merged. Folding ``query_code`` into ``symbol`` would silently delete the
tree-sitter query capability.

F5: ``content`` is registered as a *bespoke* route because
``search_content.execute`` returns ``dict | int`` (a bare int exit code when
``suppress_output=True``). The bespoke handler tolerates the union return and
owns its own arg handling (no inner-schema projection). ``grep``
(``find_and_grep``) has the same union return but is routed via the normal
``action_map`` — the FacadeTool forwards its result verbatim, so an int return
flows through unchanged.

This facade is registered ALONGSIDE the legacy tools during Wave C cutover; at
P0 it coexists with the existing 62 tools and changes none of their behaviour.
"""

from __future__ import annotations

from typing import Any

from .facade_tool import FacadeTool

# Facade-level annotations: every search action is read-only, so a single
# honest ``readOnlyHint=True`` is valid here (unlike e.g. a future ``edit``
# facade that spans read + mutating actions — see review §8 F-extra-3).
_SEARCH_ANNOTATIONS: dict[str, Any] = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

_SEARCH_DESCRIPTION = (
    "Code-intelligence (codegraph-compatible) search facade. "
    "Covers codegraph_symbol_search (BM25), codegraph_query (tree-sitter AST), "
    "codegraph_query chain DSL, and ripgrep/fd text search in one tool. "
    "Pick a capability via `action`:\n"
    "- action=symbol — BM25 FTS lookup of a symbol by name (fast 'where is X "
    "defined', codegraph_symbol_search equivalent). "
    "Params: query, language, kind, limit.\n"
    "- action=query — tree-sitter .scm query DSL (semantic AST match, NOT the "
    "same as symbol). Params: query_key, query_string, filter, file_path.\n"
    "- action=content — ripgrep text/regex search across files. "
    "Params: query, roots, include_globs, ...\n"
    "- action=grep — two-stage fd (file discovery) + ripgrep search. "
    "Params: query, roots, ...\n"
    "- action=batch — run multiple ripgrep searches in one call. "
    "Params: queries (required array of 2-10 items; each item requires "
    "`pattern` and may include roots/include_globs/exclude_globs/max_results/label), "
    "output_format.\n"
    "- action=chain — jQuery-style codegraph chain DSL: compose search / "
    "explore / callers / callees in one process. Steps are separated by '.' "
    "(NOT '|'), e.g. query=\"search('IndexShard').callers()\" or "
    "\"explore('parse').related()\"; a plain string with no parentheses is "
    "treated as explore(string).related(). "
    "Params: query (required — the chain string), max_symbols, max_files, "
    "include_code, compact.\n"
    "- action=select — Hyphae DSL, a CSS-selector-style graph query (RFC-0003). "
    "ONE selector replaces chains of navigate/callers/search: #name, .kind "
    "(.function/.method/.class), *, :calls(#X), :callees(#X), :not(sel), "
    ":in(path), [file=p]/[language=l]/[class=C], combinators A > B / A B. "
    "Example: '.function:calls(#IndexShard):in(server/)'. Params: selector "
    "(required), max_results, output_format.\n"
    "- action=subscribe — RFC-0001 reactive push: subscribe to a Hyphae selector. "
    "Receive send_resource_updated when results change; re-read resource_uri. "
    "Returns { sub_id, resource_uri }. Params: selector (required), min_interval.\n"
    "- action=unsubscribe — cancel a Hyphae subscription. Params: sub_id or selector."
)


def build_search_facade(project_root: str | None = None) -> FacadeTool:
    """Construct the ``search`` facade wired to live inner tool instances.

    Imports are inlined to keep cold-start cost off the import path for callers
    that don't build the facade (matches the lazy-import convention in
    ``_tool_registry.py``).
    """
    from .batch_search_tool import BatchSearchTool
    from .codegraph_query_tool import CodeGraphQueryTool
    from .find_and_grep_tool import FindAndGrepTool
    from .hyphae_select_tool import HyphaeSelectTool
    from .hyphae_subscribe_tool import HyphaeSubscribeTool, HyphaeUnsubscribeTool
    from .query_tool import QueryTool
    from .search_content_tool import SearchContentTool
    from .symbol_search_tool import SYMBOL_SEARCH_KINDS, CodeGraphSymbolSearchTool

    # Inner instance used by the bespoke ``content`` route. It is held so the
    # facade can rebind it on project-root changes (G3) just like action_map
    # instances; we therefore also place it in action_map handling via the
    # bespoke closure that closes over the live instance.
    content_tool = SearchContentTool(project_root)

    async def _content_route(args: dict[str, Any]) -> Any:
        """F5 bespoke route: search_content returns dict|int — forward verbatim."""
        return await content_tool.execute(args)

    facade = FacadeTool(
        facade_name="search",
        action_map={
            "symbol": CodeGraphSymbolSearchTool(project_root),  # BM25 FTS
            "query": QueryTool(project_root),  # F3: tree-sitter .scm DSL
            "grep": FindAndGrepTool(project_root),  # fd + ripgrep (dict|int)
            "batch": BatchSearchTool(project_root),  # multi-query batch
            # jQuery-style graph chain DSL (search().explore().callees()...),
            # folded here from the standalone ``codegraph_query`` tool so the
            # whole 62-row capability surface survives the facade cutover.
            "chain": CodeGraphQueryTool(project_root),
            # Hyphae DSL — CSS-selector-style graph query (RFC-0003 port).
            # One selector replaces chains of navigate/callers/search, e.g.
            # ".function:calls(#IndexShard):in(server/)".
            "select": HyphaeSelectTool(project_root),
            # RFC-0001: reactive push — subscribe/unsubscribe to selector results.
            # Agent subscribes → receives send_resource_updated when results change
            # → re-reads tsa://hyphae/{selector} for the new set.
            "subscribe": HyphaeSubscribeTool(project_root),
            "unsubscribe": HyphaeUnsubscribeTool(project_root),
        },
        bespoke_map={
            "content": _content_route,  # F5: search_content (dict|int)
        },
        description=_SEARCH_DESCRIPTION,
        annotations=_SEARCH_ANNOTATIONS,
        project_root=project_root,
        # #640: ``kind`` is high-value for action=symbol (e.g. kind=constant)
        # but was only reachable via additionalProperties — invisible to
        # schema-reading agents. Surface it with the authoritative enum,
        # sourced from the inner tool so facade/inner/CLI never drift.
        extra_public_params={
            "kind": {
                "type": "string",
                "enum": list(SYMBOL_SEARCH_KINDS),
                "description": "Symbol kind filter for action=symbol (default: any).",
            },
        },
    )

    # G3: make the bespoke ``content`` tool rebind with the facade. The
    # FacadeTool only auto-rebinds ``action_map`` instances; register the
    # bespoke inner so set_project_path reaches it too.
    facade.register_bespoke_inner(content_tool)
    return facade
