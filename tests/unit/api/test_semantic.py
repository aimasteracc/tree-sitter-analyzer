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


def test_query_model_is_mandatory_even_for_identical_dimension(ast_cache_conn):
    """PR #1352 P2：维度相同不能证明模型相同；没有显式查询身份必须拒绝。"""
    sid = _seed_symbol(ast_cache_conn, "candidate")
    _seed_embedding(ast_cache_conn, sid, [1.0, 0.0])
    with pytest.raises(TypeError, match="query_model"):
        find_semantic_neighbors(ast_cache_conn, [1.0, 0.0])


def test_query_model_mismatch_rejected_even_when_vectors_identical(ast_cache_conn):
    """PR #1352 P2：相同浮点值、相同维度，但来自不同模型时不能报告相似度。"""
    sid = _seed_symbol(ast_cache_conn, "candidate")
    _seed_embedding(ast_cache_conn, sid, [1.0, 0.0])
    with pytest.raises(ValueError, match="EMBEDDING_MODEL_MISMATCH"):
        find_semantic_neighbors(ast_cache_conn, [1.0, 0.0], query_model="another-model")


@pytest.mark.parametrize("identity", [None, "", " ", 7])
def test_query_model_has_no_invalid_default(ast_cache_conn, identity):
    """PR #1352 P2：空或非字符串身份不得触发默认模型推断。"""
    with pytest.raises(
        ValueError, match="query_model must be a non-empty model identifier"
    ):
        find_semantic_neighbors(ast_cache_conn, [1.0, 0.0], query_model=identity)


def test_query_model_rejects_mixed_same_dimension_rows(ast_cache_conn):
    """PR #1352 P2：索引中任一候选来自另一模型时不能部分比较后返回成功。"""
    for name in ("own", "foreign"):
        _seed_embedding(ast_cache_conn, _seed_symbol(ast_cache_conn, name), [1.0, 0.0])
    ast_cache_conn.execute(
        "UPDATE symbol_embeddings SET model='other' WHERE symbol_id=(SELECT id FROM ast_symbol_rows WHERE name='foreign')"
    )
    with pytest.raises(ValueError, match="EMBEDDING_MODEL_MISMATCH"):
        find_semantic_neighbors(ast_cache_conn, [1.0, 0.0], query_model="test")


def test_query_dimension_is_checked_independently_of_model(ast_cache_conn):
    """PR #1352 P2：模型身份相同仍必须核对维度，不能依赖 NumPy 广播或偶然异常。"""
    _seed_embedding(
        ast_cache_conn, _seed_symbol(ast_cache_conn, "candidate"), [1.0, 0.0, 0.0]
    )
    with pytest.raises(ValueError, match="EMBEDDING_DIMENSION_MISMATCH"):
        find_semantic_neighbors(ast_cache_conn, [1.0, 0.0], query_model="test")


@pytest.mark.parametrize(
    "damage",
    ["mixed_models", "mixed_dimensions", "unknown", "empty", "text", "odd_blob"],
)
def test_invalid_incremental_space_requires_rebuild_before_provider(
    ast_cache_conn, openai_transport, damage
):
    """PR #1352 P2：损坏或混合空间必须先重建，不能只按 symbol_id 跳过坏向量再声称成功。"""
    from tree_sitter_analyzer.embeddings.pipeline import run_pipeline

    for name in ("first", "second"):
        _seed_embedding(ast_cache_conn, _seed_symbol(ast_cache_conn, name), [1.0, 0.0])
    ast_cache_conn.execute(
        "UPDATE symbol_embeddings SET model='text-embedding-3-small'"
    )
    model, vector = {
        "mixed_models": ("unixcoder-base", struct.pack("<2f", 1.0, 0.0)),
        "mixed_dimensions": (
            "text-embedding-3-small",
            struct.pack("<3f", 1.0, 0.0, 0.0),
        ),
        "unknown": ("unknown-model", struct.pack("<2f", 1.0, 0.0)),
        "empty": ("text-embedding-3-small", b""),
        "text": ("text-embedding-3-small", "12345678"),
        "odd_blob": ("text-embedding-3-small", b"abc"),
    }[damage]
    if damage in ("mixed_models", "mixed_dimensions"):
        ast_cache_conn.execute(
            "UPDATE symbol_embeddings SET model=?,vector=? WHERE symbol_id=(SELECT id FROM ast_symbol_rows WHERE name='second')",
            (model, vector),
        )
    else:
        ast_cache_conn.execute(
            "UPDATE symbol_embeddings SET model=?,vector=?", (model, vector)
        )
    before = [
        tuple(r) for r in ast_cache_conn.execute("SELECT * FROM symbol_embeddings")
    ]
    with pytest.raises(ValueError, match="EMBEDDING_SPACE_INVALID.*rebuild=True"):
        run_pipeline(ast_cache_conn)
    openai_transport.assert_not_called()
    assert [
        tuple(r) for r in ast_cache_conn.execute("SELECT * FROM symbol_embeddings")
    ] == before


@pytest.mark.parametrize("count", [0, 2])
def test_provider_cardinality_cannot_misattribute_vectors(
    ast_cache_conn, openai_transport, count
):
    """PR #1352 P2：provider 返回条数必须匹配该批符号，不能忽略额外向量或部分写入。"""
    from types import SimpleNamespace

    from tree_sitter_analyzer.embeddings.pipeline import run_pipeline

    _seed_symbol(ast_cache_conn, "candidate")
    openai_transport.side_effect = lambda **kwargs: SimpleNamespace(
        data=[SimpleNamespace(embedding=[1.0, 0.0]) for _ in range(count)]
    )
    result = run_pipeline(ast_cache_conn, model="openai")
    assert (result["indexed"], result["errors"]) == (0, 1)
    assert ast_cache_conn.execute("SELECT * FROM symbol_embeddings").fetchall() == []


def test_incremental_space_rechecked_after_external_rpc(tmp_path, openai_transport):
    """PR #1352 P2：另一 WAL 连接在 provider 请求期间重建模型，旧请求不能再写入另一空间。"""
    from types import SimpleNamespace

    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.embeddings.pipeline import (
        init_embeddings_db,
        run_pipeline,
    )

    cache = ASTCache(str(tmp_path))
    try:
        old = tmp_path / "old.py"
        old.write_text("def old():\n    pass\n", encoding="utf-8")
        cache.index_file(str(old))
        conn = cache.get_conn()
        init_embeddings_db(conn)
        run_pipeline(conn, model="openai")
        new = tmp_path / "new.py"
        new.write_text("def new():\n    pass\n", encoding="utf-8")
        cache.index_file(str(new))

        def rpc(**kwargs):
            with sqlite3.connect(cache.db_path) as writer:
                writer.execute("UPDATE symbol_embeddings SET model='unixcoder-base'")
            return SimpleNamespace(data=[SimpleNamespace(embedding=[1.0, 0.0])])

        openai_transport.side_effect = rpc
        result = run_pipeline(conn)
        assert (result["indexed"], result["errors"]) == (0, 1)
        assert [
            tuple(r)
            for r in conn.execute(
                "SELECT model,count(*) FROM symbol_embeddings GROUP BY model"
            )
        ] == [("unixcoder-base", 1)]
    finally:
        cache.close()


def test_auto_continues_local_model_without_trying_available_remote(
    ast_cache_conn, openai_transport, unixcoder_transport
):
    """PR #1352 P2：本地索引的 auto 增量只能继续本地模型，即使远程 provider 同时可用。"""
    from tree_sitter_analyzer.embeddings.pipeline import run_pipeline

    _seed_symbol(ast_cache_conn, "old")
    run_pipeline(ast_cache_conn, model="unixcoder")
    _seed_symbol(ast_cache_conn, "new")
    result = run_pipeline(ast_cache_conn)
    assert (
        result["model_name"],
        result["indexed"],
        result["skipped"],
        result["errors"],
    ) == ("unixcoder-base", 1, 1, 0)
    assert [
        tuple(r)
        for r in ast_cache_conn.execute(
            "SELECT model,count(*) FROM symbol_embeddings GROUP BY model"
        )
    ] == [("unixcoder-base", 2)]
    openai_transport.assert_not_called()


def test_model_switch_rebuild_rolls_back_completed_batches(
    ast_cache_conn, openai_transport, unixcoder_transport
):
    """PR #1352 P2：跨模型重建在后续 provider 批次失败时，已写批次和模型标签必须整体回滚。"""
    from tree_sitter_analyzer.embeddings.pipeline import run_pipeline

    for name in ("first", "second"):
        _seed_symbol(ast_cache_conn, name)
    run_pipeline(ast_cache_conn, model="openai")
    before = [
        tuple(r)
        for r in ast_cache_conn.execute(
            "SELECT * FROM symbol_embeddings ORDER BY symbol_id"
        )
    ]
    openai_transport.reset_mock()
    unixcoder_transport.side_effect = [
        [0.0, 1.0],
        [0.0, 1.0],
        RuntimeError("second batch refused"),
    ]
    result = run_pipeline(ast_cache_conn, model="unixcoder", rebuild=True, batch_size=1)
    assert (result["indexed"], result["errors"]) == (0, 2)
    assert [
        tuple(r)
        for r in ast_cache_conn.execute(
            "SELECT * FROM symbol_embeddings ORDER BY symbol_id"
        )
    ] == before
    openai_transport.assert_not_called()


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


def test_internal_arithmetic_score_does_not_require_numpy(monkeypatch):
    # PR #1352：私有纯算术评分不应因无关的 NumPy 可用性而失败。
    from tree_sitter_analyzer.api import semantic

    monkeypatch.setattr(semantic, "_NUMPY_AVAILABLE", False)
    assert (
        semantic._score_symbol_full(1.0, 100, 50, alpha=0.5, beta=0.25, gamma=0.25)
        == 1.0
    )


def test_public_search_still_requires_numpy_before_sql(ast_cache_conn, monkeypatch):
    # PR #1352：公开搜索确实依赖 NumPy，缺依赖时必须在访问索引前失败。
    from tree_sitter_analyzer.api import semantic

    monkeypatch.setattr(semantic, "_NUMPY_AVAILABLE", False)
    statements = []
    ast_cache_conn.set_trace_callback(statements.append)
    with pytest.raises(
        semantic.SemanticUnavailableError,
        match="numpy required for find_semantic_neighbors",
    ):
        semantic.find_semantic_neighbors(ast_cache_conn, [1.0, 0.0], query_model="test")
    assert statements == []


# ---------------------------------------------------------------------------
# find_semantic_neighbors
# ---------------------------------------------------------------------------


def test_find_semantic_neighbors_empty_table(ast_cache_conn):
    result = find_semantic_neighbors(ast_cache_conn, [1.0, 0.0], query_model="test")
    assert result == []


def test_find_semantic_neighbors_missing_table():
    """PR #1352：缺失向量表不是健康的空索引，Python API 也必须保留存储错误。"""
    bare_conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(
            sqlite3.OperationalError, match="no such table: symbol_embeddings"
        ):
            find_semantic_neighbors(bare_conn, [1.0, 0.0], query_model="test")
    finally:
        bare_conn.close()


def test_find_semantic_neighbors_min_similarity_filter(ast_cache_conn):
    """Only symbols above min_similarity threshold are returned."""
    id_a = _seed_symbol(ast_cache_conn, "sym_a", language="python")
    id_b = _seed_symbol(ast_cache_conn, "sym_b", language="python")
    _seed_embedding(ast_cache_conn, id_a, [1.0, 0.0])  # identical to query
    _seed_embedding(ast_cache_conn, id_b, [0.0, 1.0])  # orthogonal to query

    result = find_semantic_neighbors(
        ast_cache_conn, [1.0, 0.0], query_model="test", min_similarity=0.9
    )
    names = [r["name"] for r in result]
    assert "sym_a" in names
    assert "sym_b" not in names


def test_find_semantic_neighbors_top_k(ast_cache_conn):
    """top_k caps the number of results."""
    for i in range(3):
        sid = _seed_symbol(ast_cache_conn, f"sym_{i}", language="python", line=i + 1)
        _seed_embedding(ast_cache_conn, sid, [1.0, float(i) * 0.01])

    result = find_semantic_neighbors(
        ast_cache_conn, [1.0, 0.0], query_model="test", top_k=2, min_similarity=0.0
    )
    assert len(result) <= 2


def test_find_semantic_neighbors_language_filter(ast_cache_conn):
    """language_filter restricts results to the given language."""
    id_py = _seed_symbol(ast_cache_conn, "fn_py", language="python")
    id_rs = _seed_symbol(ast_cache_conn, "fn_rs", language="rust")
    _seed_embedding(ast_cache_conn, id_py, [1.0, 0.0])
    _seed_embedding(ast_cache_conn, id_rs, [1.0, 0.0])

    result = find_semantic_neighbors(
        ast_cache_conn,
        [1.0, 0.0],
        query_model="test",
        min_similarity=0.0,
        language_filter="python",
    )
    names = [r["name"] for r in result]
    assert "fn_py" in names
    assert "fn_rs" not in names


def test_find_semantic_neighbors_zero_query_vector(ast_cache_conn):
    """Zero-length query vector → returns [] without crashing."""
    sid = _seed_symbol(ast_cache_conn, "fn_x")
    _seed_embedding(ast_cache_conn, sid, [1.0, 0.0])
    result = find_semantic_neighbors(ast_cache_conn, [0.0, 0.0], query_model="test")
    assert result == []


def test_find_semantic_neighbors_kind_filter(ast_cache_conn):
    """kind_filter restricts results to the given symbol kind."""
    id_fn = _seed_symbol(ast_cache_conn, "my_fn", kind="function")
    id_cls = _seed_symbol(ast_cache_conn, "my_cls", kind="class")
    _seed_embedding(ast_cache_conn, id_fn, [1.0, 0.0])
    _seed_embedding(ast_cache_conn, id_cls, [1.0, 0.0])

    result = find_semantic_neighbors(
        ast_cache_conn,
        [1.0, 0.0],
        query_model="test",
        min_similarity=0.0,
        kind_filter="function",
    )
    names = [r["name"] for r in result]
    assert "my_fn" in names
    assert "my_cls" not in names
