"""MCP tool: semantic_neighbors — find symbols similar to a query by embedding.

Requires:
  - numpy
  - symbol_embeddings table populated (run embeddings pipeline first)

Graceful degradation:
  - numpy missing     → error response with install hint
  - 向量缺失或存储不可用时明确失败，不能冒充有效零匹配
"""

from __future__ import annotations

import math
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
                "stored in the symbol_embeddings table. "
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
                        "minLength": 1,
                        "description": (
                            "Natural language description of what you are looking for, "
                            "e.g. 'function that validates user input' or "
                            "'class handling database connection pooling'."
                        ),
                    },
                    "top_k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "default": 10,
                        "description": "Max number of results (1-50, default 10)",
                    },
                    "min_similarity": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
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
        return self.get_tool_definition()["inputSchema"]["properties"]  # type: ignore[no-any-return]

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if (
            not isinstance(arguments.get("query"), str)
            or not arguments["query"].strip()
        ):
            raise ValueError("query is required and must be a non-empty string")
        top_k = arguments.get("top_k", 10)
        if isinstance(top_k, float) and top_k.is_integer():
            top_k = int(top_k)
        if type(top_k) is not int or not 1 <= top_k <= 50:
            raise ValueError("top_k must be an integer between 1 and 50")
        arguments["top_k"] = top_k
        min_sim = arguments.get("min_similarity", 0.5)
        if type(min_sim) not in (int, float) or not 0 <= min_sim <= 1:
            raise ValueError("min_similarity must be a finite number between 0 and 1")
        for key in ("language", "kind"):
            if key in arguments and not isinstance(arguments[key], str):
                raise ValueError(f"{key} must be a string")
        if type(arguments.get("use_combined_score", False)) is not bool:
            raise ValueError("use_combined_score must be a boolean")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from ...api.semantic import (
            _NUMPY_AVAILABLE,
            _score_symbol_full,
            find_semantic_neighbors,
        )
        from ...embeddings.pipeline import (
            _embed_with_openai,
            _embed_with_unixcoder,
        )

        arguments = dict(arguments)
        try:
            self.validate_arguments(arguments)
        except ValueError as exc:
            return {
                "success": False,
                "error_code": "INVALID_ARGUMENT",
                "error": str(exc),
                "count": 0,
                "neighbors": [],
            }
        query = arguments["query"].strip()
        top_k = arguments["top_k"]
        min_sim = arguments.get("min_similarity", 0.5)
        language = arguments.get("language") or None
        kind = arguments.get("kind") or None
        use_combined = arguments.get("use_combined_score", False)
        if not _NUMPY_AVAILABLE:
            return {
                "success": False,
                "error": "numpy required for semantic search",
                "count": 0,
                "neighbors": [],
            }

        try:
            cache = self._get_cache()
            conn = cache.get_conn()
        except Exception as exc:
            return {"success": False, "error": str(exc), "neighbors": []}

        # 模型身份和维度属于存储契约，不能按本机可用性回退到另一向量空间。
        try:
            spaces = conn.execute(
                "SELECT DISTINCT model, length(vector), typeof(vector) FROM symbol_embeddings LIMIT 3"
            ).fetchall()
            if not spaces:
                raise ValueError(
                    "EMBEDDINGS_NOT_INDEXED: run the embedding pipeline first"
                )
            if len({r[0] for r in spaces}) != 1:
                raise ValueError("MIXED_EMBEDDING_MODELS")
            stored_model = spaces[0][0]
            if stored_model not in ("text-embedding-3-small", "unixcoder-base"):
                raise ValueError(f"UNKNOWN_EMBEDDING_MODEL: {stored_model}")
            if len(spaces) != 1:
                raise ValueError("MIXED_EMBEDDING_DIMENSIONS")
            byte_count = spaces[0][1]
            if spaces[0][2] != "blob" or not byte_count or byte_count % 4:
                raise ValueError("INVALID_EMBEDDING_DIMENSION")
            dimension = byte_count // 4
            if dimension > 1536 or (
                stored_model == "unixcoder-base" and dimension != 768
            ):
                raise ValueError("INVALID_EMBEDDING_DIMENSION")
        except Exception as exc:
            return {"success": False, "error": str(exc), "neighbors": []}

        # 评分依赖不可用时，先失败再调用 provider，不能伪造零热度或浪费请求。
        if use_combined:
            try:
                conn.execute(
                    "SELECT symbol_id, mod_count_30d FROM ast_symbol_activation LIMIT 0"
                )
                conn.execute("SELECT callee_symbol_id, kind FROM edges LIMIT 0")
                # 组合评分依赖已计算热度；不能消费 lazy 占位或已失效的旧投影。
                if conn.execute(
                    "SELECT 1 FROM ast_symbol_activation "
                    "WHERE activation_state IN ('pending','disabled') LIMIT 1"
                ).fetchone():
                    raise ValueError("activation pending or disabled")
            except Exception as exc:
                return {
                    "success": False,
                    "error": f"COMBINED_SCORE_UNAVAILABLE: {exc}",
                    "count": 0,
                    "neighbors": [],
                }

        try:
            if stored_model == "text-embedding-3-small":
                query_vec = _embed_with_openai([query], dimensions=dimension)[0]
                model_used = "openai"
            else:
                query_vec = _embed_with_unixcoder([query])[0]
                model_used = "unixcoder"
        except Exception as exc:
            return {
                "success": False,
                "error": f"No embedding model available for {stored_model}: {exc}",
                "neighbors": [],
            }
        if len(query_vec) != dimension:
            return {
                "success": False,
                "error": "QUERY_EMBEDDING_DIMENSION_MISMATCH",
                "neighbors": [],
            }
        if any(
            type(value) not in (int, float) or not math.isfinite(value)
            for value in query_vec
        ):
            return {
                "success": False,
                "error": "INVALID_QUERY_EMBEDDING",
                "count": 0,
                "neighbors": [],
            }

        try:
            neighbors = find_semantic_neighbors(
                conn,
                query_vec,
                query_model=stored_model,
                top_k=top_k,
                min_similarity=min_sim,
                language_filter=language,
                kind_filter=kind,
            )
        except Exception as exc:
            return {
                "success": False,
                "error": f"semantic search failed: {exc}",
                "neighbors": [],
            }

        if not neighbors:
            return {
                "success": True,
                "model": model_used,
                "query": query,
                "count": 0,
                "neighbors": [],
                "hint": "No neighbors meet the requested filters or similarity threshold.",
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
                except Exception as exc:
                    return {
                        "success": False,
                        "error": f"COMBINED_SCORE_UNAVAILABLE: {exc}",
                        "count": 0,
                        "neighbors": [],
                    }
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
