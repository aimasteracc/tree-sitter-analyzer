"""使用 symbol_embeddings 中的预计算向量检索语义相近符号。

查询向量必须明确声明模型身份并匹配候选维度。当前实现使用 NumPy 计算余弦
相似度；缺少依赖或存储损坏时显式失败，健康空表或无匹配时返回空列表。
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
    """计算余弦相似度所需的 NumPy 不可用。"""


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个等长浮点向量的余弦相似度，范围为 [-1, 1]。

    任一向量全零时返回 0.0；缺少 NumPy 时抛 SemanticUnavailableError。
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
    """按图距离与语义相似度计算组合相关性。

    图分数为 1 / (hop_count + 1)，零跳代表同一符号、分数为 1。
    最终分数为 alpha * graph_score + beta * cosine_sim。
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
    """MCP 组合排序使用的纯算术评分，不依赖 NumPy。"""
    import math

    heat_norm = math.log1p(max(0, git_heat)) / math.log1p(100)
    caller_norm = math.log1p(max(0, caller_count)) / math.log1p(50)
    return alpha * semantic_similarity + beta * heat_norm + gamma * caller_norm


def find_semantic_neighbors(
    conn: sqlite3.Connection,
    query_embedding: list[float],
    *,
    query_model: str,
    top_k: int = 10,
    min_similarity: float = 0.5,
    language_filter: str | None = None,
    kind_filter: str | None = None,
) -> list[dict[str, Any]]:
    """按余弦相似度返回同模型、同维度的候选符号；身份不匹配抛 ValueError。

    query_model 是必需的生成模型声明，不能从维度推断或使用默认身份。

    参数：
        conn：已打开且包含 symbol_embeddings 的 SQLite 连接。
        query_embedding：与候选维度一致的查询浮点向量。
        query_model：查询向量生成模型的明确标识。
        top_k：最多返回的结果数量。
        min_similarity：最低余弦相似度，默认 0.5。
        language_filter、kind_filter：可选语言及符号类型筛选。

    返回包含 symbol_id、name、file、line、language、kind、class_name、similarity
    的字典列表；缺少 NumPy 时抛 SemanticUnavailableError。
    """
    if not _NUMPY_AVAILABLE:
        raise SemanticUnavailableError(
            "numpy required for find_semantic_neighbors — install numpy"
        )
    if not isinstance(query_model, str) or not query_model.strip():
        raise ValueError("query_model must be a non-empty model identifier")

    # 直接读取向量：健康空表自然返回空列表，存储错误必须传播给公开错误边界。
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
               v.vector, v.model
        FROM symbol_embeddings v
        JOIN ast_symbol_rows r ON r.id = v.symbol_id
        {where_clause}
    """
    rows = conn.execute(sql, params).fetchall()
    if any(row[7] != query_model for row in rows):
        raise ValueError("EMBEDDING_MODEL_MISMATCH")
    if any(len(row[6]) != len(query_embedding) * 4 for row in rows):
        raise ValueError("EMBEDDING_DIMENSION_MISMATCH")

    query_vec = np.array(query_embedding, dtype=np.float32)
    qnorm = float(np.linalg.norm(query_vec))
    if qnorm == 0.0:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        sym_id, name, file_, line, lang, kind, blob, _model = row
        cls = None
        vec = np.array(_decode_blob(blob), dtype=np.float32)
        if not np.isfinite(vec).all():
            raise ValueError("INVALID_STORED_EMBEDDING")
        vnorm = float(np.linalg.norm(vec))
        if vnorm == 0.0:
            continue
        sim = float(np.dot(query_vec, vec) / (qnorm * vnorm))
        if sim >= min_similarity:
            scored.append(
                (
                    sim,
                    {
                        "symbol_id": sym_id,
                        "name": name,
                        "file": file_,
                        "line": line,
                        "language": lang,
                        "kind": kind,
                        "class_name": cls,
                        "similarity": round(sim, 4),
                    },
                )
            )

    scored.sort(key=lambda t: t[0], reverse=True)
    return [item for _, item in scored[:top_k]]
