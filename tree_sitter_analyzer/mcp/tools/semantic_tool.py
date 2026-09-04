"""MCP tool: semantic_neighbors — find symbols similar to a query by embedding.

Requires:
  - numpy
  - symbol_vectors table populated (run embeddings pipeline first)

Graceful degradation:
  - numpy missing     → error response with install hint
  - vectors missing   → empty result with hint to run embedding pipeline
"""

from __future__ import annotations

from typing import Any

from .base_tool import BaseMCPTool


class SemanticNeighborsTool(BaseMCPTool):
    """Find symbols semantically similar to a text query or a named symbol."""

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
            "name": "semantic_neighbors",
            "description": (
                "Find symbols semantically similar to a text query. "
                "Uses pre-computed vector embeddings (UniXcoder or OpenAI) "
                "stored in the symbol_vectors table. "
                "Requires: numpy + embedding pipeline run (embeddings pipeline not "
                "run automatically — ask the user to run it, or use search/nav "
                "as fallback). "
                "Returns top_k symbols ranked by cosine similarity (>= min_similarity). "
                "Filter by language or kind to narrow results. "
                "combined_score blends similarity + git_heat + caller_count."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Natural language description of what you are looking for, "
                            "e.g. 'function that validates user input' or "
                            "'class handling database connection pooling'."
                        ),
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max number of results (1-50, default 10)",
                    },
                    "min_similarity": {
                        "type": "number",
                        "default": 0.5,
                        "description": "Minimum cosine similarity threshold (0-1)",
                    },
                    "language": {
                        "type": "string",
                        "description": "Optional: restrict to this language",
                    },
                    "kind": {
                        "type": "string",
                        "description": "Optional: restrict to this kind (function/class/method)",
                    },
                    "use_combined_score": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "If true, re-rank by combined_score "
                            "(0.7*similarity + 0.2*git_heat + 0.1*callers)"
                        ),
                    },
                },
                "required": ["query"],
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
        return self.get_tool_definition()["inputSchema"]["properties"]

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if not arguments.get("query"):
            raise ValueError("'query' is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from ...api.semantic import (
            SemanticUnavailableError,
            _score_symbol_full,
            find_semantic_neighbors,
        )
        from ...embeddings.pipeline import (
            EmbeddingModelUnavailableError,
            _embed_with_openai,
            _embed_with_unixcoder,
        )

        query = str(arguments.get("query", "")).strip()
        if not query:
            return {"success": False, "error": "query is required"}

        top_k = max(1, min(int(arguments.get("top_k", 10)), 50))
        min_sim = float(arguments.get("min_similarity", 0.5))
        language = arguments.get("language") or None
        kind = arguments.get("kind") or None
        use_combined = bool(arguments.get("use_combined_score", False))

        # Embed the query text.
        query_vec: list[float] | None = None
        model_used = ""
        embed_error = ""
        for embed_fn, name in [(_embed_with_openai, "openai"), (_embed_with_unixcoder, "unixcoder")]:
            try:
                query_vec = embed_fn([query])[0]
                model_used = name
                break
            except Exception as exc:
                embed_error = str(exc)

        if query_vec is None:
            return {
                "success": False,
                "error": (
                    f"No embedding model available ({embed_error}). "
                    "Install openai or transformers+torch to enable semantic search."
                ),
                "neighbors": [],
            }

        try:
            cache = self._get_cache()
            conn = cache.get_conn()
        except Exception as exc:
            return {"success": False, "error": str(exc), "neighbors": []}

        try:
            neighbors = find_semantic_neighbors(
                conn,
                query_vec,
                top_k=top_k,
                min_similarity=min_sim,
                language_filter=language,
                kind_filter=kind,
            )
        except SemanticUnavailableError as exc:
            return {
                "success": False,
                "error": str(exc),
                "hint": "Install numpy: pip install numpy",
                "neighbors": [],
            }
        except Exception as exc:
            return {"success": False, "error": f"semantic search failed: {exc}", "neighbors": []}

        if not neighbors:
            return {
                "success": True,
                "model": model_used,
                "neighbors": [],
                "hint": (
                    "No neighbors found. The embedding table may be empty — "
                    "run the embedding pipeline first. Or lower min_similarity."
                ),
            }

        if use_combined:
            # Fetch git_heat and caller counts for re-ranking.
            for n in neighbors:
                sym_id = n["symbol_id"]
                try:
                    heat_row = conn.execute(
                        "SELECT mod_count_30d FROM ast_symbol_activation WHERE symbol_id=?",
                        (sym_id,),
                    ).fetchone()
                    n["git_heat"] = int(heat_row[0]) if heat_row else 0
                    caller_row = conn.execute(
                        "SELECT COUNT(*) FROM edges WHERE callee_symbol_id=? AND kind='calls'",
                        (sym_id,),
                    ).fetchone()
                    n["caller_count"] = int(caller_row[0]) if caller_row else 0
                except Exception:
                    n["git_heat"] = 0
                    n["caller_count"] = 0
                n["combined_score"] = round(
                    _score_symbol_full(
                        n["similarity"],
                        git_heat=n["git_heat"],
                        caller_count=n["caller_count"],
                    ),
                    4,
                )
            neighbors.sort(key=lambda x: x["combined_score"], reverse=True)

        return {
            "success": True,
            "model": model_used,
            "query": query,
            "count": len(neighbors),
            "neighbors": neighbors,
        }


def build_semantic_neighbors_tool(project_root: str | None) -> SemanticNeighborsTool:
    """Factory function for the ``semantic_neighbors`` MCP tool."""
    return SemanticNeighborsTool(project_root)
