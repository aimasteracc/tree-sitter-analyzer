#!/usr/bin/env python3
"""把实时文本、索引检索和 AST 查询统一到 ``search`` 门面。

门面通过 ``action`` 参数分派多种搜索能力：

==========  ====================================  ==================================
动作        内部路由                              引擎
==========  ====================================  ==================================
text        ``text_search``                       原生实时字面量扫描
symbol      ``codegraph_symbol_search``           BM25 FTS5 符号检索
query       ``query_code`` (QueryTool)            tree-sitter ``.scm`` 查询 DSL  (F3)
==========  ====================================  ==================================

F3（PRD §0）：``query``（tree-sitter ``.scm`` DSL）与 ``symbol``（BM25 FTS）
使用不同参数和引擎，必须保持独立；把 ``query_code`` 合入 ``symbol`` 会静默删除
tree-sitter 查询能力。

Wave C 切换期间该门面与 legacy 路由共存，不改变后者行为。
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
    "Covers live text, codegraph_symbol_search (BM25), codegraph_query (tree-sitter AST), "
    "codegraph_query chain DSL, TQL, and semantic symbol retrieval. "
    "Pick a capability via `action`:\n"
    "- action=text — complete literal line search over admitted live project files; "
    "no AST index or ripgrep required. Params: query, root, case_mode, word_match, "
    "include_globs, exclude_globs, limit.\n"
    "- action=symbol — BM25 FTS lookup of a symbol by name (fast 'where is X "
    "defined', codegraph_symbol_search equivalent). "
    "Params: query, language, kind, limit.\n"
    "- action=query — tree-sitter .scm query DSL (semantic AST match, NOT the "
    "same as symbol). Params: query_key, query_string, filter, file_path.\n"
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
    "- action=unsubscribe — cancel a Hyphae subscription. Params: sub_id or selector.\n"
    "- action=tql_schema — full TQL (extended Hyphae) DSL reference: temporal "
    "pseudo-classes (:hot/:stale/:hotspot), depth quantifier {n,m}, :violates, "
    ":reaches, :branch, plus all standard Hyphae pseudo-classes. Call once at "
    "session start. Params: (none).\n"
    "- action=tql_execute — execute a TQL (Temporal Query Language) selector: "
    "Hyphae extended with DepthQuantifier {n,m} bounded BFS, temporal "
    "pseudo-classes, reachability, architecture violations, and branch "
    "context. Call action=tql_schema first for the grammar. "
    "Params: selector (required), max_results.\n"
    "- action=semantic — find symbols semantically similar to a natural-"
    "language query via vector embeddings (requires numpy + embedding "
    "pipeline). Params: query (required), top_k, min_similarity, language, "
    "kind, use_combined_score."
)


def build_search_facade(
    project_root: str | None = None, lifecycle_manager: Any | None = None
) -> FacadeTool:
    """Construct the ``search`` facade wired to live inner tool instances.

    Imports are inlined to keep cold-start cost off the import path for callers
    that don't build the facade (matches the lazy-import convention in
    ``_tool_registry.py``).
    """
    from .codegraph_query_tool import CodeGraphQueryTool
    from .hyphae_select_tool import HyphaeSelectTool
    from .hyphae_subscribe_tool import HyphaeSubscribeTool, HyphaeUnsubscribeTool
    from .query_tool import QueryTool
    from .semantic_tool import SemanticNeighborsTool
    from .symbol_search_tool import SYMBOL_SEARCH_KINDS, CodeGraphSymbolSearchTool
    from .text_search_tool import TextSearchTool
    from .tql_tool import TqlExecuteTool, TqlSchemaTool

    facade = FacadeTool(
        facade_name="search",
        action_map={
            "text": TextSearchTool(project_root),
            "symbol": CodeGraphSymbolSearchTool(project_root),  # BM25 FTS
            "query": QueryTool(project_root),  # F3: tree-sitter .scm DSL
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
            "subscribe": HyphaeSubscribeTool(project_root, lifecycle_manager),
            "unsubscribe": HyphaeUnsubscribeTool(project_root, lifecycle_manager),
            # TQL — extended Hyphae DSL with temporal + depth-quantifier
            # pseudo-classes.
            "tql_schema": TqlSchemaTool(project_root),
            "tql_execute": TqlExecuteTool(project_root),
            # Semantic search — vector similarity over indexed symbol embeddings.
            "semantic": SemanticNeighborsTool(project_root),
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

    return facade
