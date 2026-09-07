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

import pytest

from tree_sitter_analyzer.mcp.tools.semantic_tool import SemanticNeighborsTool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_cache(conn):
    fake = MagicMock()
    fake.get_conn.return_value = conn
    return fake


@pytest.mark.parametrize(
    "damage", ["vectors_disappear", "definition_table_disappears", "invalid_heat"]
)
async def test_semantic_store_damage_during_provider_request_is_failure(
    tmp_path, openai_transport, damage
):
    """PR #1352：外部请求期间真实数据库变化后，不得报成功空集或伪造热度。"""
    from types import SimpleNamespace

    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.embeddings import pipeline

    source = tmp_path / "a.py"
    source.write_text("def alpha():\n    pass\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_file(str(source))
        db = cache.get_conn()
        assert pipeline.init_embeddings_db(db) is True
        assert pipeline.run_pipeline(db, model="openai")["indexed"] == 1

        def rpc(**kwargs):
            if damage == "vectors_disappear":
                db.execute("DROP TABLE symbol_embeddings")
            elif damage == "definition_table_disappears":
                db.execute("ALTER TABLE ast_symbol_rows RENAME TO lost_symbols")
            else:
                db.execute(
                    "INSERT OR REPLACE INTO ast_symbol_activation(symbol_id,file_path,mod_count_30d,computed_at) SELECT id,file_path,'bad',0 FROM ast_symbol_rows"
                )
            return SimpleNamespace(data=[SimpleNamespace(embedding=[1.0, 0.0])])

        openai_transport.side_effect = rpc
        tool = SemanticNeighborsTool(str(tmp_path))
        tool._cache = cache
        result = await tool.execute(
            {"query": "alpha", "use_combined_score": damage == "invalid_heat"}
        )
        assert result["success"] is False
        assert result["neighbors"] == []
        prefix = (
            "COMBINED_SCORE_UNAVAILABLE:"
            if damage == "invalid_heat"
            else "semantic search failed:"
        )
        assert result["error"].startswith(prefix)
    finally:
        cache.close()


async def test_zero_stored_vector_is_not_a_similarity_match(tmp_path, openai_transport):
    """PR #1352：零向量没有余弦方向，不能凭阈值为零挤入结果。"""
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.embeddings import pipeline

    source = tmp_path / "a.py"
    source.write_text("def alpha():\n    pass\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_file(str(source))
        db = cache.get_conn()
        pipeline.init_embeddings_db(db)
        pipeline.run_pipeline(db, model="openai")
        db.execute(
            "UPDATE symbol_embeddings SET vector=?",
            (pipeline._encode_embedding([0.0, 0.0]),),
        )
        tool = SemanticNeighborsTool(str(tmp_path))
        tool._cache = cache
        result = await tool.execute({"query": "alpha", "min_similarity": 0})
        assert result["success"] is True
        assert (result["count"], result["neighbors"]) == (0, [])
    finally:
        cache.close()


async def test_nonfinite_stored_vector_is_corruption_not_zero_matches(
    tmp_path, openai_transport
):
    """PR #1352：格式大小正确但数值损坏的持久化向量不能伪装成无匹配。"""
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.embeddings import pipeline

    source = tmp_path / "a.py"
    source.write_text("def alpha():\n    pass\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_file(str(source))
        db = cache.get_conn()
        pipeline.init_embeddings_db(db)
        pipeline.run_pipeline(db, model="openai")
        db.execute(
            "UPDATE symbol_embeddings SET vector=?",
            (pipeline._encode_embedding([float("nan"), 0.0]),),
        )
        tool = SemanticNeighborsTool(str(tmp_path))
        tool._cache = cache
        result = await tool.execute({"query": "alpha"})
        assert result == {
            "success": False,
            "error": "semantic search failed: INVALID_STORED_EMBEDDING",
            "neighbors": [],
        }
    finally:
        cache.close()


def _seed_symbol(
    conn, name: str, file_path: str = "a.py", language: str = "python", line: int = 1
) -> int:
    cur = conn.execute(
        "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, "function", file_path, language, line, line + 5),
    )
    conn.commit()
    return cur.lastrowid


def _seed_embedding(
    conn, symbol_id: int, vec: list[float], model="text-embedding-3-small"
) -> None:
    blob = struct.pack(f"<{len(vec)}f", *vec)
    conn.execute(
        "INSERT INTO symbol_embeddings (symbol_id, model, vector, input_text, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (symbol_id, model, blob, "", 0),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_no_embedding_model_available(mock_embed_models, ast_cache_conn):
    """存储模型不可用时明确报错，不切换到另一向量空间。"""
    mock_openai, mock_unixcoder = mock_embed_models
    mock_openai.side_effect = RuntimeError("no openai")
    mock_unixcoder.side_effect = RuntimeError("no unixcoder")

    tool = SemanticNeighborsTool(project_root=None)
    sid = _seed_symbol(ast_cache_conn, "fn")
    _seed_embedding(ast_cache_conn, sid, [1.0, 0.0])
    tool._get_cache = MagicMock(return_value=_make_fake_cache(ast_cache_conn))
    result = await tool.execute({"query": "find database connection"})
    assert result["success"] is False
    assert "No embedding model available" in result["error"]
    mock_unixcoder.assert_not_called()


async def test_empty_neighbors_hint(mock_embed_models, ast_cache_conn):
    """未建立向量索引应明确失败，不能执行无依据的模型调用。"""
    mock_openai, _ = mock_embed_models
    mock_openai.return_value = [[0.1, 0.2]]
    mock_openai.side_effect = None

    tool = SemanticNeighborsTool(project_root=None)
    tool._get_cache = MagicMock(return_value=_make_fake_cache(ast_cache_conn))

    result = await tool.execute({"query": "find something"})
    assert result["success"] is False
    assert result["neighbors"] == []
    assert "EMBEDDINGS_NOT_INDEXED" in result["error"]
    mock_openai.assert_not_called()


async def test_combined_score_reranking(mock_embed_models, ast_cache_conn):
    """use_combined_score=True → results sorted by combined_score descending."""
    mock_openai, _ = mock_embed_models
    # Return a query vector aligned with [1.0, 0.0]
    mock_openai.return_value = [[1.0, 0.0]]
    mock_openai.side_effect = None

    # Seed two symbols with embeddings
    id_a = _seed_symbol(ast_cache_conn, "fn_high", line=1)
    id_b = _seed_symbol(ast_cache_conn, "fn_low", line=2)
    _seed_embedding(ast_cache_conn, id_a, [1.0, 0.0])  # high similarity
    _seed_embedding(ast_cache_conn, id_b, [0.5, 0.5])  # lower similarity

    tool = SemanticNeighborsTool(project_root=None)
    tool._get_cache = MagicMock(return_value=_make_fake_cache(ast_cache_conn))

    result = await tool.execute(
        {
            "query": "database",
            "use_combined_score": True,
            "min_similarity": 0.0,
        }
    )
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


async def test_query_uses_stored_unixcoder_model(mock_embed_models, ast_cache_conn):
    # PR #1352：不能因 OpenAI 可用就覆盖存储的 UniXcoder 空间。
    openai, unixcoder = mock_embed_models
    sid = _seed_symbol(ast_cache_conn, "fn")
    _seed_embedding(ast_cache_conn, sid, [1.0] + [0.0] * 767, "unixcoder-base")
    unixcoder.return_value = [[1.0] + [0.0] * 767]
    tool = SemanticNeighborsTool(project_root=None)
    tool._get_cache = MagicMock(return_value=_make_fake_cache(ast_cache_conn))
    result = await tool.execute({"query": "fn"})
    assert result["success"] is True
    assert [n["symbol_id"] for n in result["neighbors"]] == [sid]
    openai.assert_not_called()
    unixcoder.assert_called_once_with(["fn"])


@pytest.mark.parametrize(
    "models,vectors,error",
    [
        (["unknown"], [[1.0]], "UNKNOWN_EMBEDDING_MODEL"),
        (
            ["unixcoder-base", "text-embedding-3-small"],
            [[1.0], [1.0]],
            "MIXED_EMBEDDING_MODELS",
        ),
        (
            ["unixcoder-base", "unixcoder-base"],
            [[1.0], [1.0, 0.0]],
            "MIXED_EMBEDDING_DIMENSIONS",
        ),
    ],
)
async def test_invalid_embedding_store_never_calls_provider(
    mock_embed_models, ast_cache_conn, models, vectors, error
):
    # PR #1352：存储模型或维度不一致必须在模型调用前拒绝。
    for i, (model, vec) in enumerate(zip(models, vectors, strict=True)):
        sid = _seed_symbol(ast_cache_conn, str(i))
        _seed_embedding(ast_cache_conn, sid, vec, model)
    tool = SemanticNeighborsTool(project_root=None)
    tool._get_cache = MagicMock(return_value=_make_fake_cache(ast_cache_conn))
    result = await tool.execute({"query": "fn"})
    assert result["success"] is False
    assert error in result["error"]
    for provider in mock_embed_models:
        provider.assert_not_called()


async def test_query_dimension_mismatch_is_explicit(mock_embed_models, ast_cache_conn):
    # PR #1352：模型返回维度不一致，不能进入余弦运算或回退模型。
    sid = _seed_symbol(ast_cache_conn, "fn")
    _seed_embedding(ast_cache_conn, sid, [1.0] + [0.0] * 767, "unixcoder-base")
    tool = SemanticNeighborsTool(project_root=None)
    tool._get_cache = MagicMock(return_value=_make_fake_cache(ast_cache_conn))
    result = await tool.execute({"query": "fn"})
    assert result["success"] is False
    assert "QUERY_EMBEDDING_DIMENSION_MISMATCH" in result["error"]
    mock_embed_models[0].assert_not_called()


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"query": None}, "query"),
        ({"query": 7}, "query"),
        ({"top_k": 0}, "top_k"),
        ({"top_k": 51}, "top_k"),
        ({"top_k": True}, "top_k"),
        ({"top_k": 1.5}, "top_k"),
        ({"min_similarity": float("nan")}, "min_similarity"),
        ({"min_similarity": float("inf")}, "min_similarity"),
        ({"min_similarity": "0.5"}, "min_similarity"),
        ({"language": 7}, "language"),
        ({"kind": None}, "kind"),
        ({"use_combined_score": "false"}, "use_combined_score"),
    ],
)
async def test_semantic_public_parameter_error_never_calls_provider(
    mock_embed_models, changes, field
):
    # PR #1352：无效公开参数不能触发索引初始化或付费模型调用。
    tool = SemanticNeighborsTool(None)
    tool._get_cache = MagicMock(side_effect=AssertionError("must not open index"))
    response = await tool.execute({"query": "find function", **changes})
    assert response["success"] is False
    assert response["error_code"] == "INVALID_ARGUMENT"
    assert field in response["error"]
    assert response["count"] == 0
    assert response["neighbors"] == []
    tool._get_cache.assert_not_called()
    for provider in mock_embed_models:
        provider.assert_not_called()


async def test_semantic_zero_matches_keeps_exact_count(
    mock_embed_models, ast_cache_conn
):
    # PR #1352：有效查询零匹配必须返回 count=0，而不是建议重建已存在的索引。
    sid = _seed_symbol(ast_cache_conn, "fn")
    _seed_embedding(ast_cache_conn, sid, [1.0, 0.0])
    mock_embed_models[0].return_value = [[1.0, 0.0]]
    tool = SemanticNeighborsTool(None)
    tool._cache = _make_fake_cache(ast_cache_conn)
    response = await tool.execute({"query": "function", "language": "java"})
    assert response["success"] is True
    assert response["count"] == 0
    assert response["neighbors"] == []
    assert "pipeline" not in response.get("hint", "")
    mock_embed_models[0].assert_called_once_with(["function"], dimensions=2)


async def test_semantic_missing_combined_metadata_does_not_bill_provider(
    mock_embed_models, ast_cache_conn
):
    # PR #1352：请求组合评分时缺表不能伪造 heat/caller=0 的成功结果。
    sid = _seed_symbol(ast_cache_conn, "fn")
    _seed_embedding(ast_cache_conn, sid, [1.0, 0.0])
    ast_cache_conn.execute("DROP TABLE ast_symbol_activation")
    tool = SemanticNeighborsTool(None)
    tool._cache = _make_fake_cache(ast_cache_conn)
    response = await tool.execute({"query": "function", "use_combined_score": True})
    assert response["success"] is False
    assert (
        response["error"]
        == "COMBINED_SCORE_UNAVAILABLE: no such table: ast_symbol_activation"
    )
    assert response["neighbors"] == []
    for provider in mock_embed_models:
        provider.assert_not_called()


async def test_semantic_nan_provider_response_is_not_empty_success(
    mock_embed_models, ast_cache_conn
):
    # PR #1352：模型返回非有限数值是失败，不能落成空匹配成功。
    sid = _seed_symbol(ast_cache_conn, "fn")
    _seed_embedding(ast_cache_conn, sid, [1.0, 0.0])
    mock_embed_models[0].return_value = [[float("nan"), 0.0]]
    tool = SemanticNeighborsTool(None)
    tool._cache = _make_fake_cache(ast_cache_conn)
    response = await tool.execute({"query": "function"})
    assert response["success"] is False
    assert response["error"] == "INVALID_QUERY_EMBEDDING"
    assert response["neighbors"] == []
    mock_embed_models[1].assert_not_called()


async def test_semantic_missing_numpy_never_calls_provider(
    mock_embed_models, ast_cache_conn, monkeypatch
):
    # PR #1352：本地依赖缺失应在远程模型请求之前失败。
    from tree_sitter_analyzer.api import semantic

    sid = _seed_symbol(ast_cache_conn, "fn")
    _seed_embedding(ast_cache_conn, sid, [1.0, 0.0])
    monkeypatch.setattr(semantic, "_NUMPY_AVAILABLE", False)
    tool = SemanticNeighborsTool(None)
    tool._cache = _make_fake_cache(ast_cache_conn)
    response = await tool.execute({"query": "function"})
    assert response["success"] is False
    assert response["error"] == "numpy required for semantic search"
    for provider in mock_embed_models:
        provider.assert_not_called()


@pytest.mark.parametrize(
    "vector",
    [b"", b"bad", "not-a-blob", bytes(1537 * 4)],
    ids=["empty", "unaligned", "text", "oversized"],
)
async def test_semantic_invalid_vector_storage_fails_before_provider(
    mock_embed_models, ast_cache_conn, vector
):
    # PR #1352：SQLite 可存非 BLOB 或非法维度，必须在模型调用前阻止。
    sid = _seed_symbol(ast_cache_conn, "fn")
    ast_cache_conn.execute(
        "INSERT INTO symbol_embeddings VALUES (?, 'text-embedding-3-small', ?, '', 0)",
        (sid, vector),
    )
    tool = SemanticNeighborsTool(None)
    tool._cache = _make_fake_cache(ast_cache_conn)
    response = await tool.execute({"query": "function"})
    assert response["success"] is False
    assert response["error"] == "INVALID_EMBEDDING_DIMENSION"
    assert response["neighbors"] == []
    for provider in mock_embed_models:
        provider.assert_not_called()


async def test_semantic_accepts_integral_top_k_without_mutating_request(
    mock_embed_models, ast_cache_conn
):
    # PR #1352：公开 top_k 保持整值数字兼容，且严格限制返回数量。
    first = _seed_symbol(ast_cache_conn, "first")
    second = _seed_symbol(ast_cache_conn, "second")
    _seed_embedding(ast_cache_conn, first, [1.0, 0.0])
    _seed_embedding(ast_cache_conn, second, [0.0, 1.0])
    mock_embed_models[0].return_value = [[1.0, 0.0]]
    tool = SemanticNeighborsTool(None)
    tool._cache = _make_fake_cache(ast_cache_conn)
    arguments = {"query": "function", "top_k": 1.0, "min_similarity": 0}
    response = await tool.execute(arguments)
    assert response["success"] is True
    assert response["count"] == 1
    assert [item["symbol_id"] for item in response["neighbors"]] == [first]
    assert type(arguments["top_k"]) is float


async def test_search_semantic_disk_index_combined_ranking(tmp_path, monkeypatch):
    # PR #1352：只有模型边界替身；磁盘索引、真实调用边、元数据读取和评分均走生产链路。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.embeddings import pipeline
    from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade

    source = tmp_path / "ranking.py"
    source.write_text(
        'def semantic_only():\n    """semantic match"""\n    return 1\n\ndef hot_target():\n    """hot match"""\n    return 2\n'
        + "".join(f"\ndef caller_{i}():\n    return hot_target()\n" for i in range(50)),
        encoding="utf-8",
    )

    def embed(texts, **kwargs):
        vectors = []
        for text in texts:
            prefix = (
                [0.8, 0.6]
                if text.startswith("function:hot_target ")
                else (
                    [1.0, 0.0]
                    if text in ("warmup", "rank targets")
                    or text.startswith("function:semantic_only ")
                    else [0.0, 1.0]
                )
            )
            vectors.append(prefix + [0.0] * 1534)
        return vectors

    provider = MagicMock(side_effect=embed)
    wrong_provider = MagicMock(side_effect=AssertionError("wrong model provider"))
    monkeypatch.setattr(pipeline, "_embed_with_openai", provider)
    monkeypatch.setattr(pipeline, "_embed_with_unixcoder", wrong_provider)
    cache = ASTCache(str(tmp_path))
    try:
        assert (
            cache.index_project(max_files=2, workers=0, include_activation=False)[
                "errors"
            ]
            == 0
        )
        conn = cache.get_conn()
        assert pipeline.init_embeddings_db(conn) is True
        assert pipeline.run_pipeline(conn, model="openai")["indexed"] == 52
        conn.execute(
            "INSERT OR REPLACE INTO ast_symbol_activation(symbol_id,file_path,mod_count_30d,computed_at) "
            "SELECT id,file_path,CASE WHEN name='hot_target' THEN 100 ELSE 0 END,0 FROM ast_symbol_rows"
        )
        conn.commit()
        assert [
            tuple(r)
            for r in conn.execute(
                "SELECT DISTINCT model,length(vector) FROM symbol_embeddings"
            )
        ] == [("text-embedding-3-small", 6144)]
        assert (
            conn.execute(
                "SELECT count(*) FROM edges e JOIN ast_symbol_rows s ON s.id=e.callee_symbol_id "
                "WHERE e.kind='calls' AND s.name='hot_target'"
            ).fetchone()[0]
            == 50
        )
    finally:
        cache.close()
    provider.reset_mock()
    facade = build_search_facade(str(tmp_path))
    request = {
        "action": "semantic",
        "query": "rank targets",
        "top_k": 2,
        "min_similarity": 0.5,
    }
    plain = await facade.execute(request)
    weighted = await facade.execute({**request, "use_combined_score": True})
    assert plain["success"] is weighted["success"] is True
    assert plain["count"] == weighted["count"] == 2
    assert [n["name"] for n in plain["neighbors"]] == ["semantic_only", "hot_target"]
    assert [
        (
            n["name"],
            n["similarity"],
            n["git_heat"],
            n["caller_count"],
            n["combined_score"],
        )
        for n in weighted["neighbors"]
    ] == [("hot_target", 0.8, 100, 50, 0.86), ("semantic_only", 1.0, 0, 0, 0.7)]
    assert provider.call_count == 2
    for call in provider.call_args_list:
        assert call.args == (["rank targets"],)
        assert call.kwargs == {"dimensions": 1536}
    wrong_provider.assert_not_called()
