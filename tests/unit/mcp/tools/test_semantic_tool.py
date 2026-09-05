"""Tests for tree_sitter_analyzer.mcp.tools.semantic_tool.

Covers: SemanticNeighborsTool.execute() — embed model selection, error paths,
combined_score reranking, and cache unavailability.
Target coverage: ~75-82% of semantic_tool.py.

Mock strategy: patch both pipeline and semantic_tool module namespaces for
_embed_with_openai and _embed_with_unixcoder (due to re-import at lines 116-119).
"""

from __future__ import annotations

import struct
from unittest.mock import MagicMock

from tree_sitter_analyzer.mcp.tools.semantic_tool import SemanticNeighborsTool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_cache(conn):
    fake = MagicMock()
    fake.get_conn.return_value = conn
    return fake


def _seed_symbol(conn, name: str, file_path: str = "a.py", language: str = "python", line: int = 1) -> int:
    cur = conn.execute(
        "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, "function", file_path, language, line, line + 5),
    )
    conn.commit()
    return cur.lastrowid


def _seed_embedding(conn, symbol_id: int, vec: list[float]) -> None:
    blob = struct.pack(f"<{len(vec)}f", *vec)
    conn.execute(
        "INSERT INTO symbol_embeddings (symbol_id, model, vector, input_text, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (symbol_id, "test", blob, "", 0),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_no_embedding_model_available(mock_embed_models):
    """Both embed functions raise → success=False with 'No embedding model available'."""
    mock_openai, mock_unixcoder = mock_embed_models
    mock_openai.side_effect = RuntimeError("no openai")
    mock_unixcoder.side_effect = RuntimeError("no unixcoder")

    tool = SemanticNeighborsTool(project_root=None)
    result = await tool.execute({"query": "find database connection"})
    assert result["success"] is False
    assert "No embedding model available" in result["error"]


async def test_empty_neighbors_hint(mock_embed_models, ast_cache_conn):
    """Embed succeeds but no neighbors found → success=True with 'pipeline' hint."""
    mock_openai, _ = mock_embed_models
    mock_openai.return_value = [[0.1, 0.2]]
    mock_openai.side_effect = None

    tool = SemanticNeighborsTool(project_root=None)
    tool._get_cache = MagicMock(return_value=_make_fake_cache(ast_cache_conn))

    result = await tool.execute({"query": "find something"})
    assert result["success"] is True
    assert result["neighbors"] == []
    assert "pipeline" in result.get("hint", "").lower()


async def test_combined_score_reranking(mock_embed_models, ast_cache_conn):
    """use_combined_score=True → results sorted by combined_score descending."""
    mock_openai, _ = mock_embed_models
    # Return a query vector aligned with [1.0, 0.0]
    mock_openai.return_value = [[1.0, 0.0]]
    mock_openai.side_effect = None

    # Seed two symbols with embeddings
    id_a = _seed_symbol(ast_cache_conn, "fn_high", line=1)
    id_b = _seed_symbol(ast_cache_conn, "fn_low", line=2)
    _seed_embedding(ast_cache_conn, id_a, [1.0, 0.0])   # high similarity
    _seed_embedding(ast_cache_conn, id_b, [0.5, 0.5])   # lower similarity

    tool = SemanticNeighborsTool(project_root=None)
    tool._get_cache = MagicMock(return_value=_make_fake_cache(ast_cache_conn))

    result = await tool.execute({
        "query": "database",
        "use_combined_score": True,
        "min_similarity": 0.0,
    })
    assert result["success"] is True
    neighbors = result["neighbors"]
    assert len(neighbors) == 2
    # Verify combined_score is present and sorted descending
    scores = [n["combined_score"] for n in neighbors]
    assert scores == sorted(scores, reverse=True)


async def test_get_cache_raises_returns_error(mock_embed_models):
    """Cache unavailable → success=False error response."""
    mock_openai, _ = mock_embed_models
    mock_openai.return_value = [[0.1, 0.2]]
    mock_openai.side_effect = None

    tool = SemanticNeighborsTool(project_root=None)
    tool._get_cache = MagicMock(side_effect=ValueError("no project root"))

    result = await tool.execute({"query": "find function"})
    assert result["success"] is False
    assert "no project root" in result["error"]
