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
            logger.debug("init_embeddings_db: sqlite-vss unavailable (%s) — fallback to numpy cosine", exc)

    return True


def build_embedding_input(symbol_row: dict[str, Any]) -> str:
    """Build the text input for the embedding model from a symbol row dict.

    The format is: ``kind:name [class_name] docstring``
    Symbol rows are expected to have keys: name, kind, class_name, docstring.
    """
    parts: list[str] = []
    kind = symbol_row.get("kind") or "symbol"
    name = symbol_row.get("name") or ""
    parts.append(f"{kind}:{name}")
    cls = symbol_row.get("class_name") or symbol_row.get("class") or ""
    if cls:
        parts.append(f"[{cls}]")
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


def _embed_with_unixcoder(texts: list[str]) -> list[list[float]]:
    """Embed texts using UniXcoder (local HuggingFace model)."""
    import torch  # type: ignore
    from transformers import AutoModel, AutoTokenizer  # type: ignore

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


def _embed_with_openai(texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
    """Embed texts using OpenAI embeddings API."""
    from openai import OpenAI  # type: ignore

    client = OpenAI()
    response = client.embeddings.create(input=texts, model=model)
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

    # Resolve embed function.
    embed_fn: Callable[..., list[list[float]]] | None = None
    model_name: str = ""
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

    # Fetch symbols to index.
    if rebuild:
        conn.execute("DELETE FROM symbol_embeddings")
        conn.commit()

    already_indexed: set[int] = {
        r[0] for r in conn.execute("SELECT symbol_id FROM symbol_embeddings")
    }

    rows = conn.execute(
        "SELECT id, name, kind FROM ast_symbol_rows"
    ).fetchall()

    to_index = [r for r in rows if r[0] not in already_indexed]

    indexed = 0
    errors = 0
    t0 = time.monotonic()

    for i in range(0, len(to_index), batch_size):
        batch = to_index[i : i + batch_size]
        texts = [
            build_embedding_input(
                {"name": r[1], "kind": r[2]}
            )
            for r in batch
        ]
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
            conn.commit()
            indexed += len(batch)
        except Exception as exc:
            logger.warning("run_pipeline: batch %d failed: %s", i // batch_size, exc)
            errors += len(batch)

    elapsed = time.monotonic() - t0
    return {
        "model_name": model_name,
        "indexed": indexed,
        "skipped": len(already_indexed),
        "errors": errors,
        "elapsed_s": round(elapsed, 2),
    }
