"""Embedding pipeline for TSA symbol vectors.

Optional dependency chain:
  numpy               — required for cosine similarity
  sqlite-vss          — optional HNSW ANN index (vss0.so extension)
  Embed model — one of:
    UniXcoder (local HuggingFace): transformers + torch
    OpenAI text-embedding-3-small: openai SDK

Graceful degradation:
  - If sqlite-vss is unavailable, embeddings are stored in a plain BLOB
    column (symbol_embeddings.embedding) and similarity search falls back to
    numpy cosine over all rows (O(n)).
  - If no embed model is available, init_embeddings_db() still creates the
    schema; run_pipeline() raises EmbeddingModelUnavailableError.
  - All ImportError / extension load failures are caught and logged to
    a single top-level ``_EMBED_ERROR`` string; callers check that.

Schema (appended to existing SQLite DB):
  CREATE TABLE IF NOT EXISTS symbol_embeddings (
      symbol_id  INTEGER PRIMARY KEY REFERENCES ast_symbol_rows(id),
      model_name TEXT    NOT NULL,
      embedding  BLOB    NOT NULL,   -- float32 array, little-endian
      indexed_at INTEGER NOT NULL    -- unix timestamp
  );
  -- vss0 virtual table created when sqlite-vss is available:
  CREATE VIRTUAL TABLE IF NOT EXISTS vss_symbol_embeddings
      USING vss0(embedding(DIM));
"""

from __future__ import annotations

import json
import logging
import sqlite3
import struct
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_EMBED_ERROR: str | None = None
_NUMPY_AVAILABLE = False
_VSS_AVAILABLE = False
_UNIXCODER_CACHE: dict[str, Any] = {}
_OPENAI_CLIENT: Any = None

try:
    import numpy as _np  # noqa: F401

    _NUMPY_AVAILABLE = True
except ImportError:
    _EMBED_ERROR = "numpy not available — install numpy for embedding support"

_SCHEMA_SYMBOL_VECTORS = """
CREATE TABLE IF NOT EXISTS symbol_embeddings (
    symbol_id  INTEGER PRIMARY KEY REFERENCES ast_symbol_rows(id) ON DELETE CASCADE,
    model      TEXT    NOT NULL,
    vector     BLOB    NOT NULL,
    input_text TEXT,
    created_at INTEGER NOT NULL
);
"""


class EmbeddingModelUnavailableError(RuntimeError):
    """Raised when no embedding model can be loaded."""


def init_embeddings_db(conn: sqlite3.Connection) -> bool:
    """Create the symbol_embeddings table (and vss0 virtual table if available).

    Returns True if the schema was created successfully, False otherwise.
    """
    try:
        conn.executescript(_SCHEMA_SYMBOL_VECTORS)
        conn.commit()
    except sqlite3.OperationalError as exc:
        logger.warning("init_embeddings_db: schema creation failed: %s", exc)
        return False

    global _VSS_AVAILABLE
    if not _VSS_AVAILABLE:
        try:
            conn.enable_load_extension(True)
            conn.load_extension("vss0")
            _VSS_AVAILABLE = True
            logger.info("init_embeddings_db: sqlite-vss loaded")
        except Exception as exc:
            logger.debug(
                "init_embeddings_db: sqlite-vss unavailable (%s) — fallback to numpy cosine",
                exc,
            )

    return True


def build_embedding_input(symbol_row: dict[str, Any]) -> str:
    """使用真实索引字段构造 kind/name/class、签名和文档；缺少的字段不猜测。"""
    parts: list[str] = []
    kind = symbol_row.get("kind") or "symbol"
    name = symbol_row.get("name") or ""
    parts.append(f"{kind}:{name}")
    cls = symbol_row.get("class_name") or symbol_row.get("class") or ""
    if cls:
        parts.append(f"[{cls}]")
    signature = symbol_row.get("signature")
    if not signature and symbol_row.get("params"):
        signature = name + symbol_row["params"]
        if symbol_row.get("return_type"):
            signature += " -> " + symbol_row["return_type"]
    if signature:
        parts.append(str(signature))
    doc = symbol_row.get("docstring") or ""
    if doc:
        # Truncate docstrings to 256 chars to stay within token budget.
        parts.append(doc[:256])
    return " ".join(parts)


def _encode_embedding(vec: list[float]) -> bytes:
    """Pack a float32 list to little-endian BLOB."""
    return struct.pack(f"<{len(vec)}f", *vec)


def _decode_embedding(blob: bytes) -> list[float]:
    """Unpack a little-endian float32 BLOB to a list."""
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


def _embed_with_unixcoder(texts: list[str]) -> list[list[float]]:  # pragma: no cover
    """Embed texts using UniXcoder (local HuggingFace model)."""
    import torch
    from transformers import AutoModel, AutoTokenizer

    model_name = "microsoft/unixcoder-base"
    if model_name not in _UNIXCODER_CACHE:
        tokenizer = AutoTokenizer.from_pretrained(model_name)  # nosec B615 - hardcoded constant, not user input
        model = AutoModel.from_pretrained(model_name)  # nosec B615 - hardcoded constant, not user input
        model.eval()
        _UNIXCODER_CACHE[model_name] = (tokenizer, model)
    tokenizer, model = _UNIXCODER_CACHE[model_name]
    results = []
    with torch.no_grad():
        for text in texts:
            enc = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
            out = model(**enc)
            vec = out.last_hidden_state[:, 0, :].squeeze().tolist()
            results.append(vec)
    return results


def _embed_with_openai(
    texts: list[str],
    model: str = "text-embedding-3-small",
    *,
    dimensions: int | None = None,
) -> list[list[float]]:  # pragma: no cover
    """复用客户端，并在查询时请求与存储一致的向量维度。"""
    from openai import OpenAI

    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is None:
        _OPENAI_CLIENT = OpenAI()
    options = {"dimensions": dimensions} if dimensions is not None else {}
    response = _OPENAI_CLIENT.embeddings.create(input=texts, model=model, **options)
    return [item.embedding for item in response.data]


def run_pipeline(
    conn: sqlite3.Connection,
    *,
    model: str = "auto",
    batch_size: int = 32,
    rebuild: bool = False,
) -> dict[str, Any]:
    """Index symbol embeddings into the symbol_embeddings table.

    Args:
        conn: Open SQLite connection with ast_symbol_rows populated.
        model: One of ``"auto"`` / ``"unixcoder"`` / ``"openai"``.
               ``"auto"`` tries openai first, then unixcoder.
        batch_size: Number of symbols to embed per batch.
        rebuild: If True, drop and re-index all embeddings.

    Returns:
        dict with keys: model_name, indexed, skipped, errors, elapsed_s.

    Raises:
        EmbeddingModelUnavailableError: when no model can be loaded.
    """
    if not _NUMPY_AVAILABLE:
        raise EmbeddingModelUnavailableError(
            _EMBED_ERROR or "numpy required for embeddings"
        )
    if type(batch_size) is not int or not 1 <= batch_size <= 1024:
        raise ValueError("batch_size must be within 1..1024")

    # 先验证输入，避免元数据错误触发模型请求或破坏已有向量。
    already_indexed: set[int] = (
        set()
        if rebuild
        else {r[0] for r in conn.execute("SELECT symbol_id FROM symbol_embeddings")}
    )

    rows = conn.execute(
        "SELECT id, name, kind, file_path, line FROM ast_symbol_rows ORDER BY file_path, line, id"
    ).fetchall()

    to_index = [r for r in rows if r[0] not in already_indexed]

    indexed = 0
    errors = 0
    t0 = time.monotonic()

    # 每文件只解析一次 symbols_json，按精确身份取元数据，不能只按名字拿首条。
    texts_by_id: dict[int, str] = {}
    current_file: str | None = None
    metadata: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    for row in to_index:
        if row[3] != current_file:
            current_file = row[3]
            stored = conn.execute(
                "SELECT symbols_json FROM ast_index WHERE file_path=?", (current_file,)
            ).fetchone()
            payload = json.loads(stored[0]) if stored else {}
            metadata = {}
            for symbol in payload.get("symbols", []):
                key = (symbol.get("name"), symbol.get("kind"), symbol.get("line"))
                if key in metadata:
                    raise ValueError("AMBIGUOUS_EMBEDDING_SYMBOL")
                metadata[key] = symbol
        symbol = metadata.get((row[1], row[2], row[4]))
        if symbol is None:
            logger.warning(
                "EMBEDDING_METADATA_MISSING: %s:%s:%s", row[3], row[1], row[4]
            )
        texts_by_id[row[0]] = build_embedding_input(
            symbol or {"name": row[1], "kind": row[2]}
        )

    embed_fn: Callable[..., list[list[float]]] | None = None
    model_name = ""
    if model in ("auto", "openai"):
        try:
            _embed_with_openai(["warmup"])
            embed_fn = _embed_with_openai
            model_name = "text-embedding-3-small"
        except Exception as exc:
            logger.debug("run_pipeline: openai unavailable (%s)", exc)
    if embed_fn is None and model in ("auto", "unixcoder"):
        try:
            _embed_with_unixcoder(["warmup"])
            embed_fn = _embed_with_unixcoder
            model_name = "unixcoder-base"
        except Exception as exc:
            logger.debug("run_pipeline: unixcoder unavailable (%s)", exc)
    if embed_fn is None:
        raise EmbeddingModelUnavailableError(
            "No embedding model available. Install openai or transformers+torch."
        )

    # 重建采用保存点；任一批次失败都恢复旧索引，不提交半成品。
    if rebuild:
        conn.execute("SAVEPOINT embeddings_rebuild")
        conn.execute("DELETE FROM symbol_embeddings")
    for i in range(0, len(to_index), batch_size):
        batch = to_index[i : i + batch_size]
        texts = [texts_by_id[r[0]] for r in batch]
        try:
            vecs = embed_fn(texts)
            now = int(time.time())
            conn.executemany(
                "INSERT OR REPLACE INTO symbol_embeddings "
                "(symbol_id, model, vector, input_text, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (batch[j][0], model_name, _encode_embedding(vecs[j]), texts[j], now)
                    for j in range(len(batch))
                ],
            )
            if not rebuild:
                conn.commit()
            indexed += len(batch)
        except Exception as exc:
            logger.warning("run_pipeline: batch %d failed: %s", i // batch_size, exc)
            errors += len(batch)
            if rebuild:
                conn.execute("ROLLBACK TO embeddings_rebuild")
                conn.execute("RELEASE embeddings_rebuild")
                indexed = 0
                errors = len(to_index)
                break

    if rebuild and not errors:
        conn.execute("RELEASE embeddings_rebuild")
        conn.commit()

    elapsed = time.monotonic() - t0
    return {
        "model_name": model_name,
        "indexed": indexed,
        "skipped": len(already_indexed),
        "errors": errors,
        "elapsed_s": round(elapsed, 2),
    }
