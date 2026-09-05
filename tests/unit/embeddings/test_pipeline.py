"""Tests for tree_sitter_analyzer.embeddings.pipeline.

Covers: init_embeddings_db, _encode_embedding/_decode_embedding roundtrip,
build_embedding_input format, run_pipeline model selection and batching.
Target coverage: ~75-85% of pipeline.py reachable lines.
"""

from __future__ import annotations

import sqlite3
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
    count = ast_cache_conn.execute("SELECT COUNT(*) FROM symbol_embeddings").fetchone()[0]
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
    id_b = _seed_symbol(ast_cache_conn, "fn_e")

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
        [[0.1, 0.2]],               # warmup succeeds → openai selected
        RuntimeError("batch fail"), # actual batch raises
    ]

    _seed_symbol(ast_cache_conn, "fn_f")

    result = run_pipeline(ast_cache_conn, model="openai")
    assert result["model_name"] == "text-embedding-3-small"
    assert result["errors"] == 1   # fn_f counted as error
    assert result["indexed"] == 0
