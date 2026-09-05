"""Tests for tree_sitter_analyzer.api.semantic.

Covers: cosine_similarity, combined_score, find_semantic_neighbors.
Target coverage: ~90%+ of api/semantic.py reachable lines.
"""

from __future__ import annotations

import sqlite3
import struct

import pytest

from tree_sitter_analyzer.api.semantic import (
    combined_score,
    cosine_similarity,
    find_semantic_neighbors,
)

# ---------------------------------------------------------------------------
# Private seed helpers
# ---------------------------------------------------------------------------

def _seed_symbol(
    conn,
    name: str,
    kind: str = "function",
    file_path: str = "a.py",
    language: str = "python",
    line: int = 1,
) -> int:
    """INSERT a row into ast_symbol_rows and return its rowid."""
    cur = conn.execute(
        "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, kind, file_path, language, line, line + 5),
    )
    conn.commit()
    return cur.lastrowid


def _seed_embedding(conn, symbol_id: int, vec: list[float]) -> None:
    """INSERT a row into symbol_embeddings with the given float vector."""
    blob = struct.pack(f"<{len(vec)}f", *vec)
    conn.execute(
        "INSERT INTO symbol_embeddings (symbol_id, model, vector, input_text, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (symbol_id, "test", blob, "", 0),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# cosine_similarity
# ---------------------------------------------------------------------------

def test_cosine_similarity_identical_vectors():
    result = cosine_similarity([1.0, 0.0], [1.0, 0.0])
    assert result == pytest.approx(1.0)


def test_cosine_similarity_zero_vector_first():
    result = cosine_similarity([0.0, 0.0], [1.0, 0.0])
    assert result == 0.0


def test_cosine_similarity_zero_vector_second():
    result = cosine_similarity([1.0, 0.0], [0.0, 0.0])
    assert result == 0.0


def test_cosine_similarity_orthogonal():
    result = cosine_similarity([1.0, 0.0], [0.0, 1.0])
    assert result == pytest.approx(0.0, abs=1e-6)


def test_cosine_similarity_negative_values():
    assert cosine_similarity([-1.0, 0.0], [-1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# combined_score
# ---------------------------------------------------------------------------

def test_combined_score_zero_hops():
    # graph_score = 1/(0+1) = 1.0, alpha=0.6, beta=0.4
    result = combined_score(0, 0.5)
    assert result == pytest.approx(0.6 * 1.0 + 0.4 * 0.5)


def test_combined_score_one_hop():
    # graph_score = 1/(1+1) = 0.5
    result = combined_score(1, 1.0)
    assert result == pytest.approx(0.6 * 0.5 + 0.4 * 1.0)


def test_combined_score_negative_hops():
    # implementation detail, not in spec: negative hops → graph_score = 0
    result = combined_score(-1, 0.5)
    assert result == pytest.approx(0.0 + 0.4 * 0.5)


# ---------------------------------------------------------------------------
# find_semantic_neighbors
# ---------------------------------------------------------------------------

def test_find_semantic_neighbors_empty_table(ast_cache_conn):
    result = find_semantic_neighbors(ast_cache_conn, [1.0, 0.0])
    assert result == []


def test_find_semantic_neighbors_missing_table():
    """No symbol_embeddings table → returns [] gracefully (OperationalError caught)."""
    bare_conn = sqlite3.connect(":memory:")
    result = find_semantic_neighbors(bare_conn, [1.0, 0.0])
    assert result == []
    bare_conn.close()


def test_find_semantic_neighbors_min_similarity_filter(ast_cache_conn):
    """Only symbols above min_similarity threshold are returned."""
    id_a = _seed_symbol(ast_cache_conn, "sym_a", language="python")
    id_b = _seed_symbol(ast_cache_conn, "sym_b", language="python")
    _seed_embedding(ast_cache_conn, id_a, [1.0, 0.0])   # identical to query
    _seed_embedding(ast_cache_conn, id_b, [0.0, 1.0])   # orthogonal to query

    result = find_semantic_neighbors(
        ast_cache_conn, [1.0, 0.0], min_similarity=0.9
    )
    names = [r["name"] for r in result]
    assert "sym_a" in names
    assert "sym_b" not in names


def test_find_semantic_neighbors_top_k(ast_cache_conn):
    """top_k caps the number of results."""
    for i in range(3):
        sid = _seed_symbol(ast_cache_conn, f"sym_{i}", language="python", line=i + 1)
        _seed_embedding(ast_cache_conn, sid, [1.0, float(i) * 0.01])

    result = find_semantic_neighbors(ast_cache_conn, [1.0, 0.0], top_k=2, min_similarity=0.0)
    assert len(result) <= 2


def test_find_semantic_neighbors_language_filter(ast_cache_conn):
    """language_filter restricts results to the given language."""
    id_py = _seed_symbol(ast_cache_conn, "fn_py", language="python")
    id_rs = _seed_symbol(ast_cache_conn, "fn_rs", language="rust")
    _seed_embedding(ast_cache_conn, id_py, [1.0, 0.0])
    _seed_embedding(ast_cache_conn, id_rs, [1.0, 0.0])

    result = find_semantic_neighbors(
        ast_cache_conn, [1.0, 0.0], min_similarity=0.0, language_filter="python"
    )
    names = [r["name"] for r in result]
    assert "fn_py" in names
    assert "fn_rs" not in names


def test_find_semantic_neighbors_zero_query_vector(ast_cache_conn):
    """Zero-length query vector → returns [] without crashing."""
    sid = _seed_symbol(ast_cache_conn, "fn_x")
    _seed_embedding(ast_cache_conn, sid, [1.0, 0.0])
    result = find_semantic_neighbors(ast_cache_conn, [0.0, 0.0])
    assert result == []


def test_find_semantic_neighbors_kind_filter(ast_cache_conn):
    """kind_filter restricts results to the given symbol kind."""
    id_fn = _seed_symbol(ast_cache_conn, "my_fn", kind="function")
    id_cls = _seed_symbol(ast_cache_conn, "my_cls", kind="class")
    _seed_embedding(ast_cache_conn, id_fn, [1.0, 0.0])
    _seed_embedding(ast_cache_conn, id_cls, [1.0, 0.0])

    result = find_semantic_neighbors(
        ast_cache_conn, [1.0, 0.0], min_similarity=0.0, kind_filter="function"
    )
    names = [r["name"] for r in result]
    assert "my_fn" in names
    assert "my_cls" not in names
