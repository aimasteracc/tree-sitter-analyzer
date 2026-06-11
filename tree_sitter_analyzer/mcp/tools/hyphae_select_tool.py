"""MCP tool: Hyphae DSL selector execution against the symbol graph.

Exposes the Hyphae query DSL (RFC-0003, ported from mycelium) so an agent can
express a graph query as one CSS-selector-style string instead of chaining
several navigate/callers/search calls — e.g.
``.function:calls(#IndexShard):in(server/)``.
"""

from __future__ import annotations

from typing import Any

from .base_tool import BaseMCPTool


class HyphaeSelectTool(BaseMCPTool):
    """Execute a Hyphae selector and return matching symbols."""

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
            "name": "hyphae_select",
            "description": (
                "Run a Hyphae DSL selector (CSS-selector-style graph query) over "
                "the indexed symbol graph — one call replaces chains of "
                "navigate/callers/search. Grammar: #name; .function/.method/"
                ".class; * (all); edges :calls(#X) / :callees(#X) / "
                ":extends(#X) / :implements(#X) / :subclasses(#X) / "
                ":imports(module); structural :has(#X) / :not(sel) / :in(path) / "
                ":first-child / :only-child / :nth-child(n); attributes "
                "[file=]/[language=]/[class=]/[kind=]; combinators A > B / A B / "
                "A ~ B. Example: '.class:implements(#Writeable):in(server/)'. "
                "Unknown pseudo-classes raise an error (no silent pass-through). "
                "Requires ast_cache index (run index action=warm)."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": (
                        "Hyphae selector string, e.g. "
                        "'.method:calls(#UserRepo)' or '#Foo > .function'."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max symbols to return (default: 100).",
                    "default": 100,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default) or 'json'.",
                    "default": "toon",
                },
            },
            "required": ["selector"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if not str(arguments.get("selector", "")).strip():
            raise ValueError("selector is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        selector = str(arguments["selector"]).strip()
        max_results = int(arguments.get("max_results", 100) or 100)
        max_results = max(1, min(max_results, 1000))
        output_format = arguments.get("output_format", "toon")

        from ...hyphae import Evaluator, parse
        from ...hyphae.parser import HyphaeSyntaxError

        try:
            ast = parse(selector)
        except (HyphaeSyntaxError, ValueError) as exc:
            return {
                "success": False,
                "selector": selector,
                "error": f"Hyphae syntax error: {exc}",
                "symbols": [],
            }

        cache = self._get_cache()

        # Detect index state cheaply: check if cache has any indexed files
        index_state = self._detect_index_state(cache)

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

        # Build next_step based on index state and result count
        if index_state != "ready":
            # Index is missing or empty — 0 doesn't mean "no matches", it means "not indexed"
            next_step = (
                "Index missing or empty. Run the `index` tool with action=auto "
                "to build the cache."
            )
            verdict = "WARN"
        elif truncated:
            next_step = (
                f"Results truncated at {max_results} of {total_matches} matches. "
                "Narrow the selector with :in(path), [file=], [language=], or :not(...) "
                "to reduce results, or raise max_results."
            )
            verdict = "INFO"
        elif len(symbols) == 0:
            # Zero matches on a ready index — selector didn't match anything
            next_step = (
                "No matches found. Check your selector or try a broader search "
                "(e.g., remove :in(path) or [file=] filters)."
            )
            verdict = "NOT_FOUND"
        else:
            next_step = (
                "Answer from these symbols, or refine the selector "
                "(add :in(path) / [file=] / :not(...) to narrow)."
            )
            verdict = "INFO"

        result: dict[str, Any] = {
            "success": True,
            "selector": selector,
            "count": len(symbols),
            "total_matches": total_matches,
            "truncated": truncated,
            "symbols": symbols,
            "index_state": index_state,
            "agent_summary": {
                "summary_line": f"hyphae_select: {len(symbols)} symbols for {selector!r}",
                "verdict": verdict,
                "next_step": next_step,
            },
        }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    def _detect_index_state(self, cache: Any) -> str:
        """Determine index state: missing, empty, or ready.

        Reuses the same check as codegraph_status_tool:
        - missing: cache file doesn't exist or can't be opened
        - empty: cache exists but has no indexed files (total_files == 0)
        - ready: cache exists and has indexed files (total_files > 0)
        """
        try:
            stats = cache.get_stats()
            if stats and stats.get("total_files", 0) > 0:
                return "ready"
            return "empty"
        except Exception:
            return "missing"
