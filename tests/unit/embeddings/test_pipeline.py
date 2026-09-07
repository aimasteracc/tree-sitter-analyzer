"""Tests for tree_sitter_analyzer.embeddings.pipeline.

Covers: init_embeddings_db, _encode_embedding/_decode_embedding roundtrip,
build_embedding_input format, run_pipeline model selection and batching.
Target coverage: ~75-85% of pipeline.py reachable lines.
"""

from __future__ import annotations

import struct
import time

import pytest

from tree_sitter_analyzer.embeddings.pipeline import (
    EmbeddingModelUnavailableError,
    _decode_embedding,
    _encode_embedding,
    build_embedding_input,
    init_embeddings_db,
    run_pipeline,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _seed_symbol(conn, name: str, kind: str = "function") -> int:
    cur = conn.execute(
        "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, kind, "a.py", "python", 1, 10),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# init_embeddings_db
# ---------------------------------------------------------------------------


def test_init_embeddings_db_creates_table(ast_cache_conn):
    """init_embeddings_db returns True and the table is accessible."""
    # The fixture already creates symbol_embeddings; calling init again is idempotent.
    result = init_embeddings_db(ast_cache_conn)
    assert result is True
    count = ast_cache_conn.execute("SELECT COUNT(*) FROM symbol_embeddings").fetchone()[
        0
    ]
    assert count == 0  # empty but present


# ---------------------------------------------------------------------------
# Encode/decode roundtrip
# ---------------------------------------------------------------------------


def test_encode_decode_roundtrip():
    vec = [1.0, 2.0, -3.5]
    decoded = _decode_embedding(_encode_embedding(vec))
    assert decoded == pytest.approx(vec)


def test_encode_empty_vector():
    blob = _encode_embedding([])
    assert _decode_embedding(blob) == []


# ---------------------------------------------------------------------------
# build_embedding_input
# ---------------------------------------------------------------------------


def test_build_embedding_input_basic():
    row = {"name": "fn", "kind": "function"}
    result = build_embedding_input(row)
    assert "function:fn" in result


def test_build_embedding_input_truncates_docstring():
    long_doc = "x" * 300
    row = {"name": "fn", "kind": "function", "docstring": long_doc}
    result = build_embedding_input(row)
    # docstring is truncated to 256 chars before joining
    assert len(result) < len("function:fn") + 1 + 300 + 10  # well below full length
    assert "x" * 256 in result
    assert "x" * 257 not in result


def test_build_embedding_input_with_class():
    row = {"name": "method", "kind": "method", "class_name": "MyClass"}
    result = build_embedding_input(row)
    assert "[MyClass]" in result


def test_build_embedding_input_missing_fields():
    row = {}
    result = build_embedding_input(row)
    assert "symbol:" in result  # defaults


# ---------------------------------------------------------------------------
# run_pipeline — model selection
# ---------------------------------------------------------------------------


def test_run_pipeline_auto_openai_wins(mock_embed_models, ast_cache_conn):
    """With auto mode, openai is tried first; unixcoder not called."""
    mock_openai, mock_unixcoder = mock_embed_models
    mock_openai.return_value = [[0.1, 0.2, 0.3]]
    mock_openai.side_effect = None
    mock_unixcoder.side_effect = None

    _seed_symbol(ast_cache_conn, "fn_a")

    result = run_pipeline(ast_cache_conn, model="auto")
    assert result["model_name"] == "text-embedding-3-small"
    assert result["indexed"] == 1
    assert mock_unixcoder.call_count == 0


def test_run_pipeline_auto_falls_back_to_unixcoder(mock_embed_models, ast_cache_conn):
    """When openai fails, unixcoder is used."""
    mock_openai, mock_unixcoder = mock_embed_models
    mock_openai.side_effect = RuntimeError("no openai")
    mock_unixcoder.return_value = [[0.3, 0.4]]
    mock_unixcoder.side_effect = None

    _seed_symbol(ast_cache_conn, "fn_b")

    result = run_pipeline(ast_cache_conn, model="auto")
    assert result["model_name"] == "unixcoder-base"


def test_run_pipeline_both_models_unavailable(mock_embed_models, ast_cache_conn):
    """When both models fail, EmbeddingModelUnavailableError is raised."""
    mock_openai, mock_unixcoder = mock_embed_models
    mock_openai.side_effect = RuntimeError("unavailable")
    mock_unixcoder.side_effect = RuntimeError("unavailable")

    _seed_symbol(ast_cache_conn, "fn_c")

    with pytest.raises(EmbeddingModelUnavailableError):
        run_pipeline(ast_cache_conn, model="auto")


def test_run_pipeline_skips_already_indexed(mock_embed_models, ast_cache_conn):
    """Symbols already in symbol_embeddings are skipped."""
    mock_openai, _ = mock_embed_models
    mock_openai.return_value = [[0.1, 0.2]]
    mock_openai.side_effect = None

    id_a = _seed_symbol(ast_cache_conn, "fn_d")
    _seed_symbol(ast_cache_conn, "fn_e")

    # Pre-index fn_d manually
    blob = struct.pack("<2f", 0.1, 0.2)
    ast_cache_conn.execute(
        "INSERT INTO symbol_embeddings (symbol_id, model, vector, input_text, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (id_a, "text-embedding-3-small", blob, "", int(time.time())),
    )
    ast_cache_conn.commit()

    result = run_pipeline(ast_cache_conn, model="openai")
    assert result["skipped"] == 1
    assert result["indexed"] == 1  # only fn_e


def test_run_pipeline_batch_error_counts_errors(mock_embed_models, ast_cache_conn):
    """A batch failure increments the errors counter by batch size."""
    mock_openai, _ = mock_embed_models
    # Call 0: warmup → succeeds (openai selected)
    # Call 1: actual batch → raises → errors += 1
    mock_openai.side_effect = [
        [[0.1, 0.2]],  # warmup succeeds → openai selected
        RuntimeError("batch fail"),  # actual batch raises
    ]

    _seed_symbol(ast_cache_conn, "fn_f")

    result = run_pipeline(ast_cache_conn, model="openai")
    assert result["model_name"] == "text-embedding-3-small"
    assert result["errors"] == 1  # fn_f counted as error
    assert result["indexed"] == 0


def test_pipeline_uses_exact_indexed_signature_and_docstring(
    tmp_path, mock_embed_models
):
    # PR #1352：使用真实索引中的定义身份，模型边界以外不 mock。
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "a.py"
    source.write_text(
        'def run(x: int) -> str:\n    """first doc"""\n    return str(x)\n\n'
        'def run(y: str) -> int:\n    """second doc"""\n    return len(y)\n',
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    openai, _ = mock_embed_models
    openai.side_effect = lambda texts: [[1.0, 0.0] for _ in texts]
    try:
        cache.index_file(str(source))
        conn = cache.get_conn()
        init_embeddings_db(conn)
        result = run_pipeline(conn, model="openai", batch_size=1)
        assert result["indexed"] == 2
        rows = conn.execute(
            "SELECT input_text FROM symbol_embeddings ORDER BY symbol_id"
        ).fetchall()
        assert [row[0] for row in rows] == [
            "function:run run(x: int) -> str first doc",
            "function:run run(y: str) -> int second doc",
        ]
    finally:
        cache.close()


def test_openai_client_reused_between_batches(monkeypatch):
    # PR #1352：只替换 SDK 模型边界，不创建真实客户端或网络请求。
    import sys
    from types import SimpleNamespace
    from unittest.mock import Mock

    import tree_sitter_analyzer.embeddings.pipeline as pipeline

    factory = Mock()
    factory.return_value.embeddings.create.return_value = SimpleNamespace(
        data=[SimpleNamespace(embedding=[1.0])]
    )
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=factory))
    monkeypatch.setattr(pipeline, "_OPENAI_CLIENT", None)
    for text in ("batch one", "batch two"):
        assert pipeline._embed_with_openai([text], dimensions=1) == [[1.0]]
    factory.assert_called_once_with()
    assert factory.return_value.embeddings.create.call_count == 2


def test_unixcoder_model_reused_between_batches(monkeypatch):
    # PR #1352：假模型验证实例复用，不加载 torch 或下载权重。
    import sys
    from contextlib import nullcontext
    from types import SimpleNamespace
    from unittest.mock import MagicMock, Mock

    import tree_sitter_analyzer.embeddings.pipeline as pipeline

    tokenizer = Mock(return_value={})
    model = MagicMock()
    model.return_value.last_hidden_state.__getitem__.return_value.squeeze.return_value.tolist.return_value = [
        1.0
    ]
    tokenizer_loader = Mock(return_value=tokenizer)
    model_loader = Mock(return_value=model)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(no_grad=nullcontext))
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=tokenizer_loader),
            AutoModel=SimpleNamespace(from_pretrained=model_loader),
        ),
    )
    monkeypatch.setattr(pipeline, "_UNIXCODER_CACHE", {})
    assert pipeline._embed_with_unixcoder(["one"]) == [[1.0]]
    assert pipeline._embed_with_unixcoder(["two"]) == [[1.0]]
    model_loader.assert_called_once_with("microsoft/unixcoder-base")
    tokenizer_loader.assert_called_once_with("microsoft/unixcoder-base")
    model.eval.assert_called_once_with()


def test_rebuild_replaces_existing_vector(mock_embed_models, ast_cache_conn):
    # PR #1352：rebuild 必须更新已有 ID，而不是把它当已索引跳过。
    sid = _seed_symbol(ast_cache_conn, "fn")
    old = _encode_embedding([1.0, 0.0])
    ast_cache_conn.execute(
        "INSERT INTO symbol_embeddings VALUES (?, 'old', ?, 'old input', 0)", (sid, old)
    )
    ast_cache_conn.commit()
    mock_embed_models[0].return_value = [[0.0, 1.0]]
    result = run_pipeline(ast_cache_conn, model="openai", rebuild=True)
    row = ast_cache_conn.execute(
        "SELECT symbol_id, model, vector, input_text FROM symbol_embeddings"
    ).fetchone()
    assert tuple(row) == (
        sid,
        "text-embedding-3-small",
        _encode_embedding([0.0, 1.0]),
        "function:fn",
    )
    assert result["indexed"] == 1
    assert result["skipped"] == 0


def test_failed_rebuild_preserves_existing_vectors(mock_embed_models, ast_cache_conn):
    # PR #1352：模型失败不能先清空已有可用索引。
    sid = _seed_symbol(ast_cache_conn, "fn")
    old = _encode_embedding([1.0, 0.0])
    ast_cache_conn.execute(
        "INSERT INTO symbol_embeddings VALUES (?, 'old', ?, 'old input', 0)", (sid, old)
    )
    ast_cache_conn.commit()
    mock_embed_models[0].side_effect = [[[0.0, 1.0]], RuntimeError("provider failed")]
    result = run_pipeline(ast_cache_conn, model="openai", rebuild=True)
    assert result["indexed"] == 0
    assert result["errors"] == 1
    assert [
        tuple(r)
        for r in ast_cache_conn.execute(
            "SELECT symbol_id,model,vector FROM symbol_embeddings"
        )
    ] == [(sid, "old", old)]


def test_ambiguous_metadata_rebuild_preserves_existing_vectors(
    mock_embed_models, ast_cache_conn
):
    # PR #1352：验证元数据应先于破坏性写入，同名同位置歧义不能清空旧向量。
    import json

    sid = _seed_symbol(ast_cache_conn, "fn")
    old = _encode_embedding([1.0])
    ast_cache_conn.execute(
        "INSERT INTO symbol_embeddings VALUES (?, 'old', ?, 'old input', 0)", (sid, old)
    )
    symbol = {"name": "fn", "kind": "function", "line": 1, "docstring": "doc"}
    ast_cache_conn.execute(
        "INSERT INTO ast_index(file_path,content_hash,language,mtime_ns,file_size,indexed_at,symbols_json) "
        "VALUES ('a.py','hash','python',0,0,'',?)",
        (json.dumps({"symbols": [symbol, symbol]}),),
    )
    ast_cache_conn.commit()
    with pytest.raises(ValueError, match="AMBIGUOUS_EMBEDDING_SYMBOL"):
        run_pipeline(ast_cache_conn, model="openai", rebuild=True)
    assert [
        tuple(r)
        for r in ast_cache_conn.execute(
            "SELECT symbol_id,model,vector FROM symbol_embeddings"
        )
    ] == [(sid, "old", old)]
    for provider in mock_embed_models:
        provider.assert_not_called()


def test_rebuild_rolls_back_earlier_batch_when_later_batch_fails(
    mock_embed_models, ast_cache_conn
):
    # PR #1352：失败发生在后续批次时，也不能留下前一批次的半成品。
    ids = [_seed_symbol(ast_cache_conn, name) for name in ("first", "second")]
    old = _encode_embedding([1.0, 0.0])
    ast_cache_conn.executemany(
        "INSERT INTO symbol_embeddings VALUES (?, 'old', ?, 'old input', 0)",
        [(sid, old) for sid in ids],
    )
    ast_cache_conn.commit()
    mock_embed_models[0].side_effect = [
        [[0.0, 1.0]],
        [[0.0, 1.0]],
        RuntimeError("second batch failed"),
    ]
    result = run_pipeline(ast_cache_conn, model="openai", rebuild=True, batch_size=1)
    assert result["indexed"] == 0
    assert result["errors"] == 2
    assert [
        tuple(r)
        for r in ast_cache_conn.execute(
            "SELECT symbol_id,model,vector FROM symbol_embeddings ORDER BY symbol_id"
        )
    ] == [(sid, "old", old) for sid in ids]
