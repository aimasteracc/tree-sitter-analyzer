"""Bounded decoding contracts for the NO1-010B corpus loader."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from tree_sitter_analyzer.no1_010b.record import (
    BenchmarkRecordError,
    load_corpus_records,
)


def test_loader_rejects_excessive_json_nesting(tmp_path: Path) -> None:
    corpus = tmp_path / "bad.jsonl"
    corpus.write_text("[" * 100_000 + "]" * 100_000 + "\n", encoding="utf-8")
    with pytest.raises(BenchmarkRecordError, match="invalid JSON"):
        load_corpus_records(str(corpus))


def test_loader_rejects_oversized_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("x" * (8 * 1024 * 1024 + 1)))
    with pytest.raises(BenchmarkRecordError, match="8 MiB"):
        load_corpus_records("-")


def test_loader_rejects_empty_corpus(tmp_path: Path) -> None:
    corpus = tmp_path / "empty.jsonl"
    corpus.write_text("\n\n", encoding="utf-8")
    with pytest.raises(BenchmarkRecordError, match="corpus is empty"):
        load_corpus_records(str(corpus))


def test_loader_enforces_file_limit_in_bytes(tmp_path: Path) -> None:
    corpus = tmp_path / "oversized.jsonl"
    corpus.write_bytes("界".encode() * ((8 * 1024 * 1024) // 3 + 1))
    with pytest.raises(BenchmarkRecordError, match="8 MiB"):
        load_corpus_records(str(corpus))


def test_loader_rejects_non_utf8_bytes(tmp_path: Path) -> None:
    corpus = tmp_path / "binary.jsonl"
    corpus.write_bytes(b"\xff\n")
    with pytest.raises(BenchmarkRecordError, match="valid UTF-8"):
        load_corpus_records(str(corpus))


def test_loader_rejects_unencodable_text_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    # PR #1307 review: text-only stdin maps surrogate failures to record errors.
    monkeypatch.setattr(sys, "stdin", io.StringIO("\ud800"))
    with pytest.raises(BenchmarkRecordError, match="valid UTF-8"):
        load_corpus_records("-")


def test_loader_rejects_duplicate_keys(tmp_path: Path) -> None:
    corpus = tmp_path / "dup.jsonl"
    corpus.write_text('{"id": "a", "id": "b"}\n', encoding="utf-8")
    with pytest.raises(BenchmarkRecordError, match="duplicate key"):
        load_corpus_records(str(corpus))


def test_loader_rejects_nan_constant(tmp_path: Path) -> None:
    corpus = tmp_path / "nan.jsonl"
    corpus.write_text('{"id": "a", "task": NaN}\n', encoding="utf-8")
    with pytest.raises(BenchmarkRecordError, match="non-standard JSON constant"):
        load_corpus_records(str(corpus))
