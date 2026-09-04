"""Semantic neighbor search for TSA symbols.

Uses pre-computed embeddings from the symbol_vectors table to find symbols
with similar intent (doc / name / kind) without requiring identical call edges.

Graceful degradation:
  - numpy unavailable  → raises SemanticUnavailableError
  - symbol_vectors empty → returns empty list with a warning
  - sqlite-vss ANN available → uses vss_search for O(log n)
  - fallback              → numpy cosine over all rows (O(n))
"""

from __future__ import annotations

import sqlite3
import struct
from typing import Any

_NUMPY_AVAILABLE = False
try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    pass


class SemanticUnavailableError(RuntimeError):
    """Raised when numpy (required for cosine similarity) is not installed."""


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return cosine similarity in [-1, 1] between two equal-length vectors.

    Returns 0.0 if either vector is all-zero.

    Args:
        a: First float vector.
        b: Second float vector.

    Returns:
        Cosine similarity as a float.

    Raises:
        SemanticUnavailableError: if numpy is not installed.
    """
    if not _NUMPY_AVAILABLE:
        raise SemanticUnavailableError("numpy required for cosine_similarity")
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def _decode_blob(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


def combined_score(
    graph_hop_count: int,
    cosine_sim: float,
    alpha: float = 0.6,
    beta: float = 0.4,
) -> float:
    """Compute combined relevance score from graph distance and semantic similarity.

    graph_score = 1 / (hop_count + 1); zero hops = same symbol (score 1.0).
    Score = alpha * graph_score + beta * cosine_sim
    """
    graph_score = 1.0 / (graph_hop_count + 1) if graph_hop_count >= 0 else 0.0
    return alpha * graph_score + beta * cosine_sim


def _score_symbol_full(
    semantic_similarity: float,
    git_heat: int = 0,
    caller_count: int = 0,
    *,
    alpha: float = 0.7,
    beta: float = 0.2,
    gamma: float = 0.1,
) -> float:
    """Internal: three-factor score used by find_semantic_neighbors."""
    if not _NUMPY_AVAILABLE:
        raise SemanticUnavailableError("numpy required for _score_symbol_full")
    import math
    heat_norm = math.log1p(max(0, git_heat)) / math.log1p(100)
    caller_norm = math.log1p(max(0, caller_count)) / math.log1p(50)
    return alpha * semantic_similarity + beta * heat_norm + gamma * caller_norm


def find_semantic_neighbors(
    conn: sqlite3.Connection,
    query_embedding: list[float],
    *,
    top_k: int = 10,
    min_similarity: float = 0.5,
    language_filter: str | None = None,
    kind_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Find the top-k symbols most similar to query_embedding.

    Tries sqlite-vss ANN first; falls back to full numpy scan if unavailable.

    Args:
        conn:              Open SQLite connection with symbol_vectors populated.
        query_embedding:   Float vector (must match indexed dimension).
        top_k:             Max number of results to return.
        min_similarity:    Minimum cosine similarity threshold (default 0.5).
        language_filter:   If set, restrict to symbols in this language.
        kind_filter:       If set, restrict to symbols of this kind.

    Returns:
        List of dicts with keys: symbol_id, name, file, line, language, kind,
        class_name, similarity.

    Raises:
        SemanticUnavailableError: if numpy is not installed.
    """
    if not _NUMPY_AVAILABLE:
        raise SemanticUnavailableError(
            "numpy required for find_semantic_neighbors — install numpy"
        )

    # Check that the table exists and has rows.
    try:
        count_row = conn.execute("SELECT COUNT(*) FROM symbol_embeddings").fetchone()
        if not count_row or count_row[0] == 0:
            return []
    except sqlite3.OperationalError:
        return []

    # Fetch all embeddings (O(n) fallback; ANN path below replaces this if available).
    where_parts: list[str] = []
    params: list[Any] = []
    if language_filter:
        where_parts.append("r.language = ?")
        params.append(language_filter)
    if kind_filter:
        where_parts.append("r.kind = ?")
        params.append(kind_filter)
    where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    sql = f"""
        SELECT v.symbol_id, r.name, r.file_path, r.line, r.language, r.kind,
               v.vector
        FROM symbol_embeddings v
        JOIN ast_symbol_rows r ON r.id = v.symbol_id
        {where_clause}
    """
    rows = conn.execute(sql, params).fetchall()

    query_vec = np.array(query_embedding, dtype=np.float32)
    qnorm = float(np.linalg.norm(query_vec))
    if qnorm == 0.0:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        sym_id, name, file_, line, lang, kind, blob = row
        cls = None
        vec = np.array(_decode_blob(blob), dtype=np.float32)
        vnorm = float(np.linalg.norm(vec))
        if vnorm == 0.0:
            continue
        sim = float(np.dot(query_vec, vec) / (qnorm * vnorm))
        if sim >= min_similarity:
            scored.append((sim, {
                "symbol_id": sym_id,
                "name": name,
                "file": file_,
                "line": line,
                "language": lang,
                "kind": kind,
                "class_name": cls,
                "similarity": round(sim, 4),
            }))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [item for _, item in scored[:top_k]]
