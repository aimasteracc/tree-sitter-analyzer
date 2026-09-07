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


@pytest.mark.parametrize(
    "stored,requested", [("openai", "unixcoder"), ("unixcoder", "openai")]
)
def test_incremental_explicit_model_change_requires_atomic_rebuild(
    ast_cache_conn, openai_transport, unixcoder_transport, stored, requested
):
    """PR #1352 P2：同维度的不同模型也不得增量混写；明确切换必须走原子重建。"""
    _seed_symbol(ast_cache_conn, "old_symbol")
    assert run_pipeline(ast_cache_conn, model=stored)["indexed"] == 1
    before = [
        tuple(r) for r in ast_cache_conn.execute("SELECT * FROM symbol_embeddings")
    ]
    _seed_symbol(ast_cache_conn, "new_symbol")
    openai_transport.reset_mock()
    unixcoder_transport.reset_mock()
    with pytest.raises(ValueError, match="EMBEDDING_MODEL_MISMATCH.*rebuild=True"):
        run_pipeline(ast_cache_conn, model=requested)
    assert [
        tuple(r) for r in ast_cache_conn.execute("SELECT * FROM symbol_embeddings")
    ] == before
    openai_transport.assert_not_called()
    unixcoder_transport.assert_not_called()
    result = run_pipeline(ast_cache_conn, model=requested, rebuild=True)
    assert (result["indexed"], result["skipped"], result["errors"]) == (2, 0, 0)
    expected = "text-embedding-3-small" if requested == "openai" else "unixcoder-base"
    assert [
        tuple(r)
        for r in ast_cache_conn.execute(
            "SELECT DISTINCT model,length(vector) FROM symbol_embeddings"
        )
    ] == [(expected, 8)]


@pytest.mark.parametrize("stored", ["openai", "unixcoder"])
def test_auto_incremental_binds_existing_provider_even_when_unavailable(
    ast_cache_conn, openai_transport, unixcoder_transport, stored
):
    """PR #1352 P2：auto 只续写已有模型；该 provider 失败不得回退到另一向量空间。"""
    _seed_symbol(ast_cache_conn, "old_symbol")
    run_pipeline(ast_cache_conn, model=stored)
    before = [
        tuple(r) for r in ast_cache_conn.execute("SELECT * FROM symbol_embeddings")
    ]
    _seed_symbol(ast_cache_conn, "new_symbol")
    openai_transport.reset_mock()
    unixcoder_transport.reset_mock()
    selected, other = (
        (openai_transport, unixcoder_transport)
        if stored == "openai"
        else (unixcoder_transport, openai_transport)
    )
    selected.side_effect = RuntimeError("provider offline")
    with pytest.raises(EmbeddingModelUnavailableError):
        run_pipeline(ast_cache_conn)
    other.assert_not_called()
    assert [
        tuple(r) for r in ast_cache_conn.execute("SELECT * FROM symbol_embeddings")
    ] == before


def test_incremental_openai_requests_existing_dimension(
    ast_cache_conn, openai_transport, unixcoder_transport
):
    """PR #1352 P2：缩维索引续写时必须把原维度传给 SDK，而不是使用 provider 默认维度。"""
    from types import SimpleNamespace

    _seed_symbol(ast_cache_conn, "old_symbol")
    run_pipeline(ast_cache_conn, model="openai")
    _seed_symbol(ast_cache_conn, "new_symbol")
    openai_transport.reset_mock()

    def response(**kwargs):
        dimension = kwargs.get("dimensions", 3)
        return SimpleNamespace(
            data=[
                SimpleNamespace(embedding=[1.0] + [0.0] * (dimension - 1))
                for _ in kwargs["input"]
            ]
        )

    openai_transport.side_effect = response
    result = run_pipeline(ast_cache_conn)
    assert (result["indexed"], result["errors"]) == (1, 0)
    assert [call.kwargs["dimensions"] for call in openai_transport.call_args_list] == [
        2,
        2,
    ]
    assert [
        r[0]
        for r in ast_cache_conn.execute(
            "SELECT DISTINCT length(vector) FROM symbol_embeddings"
        )
    ] == [8]
    unixcoder_transport.assert_not_called()


def test_incremental_provider_dimension_drift_keeps_existing_vectors(
    ast_cache_conn, openai_transport
):
    """PR #1352 P2：provider 忽略约定维度时该批失败，不能污染已存向量。"""
    from types import SimpleNamespace

    _seed_symbol(ast_cache_conn, "old_symbol")
    run_pipeline(ast_cache_conn, model="openai")
    before = [
        tuple(r) for r in ast_cache_conn.execute("SELECT * FROM symbol_embeddings")
    ]
    _seed_symbol(ast_cache_conn, "new_symbol")
    openai_transport.side_effect = lambda **kwargs: SimpleNamespace(
        data=[SimpleNamespace(embedding=[1.0, 0.0, 0.0])]
    )
    result = run_pipeline(ast_cache_conn)
    assert (result["indexed"], result["errors"]) == (0, 1)
    assert [
        tuple(r) for r in ast_cache_conn.execute("SELECT * FROM symbol_embeddings")
    ] == before


@pytest.mark.parametrize("area", ["semantic", "pipeline"])
def test_missing_numpy_import_preserves_explicit_dependency_error(
    monkeypatch, ast_cache_conn, area
):
    """PR #1352：真实导入失败必须保留可诊断错误，不能尝试读取 SQL 或请求模型。"""
    import importlib.util
    import sys

    from tree_sitter_analyzer.api import semantic
    from tree_sitter_analyzer.embeddings import pipeline

    owner = semantic if area == "semantic" else pipeline
    spec = importlib.util.spec_from_file_location(
        owner.__name__ + "_without_numpy", owner.__file__
    )
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as m:
        m.setitem(sys.modules, "numpy", None)
        spec.loader.exec_module(module)
    assert module._NUMPY_AVAILABLE is False
    if area == "semantic":
        with pytest.raises(
            module.SemanticUnavailableError,
            match="numpy required for cosine_similarity",
        ):
            module.cosine_similarity([1.0], [1.0])
    else:
        with pytest.raises(
            module.EmbeddingModelUnavailableError, match="numpy not available"
        ):
            module.run_pipeline(ast_cache_conn)


@pytest.mark.parametrize("batch_size", [0, 1025, True, 1.5])
def test_invalid_batch_does_not_contact_provider_or_modify_store(
    ast_cache_conn, openai_transport, batch_size
):
    """PR #1352：非法批量大小在任何模型请求和重建删除前拒绝。"""
    with pytest.raises(ValueError, match="batch_size must be within 1..1024"):
        run_pipeline(ast_cache_conn, rebuild=True, batch_size=batch_size)
    openai_transport.assert_not_called()
    assert (
        ast_cache_conn.execute("SELECT count(*) FROM symbol_embeddings").fetchone()[0]
        == 0
    )


def test_embedding_schema_read_only_failure_is_reported(ast_cache_conn):
    """PR #1352：创建表失败不能声称初始化成功。"""
    ast_cache_conn.execute("DROP TABLE symbol_embeddings")
    ast_cache_conn.execute("PRAGMA query_only=ON")
    try:
        assert init_embeddings_db(ast_cache_conn) is False
        assert (
            ast_cache_conn.execute(
                "SELECT name FROM sqlite_master WHERE name='symbol_embeddings'"
            ).fetchall()
            == []
        )
    finally:
        ast_cache_conn.execute("PRAGMA query_only=OFF")


def test_incremental_failed_batch_cannot_be_committed_by_next_batch(
    ast_cache_conn, openai_transport
):
    """PR #1352：真实触发器拒绝批次后，其前半部分不能被下一成功批次提交。"""
    for name in ("first", "second", "third"):
        _seed_symbol(ast_cache_conn, name)
    ast_cache_conn.execute(
        "CREATE TRIGGER reject_second BEFORE INSERT ON symbol_embeddings "
        "WHEN NEW.symbol_id=(SELECT id FROM ast_symbol_rows WHERE name='second') "
        "BEGIN SELECT RAISE(ABORT, 'storage refused'); END"
    )
    result = run_pipeline(ast_cache_conn, model="openai", batch_size=2)
    assert (result["indexed"], result["errors"]) == (1, 2)
    assert [
        r[0]
        for r in ast_cache_conn.execute(
            "SELECT s.name FROM symbol_embeddings e JOIN ast_symbol_rows s ON s.id=e.symbol_id"
        )
    ] == ["third"]


@pytest.mark.parametrize("vector", [[], [float("nan"), 0.0], [float("inf"), 0.0]])
def test_invalid_provider_vector_cannot_replace_healthy_index(
    ast_cache_conn, openai_transport, vector
):
    """PR #1352：provider 的空向量和非有限浮点不能替换可搜索的旧向量。"""
    from types import SimpleNamespace

    _seed_symbol(ast_cache_conn, "alpha")
    assert run_pipeline(ast_cache_conn, model="openai")["indexed"] == 1
    before = [
        tuple(r) for r in ast_cache_conn.execute("SELECT * FROM symbol_embeddings")
    ]
    openai_transport.side_effect = lambda **kwargs: SimpleNamespace(
        data=[SimpleNamespace(embedding=vector)]
    )
    result = run_pipeline(ast_cache_conn, model="openai", rebuild=True)
    assert (result["indexed"], result["errors"]) == (0, 1)
    assert [
        tuple(r) for r in ast_cache_conn.execute("SELECT * FROM symbol_embeddings")
    ] == before


def test_embedding_extension_loading_is_optional_and_not_repeated(monkeypatch):
    """PR #1352：外部扩展加载成功后不重复请求，真实普通向量表仍可正常使用。"""
    import sqlite3

    from tree_sitter_analyzer.embeddings import pipeline

    loads = []

    class ExtensionConnection(sqlite3.Connection):
        def load_extension(self, path):
            loads.append(path)

    monkeypatch.setattr(pipeline, "_VSS_AVAILABLE", False)
    db = sqlite3.connect(":memory:", factory=ExtensionConnection)
    try:
        assert init_embeddings_db(db) is True
        assert init_embeddings_db(db) is True
        assert loads == ["vss0"]
        assert db.execute("SELECT count(*) FROM symbol_embeddings").fetchone()[0] == 0
    finally:
        db.close()


def test_explicit_local_model_uses_real_adapter_without_remote_request(
    ast_cache_conn, monkeypatch, openai_transport
):
    """PR #1352：显式 unixcoder 选择只访问本地模型 SDK，绝不请求远程 provider。"""
    import sys
    from contextlib import nullcontext
    from types import SimpleNamespace

    from tree_sitter_analyzer.embeddings import pipeline

    class Tensor:
        def __getitem__(self, key):
            return self

        def squeeze(self):
            return self

        def tolist(self):
            return [1.0, 0.0]

    def tokenizer(text, **kwargs):
        return {"text": text}

    def model(**kwargs):
        return SimpleNamespace(last_hidden_state=Tensor())

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(no_grad=nullcontext))
    monkeypatch.setitem(
        sys.modules, "transformers", SimpleNamespace(AutoModel=None, AutoTokenizer=None)
    )
    monkeypatch.setattr(
        pipeline, "_UNIXCODER_CACHE", {"microsoft/unixcoder-base": (tokenizer, model)}
    )
    sid = _seed_symbol(ast_cache_conn, "local")
    result = run_pipeline(ast_cache_conn, model="unixcoder")
    assert (result["model_name"], result["indexed"], result["errors"]) == (
        "unixcoder-base",
        1,
        0,
    )
    row = ast_cache_conn.execute(
        "SELECT symbol_id,model,vector FROM symbol_embeddings"
    ).fetchone()
    assert tuple(row) == (sid, "unixcoder-base", _encode_embedding([1.0, 0.0]))
    openai_transport.assert_not_called()


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
