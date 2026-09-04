"""MCP tools: tql_execute / tql_schema.

TQL (Temporal Query Language) is the extended Hyphae DSL surface that adds:
  - DepthQuantifier  {n,m}  for bounded BFS  (:calls(#X){1,3})
  - Temporal pseudo-classes  :hot / :hot(N) / :recently_modified / :stale / :hotspot
  - Reachability              :reaches(#X){n,m}
  - Architecture violation    :violates(rule_id)
  - Branch context            :branch(if|loop|try|match)

All standard Hyphae pseudo-classes remain valid.
"""

from __future__ import annotations

from typing import Any

from .base_tool import BaseMCPTool

_SELECTOR_ECHO_CAP = 200

_TQL_SCHEMA_DOC = """\
# TQL (Hyphae) DSL Reference

## Type selectors
  .function  .method  .class  .module  *

## ID selector
  #SymbolName

## Attribute filters
  [file=path]  [language=python]  [class=ClassName]  [kind=function]

## Edge pseudo-classes
  :calls(#X)         symbols that call X
  :callees(#X)       symbols called by X
  :called-by(#X)     alias for :calls(#X)
  :extends(#X)       classes extending X
  :implements(#X)    classes implementing interface X
  :subclasses(#X)    subclasses of X
  :imports(module)   files importing module

## DepthQuantifier (bounded BFS)
  :calls(#X){n,m}      callers up to depth m, at least depth n
  :called-by(#X){n,m}  callees up to depth m, at least depth n
  :reaches(#X){n,m}    symbols that can reach X within m hops

  n and m are non-negative integers, n <= m.
  Omit {n,m} for single-hop (equivalent to {1,1}).

## Structural pseudo-classes
  :has(sel)          parent scope contains matching child
  :not(sel)          negation
  :in(path_prefix)   file path starts with prefix
  :first-child       first symbol in file
  :only-child        sole symbol in file
  :nth-child(n)      n-th symbol (1-indexed)

## Temporal pseudo-classes (require git metadata in index)
  :hot               modified in the last 30 days (default N=30)
  :hot(N)            modified in the last N days
  :recently_modified alias for :hot(30)
  :stale             NOT modified in the last 180 days
  :hotspot           top-10% by mod_count_30d within their file (high-churn symbols)

## Architecture pseudo-classes
  :violates(rule_id) symbols flagged by the named architecture rule
                     (uses health violation table; rule_id matches pattern)

## Branch context
  :branch(kind)      symbol is invoked inside a branch of the given kind
                     kinds: if  loop  try  match

## Combinators
  A > B              B is a direct child of A
  A B                B is a descendant of A
  A ~ B              B is a sibling of A

## Examples
  .function:hot(14):in(src/core/)
  .class:implements(#Repository):not(:stale)
  #process_request:calls(#db_write){1,3}
  .method:hotspot
  .function:violates(no_direct_db)
  .function:branch(loop):calls(#expensive_fn)
"""


def _cap_echo(selector: str) -> str:
    if len(selector) <= _SELECTOR_ECHO_CAP:
        return selector
    return selector[:_SELECTOR_ECHO_CAP] + f"... ({len(selector)} chars total)"


class TqlExecuteTool(BaseMCPTool):
    """Execute a TQL (extended Hyphae) selector against the symbol graph.

    Wraps the full Hyphae evaluator including the temporal, depth-quantifier,
    violates, reaches, and branch pseudo-classes added in the Nervous System
    implementation. Behaviorally identical to hyphae_select but documents
    the extended grammar and is the recommended entry point going forward.
    """

    action_map: dict[str, Any] = {}

    def __init__(self, project_root: str | None = None) -> None:
        self._cache: Any = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._cache = None

    def _get_cache(self) -> Any:
        if self._cache is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            from ...ast_cache import ASTCache
            self._cache = ASTCache(self.project_root)
        return self._cache

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "tql_execute",
            "description": (
                "Execute a TQL (Temporal Query Language) selector over the indexed "
                "symbol graph. TQL extends Hyphae with: DepthQuantifier {n,m} for "
                "bounded BFS (:calls(#X){1,3}), temporal pseudo-classes "
                "(:hot / :hot(N) / :recently_modified / :stale / :hotspot), "
                "reachability (:reaches(#X){n,m}), architecture violations "
                "(:violates(rule_id)), and branch context (:branch(if|loop|try|match)). "
                "All standard Hyphae pseudo-classes are also valid. "
                "Call tql_schema to get the full DSL reference. "
                "Requires indexed project (run index action=warm first). "
                "index_state: missing|empty|ready (0 results on empty != no matches)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": (
                            "TQL selector, e.g. '.function:hot(14):in(src/)' or "
                            "#process_request:calls(#db_write){1,3}"
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 100,
                        "description": "Max symbols to return (1-1000, default 100)",
                    },
                },
                "required": ["selector"],
                "additionalProperties": False,
            },
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return self.get_tool_definition()["inputSchema"]["properties"]  # type: ignore[no-any-return]

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if not arguments.get("selector"):
            raise ValueError("'selector' is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        selector = str(arguments.get("selector", "")).strip()
        if not selector:
            return {"success": False, "error": "selector is required", "symbols": []}

        max_results = int(arguments.get("max_results", 100) or 100)
        max_results = max(1, min(max_results, 1000))
        selector_echo = _cap_echo(selector)

        from ...hyphae import Evaluator, parse
        from ...hyphae.parser import HyphaeSyntaxError

        try:
            ast = parse(selector)
        except (HyphaeSyntaxError, ValueError) as exc:
            return {
                "success": False,
                "selector": selector_echo,
                "error": f"TQL syntax error: {exc}",
                "symbols": [],
            }

        try:
            cache = self._get_cache()
        except Exception as exc:
            return {"success": False, "error": str(exc), "symbols": []}

        index_state, indexed_files = self._detect_index_state(cache)

        evaluator = Evaluator(cache, max_results=max_results)
        matches = evaluator.eval(ast)
        symbols = [
            {
                "name": m.get("name"),
                "file": m.get("file"),
                "line": m.get("line"),
                "language": m.get("language"),
                "class": m.get("class"),
            }
            for m in matches
        ]

        truncated = evaluator.was_truncated()
        total_matches = evaluator.total_matches()

        if index_state != "ready":
            verdict = "WARN"
            next_step = (
                "Index missing or empty. Run index action=warm to build the cache."
            )
        elif truncated:
            verdict = "INFO"
            next_step = (
                f"Truncated at {max_results} of {total_matches}. "
                "Narrow with :in(path), [file=], :not(), or raise max_results."
            )
        elif not symbols:
            verdict = "NOT_FOUND"
            next_step = (
                f"No matches across {indexed_files} indexed file(s). "
                "Broaden the selector or run index action=auto to complete the index."
            )
        else:
            verdict = "INFO"
            next_step = "Refine with :in(path) / [file=] / :not() to narrow if needed."

        return {
            "success": True,
            "selector": selector_echo,
            "count": len(symbols),
            "total_matches": total_matches,
            "truncated": truncated,
            "symbols": symbols,
            "index_state": index_state,
            "indexed_files": indexed_files,
            "agent_summary": {
                "summary_line": f"tql_execute: {len(symbols)} symbols for {selector_echo!r}",
                "verdict": verdict,
                "next_step": next_step,
            },
        }

    def _detect_index_state(self, cache: Any) -> tuple[str, int]:
        try:
            stats = cache.get_stats()
            total = int((stats or {}).get("total_files", 0) or 0)
            if total > 0:
                return "ready", total
            return "empty", 0
        except Exception:
            return "missing", 0


class TqlSchemaTool(BaseMCPTool):
    """Return the full TQL (Hyphae) DSL reference documentation."""

    action_map: dict[str, Any] = {}

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "tql_schema",
            "description": (
                "Return the full TQL / Hyphae DSL reference: all pseudo-classes "
                "(including temporal :hot/:stale/:hotspot, depth quantifier {n,m}, "
                ":violates, :reaches, :branch), type selectors, attribute filters, "
                "combinators, and examples. Call once at session start to learn the "
                "query grammar before writing selectors."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return self.get_tool_definition()["inputSchema"]["properties"]  # type: ignore[no-any-return]

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "schema": _TQL_SCHEMA_DOC}


def build_tql_execute_tool(project_root: str | None) -> TqlExecuteTool:
    """Factory function for the ``tql_execute`` MCP tool."""
    return TqlExecuteTool(project_root)


def build_tql_schema_tool(project_root: str | None = None) -> TqlSchemaTool:
    """Factory function for the ``tql_schema`` MCP tool."""
    return TqlSchemaTool(project_root)
